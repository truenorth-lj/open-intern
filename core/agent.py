"""Core agent — raw LangGraph StateGraph with native async throughout."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from core.compaction import compact_context, needs_compaction
from core.config import AppConfig
from core.cost_guard import BudgetExceededError, CostGuard, RateLimitExceededError
from core.exceptions import AgentNotInitializedError
from core.identity import build_system_prompt
from core.types import ChatContext, TokenUsage
from memory.store import MemoryEntry, MemoryScope, MemoryStore
from safety.permissions import ActionVerdict, SafetyMiddleware

logger = logging.getLogger(__name__)

# Provider mapping for init_chat_model
PROVIDER_MAP = {
    "claude": "anthropic",
    "anthropic": "anthropic",
    "openai": "openai",
    "ollama": "ollama",
}

# Providers that use Anthropic-compatible API with custom base_url
ANTHROPIC_COMPATIBLE_PROVIDERS = {
    "minimax": "https://api.minimax.io/anthropic",
}


def _create_llm(config: AppConfig):
    """Create the LLM instance based on config."""

    provider = config.llm.provider
    anthropic_base_url = ANTHROPIC_COMPATIBLE_PROVIDERS.get(provider)

    if anthropic_base_url:
        from langchain_anthropic import ChatAnthropic

        api_key = config.llm.api_key
        if api_key:
            os.environ.setdefault("ANTHROPIC_API_KEY", api_key)

        return ChatAnthropic(
            model=config.llm.model,
            base_url=anthropic_base_url,
            api_key=api_key,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens_per_action,
        )
    else:
        model_string = _resolve_model_string(config)
        kwargs: dict = {"temperature": config.llm.temperature}
        if config.llm.api_key:
            kwargs["api_key"] = config.llm.api_key
        return init_chat_model(model_string, **kwargs)


def _resolve_model_string(config: AppConfig) -> str:
    """Convert config to init_chat_model format like 'anthropic:claude-sonnet-4-6'."""
    provider = PROVIDER_MAP.get(config.llm.provider, config.llm.provider)
    return f"{provider}:{config.llm.model}"


# ---------------------------------------------------------------------------
# Async memory tools
# ---------------------------------------------------------------------------


def create_memory_tools(memory_store: MemoryStore) -> list:
    """Create LangChain tools for memory operations (async)."""

    @tool
    async def recall_memory(query: str, scope: str = "shared") -> str:
        """Search organizational memory for relevant information.

        Args:
            query: What to search for in memory.
            scope: Memory scope - "shared" (org-wide), "channel" (current channel),
                   or "personal" (DM context). Defaults to "shared".
        """
        try:
            mem_scope = MemoryScope(scope)
        except ValueError:
            mem_scope = MemoryScope.SHARED

        entries = memory_store.recall(query, scope=mem_scope, limit=5)
        if not entries:
            return "No relevant memories found."

        results = []
        for e in entries:
            ts = e.created_at.strftime("%Y-%m-%d %H:%M")
            results.append(f"[{ts}] ({e.source or 'unknown'}): {e.content}")
        return "\n---\n".join(results)

    @tool
    async def store_memory(content: str, scope: str = "shared", source: str = "") -> str:
        """Store important information to organizational memory.

        Use this when you learn something important that should be remembered:
        - Decisions made by the team
        - Key facts about projects, people, or processes
        - Action items and commitments

        Args:
            content: The information to remember.
            scope: "shared" (org-wide), "channel" (channel-specific), "personal" (DM-specific).
            source: Where this info came from (e.g., "slack #general", "meeting notes").
        """
        try:
            mem_scope = MemoryScope(scope)
        except ValueError:
            mem_scope = MemoryScope.SHARED

        entry = MemoryEntry(
            content=content,
            scope=mem_scope,
            source=source,
            importance=0.7,
        )
        memory_store.store(entry)
        return f"Stored to {scope} memory."

    return [recall_memory, store_memory]


# ---------------------------------------------------------------------------
# Filesystem tools (async, delegate to backend)
# ---------------------------------------------------------------------------


def create_filesystem_tools(backend_getter) -> list:
    """Create async filesystem tools that route to the sandbox backend.

    Args:
        backend_getter: callable that returns the backend instance.
    """

    @tool
    async def ls(path: str = "/home/user") -> str:
        """List directory contents.

        Args:
            path: Directory path to list. Defaults to /home/user.
        """
        backend = backend_getter()
        entries = await backend.als_info(path)
        if not entries:
            return f"Empty directory or not found: {path}"
        lines = []
        for e in entries:
            marker = "/" if e.is_dir else ""
            size_str = f" ({e.size} bytes)" if e.size is not None else ""
            lines.append(f"  {e.path}{marker}{size_str}")
        return "\n".join(lines)

    @tool
    async def read_file(file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """Read a file with line numbers.

        Args:
            file_path: Absolute path to the file.
            offset: Line offset to start reading from (0-based). Default 0.
            limit: Maximum number of lines to read. Default 2000.
        """
        backend = backend_getter()
        return await backend.aread(file_path, offset, limit)

    @tool
    async def write_file(file_path: str, content: str) -> str:
        """Create or overwrite a file.

        Args:
            file_path: Absolute path for the file.
            content: Full file content to write.
        """
        backend = backend_getter()
        result = await backend.awrite(file_path, content)
        if result.error:
            return f"Error writing {file_path}: {result.error}"
        return f"Wrote {file_path}"

    @tool
    async def edit_file(
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        """Edit a file by replacing a string.

        Args:
            file_path: Absolute path to the file.
            old_string: The exact string to find and replace.
            new_string: The replacement string.
            replace_all: If True, replace all occurrences. Default False.
        """
        backend = backend_getter()
        result = await backend.aedit(file_path, old_string, new_string, replace_all)
        if result.error:
            return f"Edit error: {result.error}"
        return f"Edited {file_path} ({result.occurrences} replacement(s))"

    @tool
    async def glob(pattern: str, path: str = "/home/user") -> str:
        """Find files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "*.py", "**/*.md").
            path: Root directory to search from. Default /home/user.
        """
        backend = backend_getter()
        entries = await backend.aglob_info(pattern, path)
        if not entries:
            return "No files matched."
        return "\n".join(e.path for e in entries)

    @tool
    async def grep(pattern: str, path: str = "/home/user", file_glob: str = "") -> str:
        """Search for a text pattern in files.

        Args:
            pattern: Text pattern to search for.
            path: Directory to search in. Default /home/user.
            file_glob: Optional glob to filter files (e.g., "*.py").
        """
        backend = backend_getter()
        result = await backend.agrep_raw(pattern, path, file_glob or None)
        if isinstance(result, str):
            return result  # error message
        if not result:
            return "No matches found."
        lines = []
        for m in result[:50]:
            lines.append(f"{m.path}:{m.line}: {m.text}")
        return "\n".join(lines)

    @tool
    async def execute(command: str, timeout: int = 120) -> str:
        """Run a shell command in the sandbox.

        Args:
            command: The shell command to execute.
            timeout: Timeout in seconds. Default 120.
        """
        backend = backend_getter()
        result = await backend.aexecute(command, timeout=timeout)
        return result.output

    return [ls, read_file, write_file, edit_file, glob, grep, execute]


# ---------------------------------------------------------------------------
# Skills loader (async)
# ---------------------------------------------------------------------------


async def _load_skills_prompt(store, agent_id: str) -> str:
    """Load skill descriptions from AsyncPostgresStore and format for system prompt."""
    if store is None:
        return ""

    namespace = ("agent", agent_id, "filesystem")
    try:
        items = await store.asearch(namespace, limit=1000)
    except Exception as e:
        logger.warning(f"Failed to load skills from store: {e}")
        return ""

    skills: dict[str, dict] = {}
    for item in items:
        key = item.key
        if not key.startswith("/skills/"):
            continue
        parts = key.split("/")
        if len(parts) < 3:
            continue
        skill_name = parts[2]

        if skill_name not in skills:
            skills[skill_name] = {"name": skill_name, "description": "", "path": ""}

        if key.endswith("/SKILL.md"):
            content_lines = item.value.get("content", [])
            content = (
                "\n".join(content_lines) if isinstance(content_lines, list) else str(content_lines)
            )
            skills[skill_name]["path"] = key

            # Parse YAML frontmatter
            if content.startswith("---"):
                try:
                    import yaml

                    _, frontmatter, _body = content.split("---", 2)
                    meta = yaml.safe_load(frontmatter)
                    if isinstance(meta, dict):
                        skills[skill_name]["description"] = meta.get("description", "")
                except (ValueError, Exception):
                    pass

    if not skills:
        return ""

    lines = ["\n## Available Skills\n"]
    for s in sorted(skills.values(), key=lambda x: x["name"]):
        desc = s.get("description", "")
        lines.append(f"- **{s['name']}**: {desc}" if desc else f"- **{s['name']}**")
        if s.get("path"):
            lines.append(f"  (read {s['path']} for full instructions)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def _build_graph(
    llm,
    tools: list,
    system_prompt: str,
    checkpointer,
    store,
):
    """Build a LangGraph StateGraph with agent + tool nodes.

    Returns a compiled graph that supports ainvoke/astream_events.
    """

    llm_with_tools = llm.bind_tools(tools) if tools else llm

    async def agent_node(state: MessagesState) -> dict:
        """Call the LLM with the current messages."""
        messages = list(state["messages"])

        # Ensure system prompt is first message
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages
        elif isinstance(messages[0], SystemMessage):
            # Update system prompt in case skills changed
            messages = [SystemMessage(content=system_prompt)] + messages[1:]

        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    def should_continue(state: MessagesState) -> str:
        """Route: if the last message has tool calls, go to tools. Otherwise end."""
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")

    return builder.compile(
        checkpointer=checkpointer,
        store=store,
    )


# ---------------------------------------------------------------------------
# OpenInternAgent
# ---------------------------------------------------------------------------


class OpenInternAgent:
    """The main agent that ties LangGraph + Memory + Safety together."""

    def __init__(
        self,
        config: AppConfig,
        agent_id: str = "default",
        sandbox_mode: str = "base",
        e2b_sandbox_id: str = "",
        extra_tools: list | None = None,
    ):
        self.config = config
        self.agent_id = agent_id
        self.sandbox_mode = sandbox_mode  # "none" | "base" | "desktop"
        self.e2b_sandbox_id = e2b_sandbox_id
        self.extra_tools = extra_tools or []
        self.memory_store = MemoryStore(config.database_url, agent_id=agent_id)
        self.safety = SafetyMiddleware(config)
        self.cost_guard = CostGuard(
            database_url=config.database_url,
            agent_id=agent_id,
            daily_budget_usd=config.llm.daily_cost_budget_usd,
            max_actions_per_hour=config.behavior.proactivity.max_actions_per_hour
            if config.behavior.proactivity.enabled
            else 0,
            provider=config.llm.provider,
        )
        self._graph = None
        self._checkpointer = None
        self._store = None
        self._store_ctx = None
        self._e2b_backend = None

    @property
    def is_initialized(self) -> bool:
        """Whether the agent has been fully initialized."""
        return self._graph is not None

    # Keep old name as alias so callers that haven't been updated still work
    @property
    def _agent(self):
        return self._graph

    def initialize_sync(self) -> None:
        """Phase 1 (sync): Initialize memory, LLM, safety, backend.

        Called before the async event loop is running.
        """
        self.memory_store.initialize()
        logger.info("Memory store ready")

        self._llm = _create_llm(self.config)
        logger.info(f"LLM ready: {self.config.llm.provider}:{self.config.llm.model}")

        self._base_system_prompt = build_system_prompt(self.config)
        self._memory_tools = create_memory_tools(self.memory_store)
        self._shell_backend = self._create_shell_backend()

        logger.info(f"Agent '{self.config.identity.name}' sync init complete")

    async def initialize_async(self) -> None:
        """Phase 2 (async): Create async checkpointer, store, compile graph.

        Must be called on the uvicorn event loop.
        """
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg import AsyncConnection
        from psycopg.rows import dict_row

        conn = await AsyncConnection.connect(
            self.config.database_url,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        )
        self._checkpointer = AsyncPostgresSaver(conn)
        await self._checkpointer.setup()
        logger.info("Async checkpointer ready (PostgreSQL)")

        from langgraph.store.postgres import AsyncPostgresStore

        self._store_ctx = AsyncPostgresStore.from_conn_string(self.config.database_url)
        self._store = await self._store_ctx.__aenter__()
        await self._store.setup()
        logger.info("AsyncPostgresStore ready")

        # Seed skills from disk into store
        from scripts.seed_skills import seed_skills_async

        n = await seed_skills_async(self._store, agent_id=self.agent_id)
        if n:
            logger.info(f"Seeded {n} skill file(s) into store")

        # Handle E2B sandbox setup
        if self.sandbox_mode in ("base", "desktop") and self._e2b_backend is not None:
            self._restore_sandbox_from_r2()
            self._seed_skills_to_sandbox()
            # Register reconnect callbacks so data is restored after sandbox expiry
            self._e2b_backend._on_reconnect = [
                self._restore_sandbox_from_r2,
                self._seed_skills_to_sandbox,
            ]
            # Register idle callback — backup to R2 before pausing
            self._e2b_backend._on_idle = [self._backup_sandbox_to_r2]
            logger.info("Backend ready (E2B unified — files + shell in sandbox)")

        # Load skills into system prompt
        skills_prompt = await _load_skills_prompt(self._store, self.agent_id)
        system_prompt = self._base_system_prompt
        if skills_prompt:
            system_prompt += "\n" + skills_prompt

        # Collect all tools
        all_tools = list(self._memory_tools) + list(self.extra_tools)

        # Add filesystem tools if we have a sandbox backend
        if self._e2b_backend is not None:
            backend = self._shell_backend
            fs_tools = create_filesystem_tools(lambda: backend)
            all_tools.extend(fs_tools)

        # Build and compile the graph
        self._graph = _build_graph(
            llm=self._llm,
            tools=all_tools,
            system_prompt=system_prompt,
            checkpointer=self._checkpointer,
            store=self._store,
        )
        logger.info(f"Agent '{self.config.identity.name}' fully initialized (async)")

    def initialize(self) -> None:
        """Legacy sync initialize — for CLI and tests.

        Creates sync PostgresSaver (not async) for contexts without an event loop.
        """
        self.memory_store.initialize()
        logger.info("Memory store ready")

        self._llm = _create_llm(self.config)
        logger.info(f"LLM ready: {self.config.llm.provider}:{self.config.llm.model}")

        system_prompt = build_system_prompt(self.config)

        memory_tools = create_memory_tools(self.memory_store)
        all_tools = memory_tools + self.extra_tools

        # Create sync checkpointer (for CLI usage)
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row

        self._checkpoint_conn = Connection.connect(
            self.config.database_url,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        )
        self._checkpointer = PostgresSaver(self._checkpoint_conn)
        self._checkpointer.setup()
        logger.info("Checkpointer ready (PostgreSQL, sync)")

        # Create sync PostgresStore
        from langgraph.store.postgres import PostgresStore

        self._store_ctx = PostgresStore.from_conn_string(self.config.database_url)
        self._store = self._store_ctx.__enter__()
        self._store.setup()
        logger.info("PostgresStore ready (sync)")

        # Seed skills
        from scripts.seed_skills import seed_skills

        n = seed_skills(self._store, agent_id=self.agent_id)
        if n:
            logger.info(f"Seeded {n} skill file(s) into store")

        # Create backend
        self._shell_backend = self._create_shell_backend()

        if self.sandbox_mode in ("base", "desktop") and self._e2b_backend is not None:
            self._restore_sandbox_from_r2()
            self._seed_skills_to_sandbox()
            # Register reconnect callbacks so data is restored after sandbox expiry
            self._e2b_backend._on_reconnect = [
                self._restore_sandbox_from_r2,
                self._seed_skills_to_sandbox,
            ]
            # Register idle callback — backup to R2 before pausing
            self._e2b_backend._on_idle = [self._backup_sandbox_to_r2]

            backend = self._shell_backend
            fs_tools = create_filesystem_tools(lambda: backend)
            all_tools.extend(fs_tools)
            logger.info("Backend ready (E2B unified)")

        # Build graph (with sync checkpointer — ainvoke still works)
        self._graph = _build_graph(
            llm=self._llm,
            tools=all_tools,
            system_prompt=system_prompt,
            checkpointer=self._checkpointer,
            store=self._store,
        )
        logger.info(f"Agent '{self.config.identity.name}' initialized (sync)")

    def _create_shell_backend(self):
        """Create the shell backend based on sandbox_mode: none | base | desktop."""
        if self.sandbox_mode in ("base", "desktop"):
            try:
                api_key = os.environ.get("E2B_API_KEY", "")
                if not api_key:
                    logger.error(
                        f"E2B sandbox ({self.sandbox_mode}) enabled for agent "
                        f"{self.agent_id} but E2B_API_KEY not set. "
                        "Continuing without sandbox — file/shell tools disabled."
                    )
                elif self.sandbox_mode == "desktop":
                    from core.e2b_desktop_backend import E2BDesktopBackend

                    backend = E2BDesktopBackend(
                        agent_id=self.agent_id,
                        api_key=api_key,
                        sandbox_id=self.e2b_sandbox_id or None,
                    )
                    self._e2b_backend = backend
                    logger.info(f"E2B Desktop sandbox configured (lazy) for agent: {self.agent_id}")
                    return backend
                else:
                    from core.e2b_backend import E2BSandboxBackend

                    backend = E2BSandboxBackend(
                        agent_id=self.agent_id,
                        api_key=api_key,
                        sandbox_id=self.e2b_sandbox_id or None,
                    )
                    self._e2b_backend = backend
                    logger.info(f"E2B sandbox configured (lazy) for agent: {self.agent_id}")
                    return backend
            except ImportError as exc:
                pkg = "e2b-desktop" if self.sandbox_mode == "desktop" else "e2b"
                logger.warning(
                    f"{pkg} package not installed — file/shell tools disabled. "
                    f"Install with: pip install {pkg}"
                )
                logger.debug("Import error details: %s", exc)
            except Exception as e:
                logger.error(f"E2B sandbox failed: {e}. Continuing without sandbox.")

        # No shell backend for non-sandbox mode
        return None

    _MAX_SKILL_FILE_SIZE = 1_000_000  # 1 MB

    def _seed_skills_to_sandbox(self) -> None:
        """Copy skill files from disk into the E2B sandbox filesystem."""
        if self._e2b_backend is None:
            return

        skills_dir = Path(__file__).resolve().parent.parent / "skills"
        if not skills_dir.exists():
            logger.warning(f"Skills directory not found: {skills_dir}")
            return

        files_to_upload: list[tuple[str, bytes]] = []
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith((".", "_")):
                continue
            for file_path in sorted(skill_dir.rglob("*")):
                if not file_path.is_file() or file_path.stat().st_size > self._MAX_SKILL_FILE_SIZE:
                    continue
                relative = file_path.relative_to(skills_dir)
                sandbox_path = f"/home/user/skills/{relative.as_posix()}"
                content = file_path.read_bytes()
                files_to_upload.append((sandbox_path, content))

        if files_to_upload:
            self._e2b_backend.execute("mkdir -p /home/user/skills")
            self._e2b_backend.upload_files(files_to_upload)
            logger.info(f"Seeded {len(files_to_upload)} skill file(s) into E2B sandbox")

    def _backup_sandbox_to_r2(self) -> None:
        """Backup sandbox files to R2 (called before idle pause)."""
        if self._e2b_backend is None:
            return
        try:
            from core.r2_storage import R2Storage

            r2 = R2Storage(self.config)
            if not r2.enabled:
                return
            key = self._e2b_backend.backup_to_r2(r2)
            if key:
                logger.info(f"Backed up sandbox to R2 for agent {self.agent_id}: {key}")
            else:
                logger.warning(f"R2 backup returned no key for agent {self.agent_id}")
        except Exception as e:
            logger.warning(f"R2 backup failed (non-fatal): {e}")

    def _restore_sandbox_from_r2(self) -> None:
        """Restore files from R2 backup into the E2B sandbox."""
        if self._e2b_backend is None:
            return
        try:
            from core.r2_storage import R2Storage

            r2 = R2Storage(self.config)
            if not r2.enabled:
                return
            restored = self._e2b_backend.restore_from_r2(r2)
            if restored:
                logger.info(f"Restored sandbox from R2 backup for agent {self.agent_id}")
        except Exception as e:
            logger.warning(f"R2 restore failed (non-fatal): {e}")

    @staticmethod
    def _enrich_message(message: str, context: dict) -> str:
        """Prepend platform context to a user message."""
        if context.get("channel_id") and context.get("platform") != "web":
            return (
                f"[Context: channel={context.get('channel_id', '')}, "
                f"user_id={context.get('user_id', '')}, "
                f"user_name={context.get('user_name', 'unknown')}, "
                f"platform={context.get('platform', 'unknown')}]\n\n"
                f"{message}"
            )
        return message

    async def chat(
        self,
        message: str,
        context: ChatContext | None = None,
        thread_id: str | None = None,
    ) -> tuple[str, TokenUsage]:
        """Send a message to the agent and get a response.

        Uses native ainvoke — no thread pool blocking.
        """
        if self._graph is None:
            raise AgentNotInitializedError(self.agent_id)

        context = context or {}

        # Cost guard check
        try:
            self.cost_guard.check()
        except BudgetExceededError:
            return (
                "I've reached my daily budget limit. Please try again tomorrow "
                "or ask an admin to increase the budget.",
                TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            )
        except RateLimitExceededError:
            return (
                "I'm receiving too many requests right now. Please try again in a few minutes.",
                TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            )

        # Safety check
        action_type = "respond_to_dm" if context.get("is_dm") else "respond_to_mention"
        verdict = self.safety.check(
            action_type,
            description=f"Responding to message in {context.get('channel_id', 'unknown')}",
            user_id=context.get("user_id", ""),
        )
        if verdict == ActionVerdict.DENY:
            return "I'm not allowed to respond in this context.", TokenUsage(
                input_tokens=0, output_tokens=0, total_tokens=0
            )

        enriched_message = self._enrich_message(message, context)

        invoke_config = {}
        if thread_id:
            invoke_config = {"configurable": {"thread_id": thread_id}}

        # Context compaction
        if thread_id:
            await self._maybe_compact(invoke_config)

        # Native async invoke — no asyncio.to_thread
        result = await self._graph.ainvoke(
            {"messages": [{"role": "user", "content": enriched_message}]},
            invoke_config,
        )

        response = self._extract_response(result)
        token_usage = self._extract_token_usage(result)
        self._store_conversation(message, response, context)

        return response, token_usage

    async def chat_stream(
        self,
        message: str,
        context: ChatContext | None = None,
        thread_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream a response token-by-token via astream_events.

        Yields dicts with:
          {"type": "token", "content": "..."}   — incremental text chunk
          {"type": "done", "content": "...", "token_usage": {...}}  — final result
        """
        if self._graph is None:
            raise AgentNotInitializedError(self.agent_id)

        context = context or {}

        # Cost guard check
        try:
            self.cost_guard.check()
        except BudgetExceededError:
            yield {
                "type": "done",
                "content": "I've reached my daily budget limit. Please try again tomorrow "
                "or ask an admin to increase the budget.",
                "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            }
            return
        except RateLimitExceededError:
            yield {
                "type": "done",
                "content": "I'm receiving too many requests right now. "
                "Please try again in a few minutes.",
                "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            }
            return

        # Safety check
        action_type = "respond_to_dm" if context.get("is_dm") else "respond_to_mention"
        verdict = self.safety.check(
            action_type,
            description=f"Responding to message in {context.get('channel_id', 'unknown')}",
            user_id=context.get("user_id", ""),
        )
        if verdict == ActionVerdict.DENY:
            yield {
                "type": "done",
                "content": "I'm not allowed to respond in this context.",
                "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            }
            return

        enriched_message = self._enrich_message(message, context)

        invoke_config = {}
        if thread_id:
            invoke_config = {"configurable": {"thread_id": thread_id}}

        if thread_id:
            await self._maybe_compact(invoke_config)

        input_data = {"messages": [{"role": "user", "content": enriched_message}]}
        full_text = ""

        try:
            async for event in self._graph.astream_events(input_data, invoke_config, version="v2"):
                kind = event.get("event", "")
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk is not None:
                        token_text = ""
                        if hasattr(chunk, "content"):
                            content = chunk.content
                            if isinstance(content, str):
                                token_text = content
                            elif isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        token_text += block.get("text", "")
                                    elif isinstance(block, str):
                                        token_text += block
                        if token_text:
                            full_text += token_text
                            yield {"type": "token", "content": token_text}
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    yield {"type": "status", "tool": tool_name, "status": "running"}
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    yield {"type": "status", "tool": tool_name, "status": "done"}

        except Exception:
            logger.warning("astream_events failed, falling back to non-streaming chat()")
            response, token_usage = await self.chat(message, context, thread_id)
            yield {"type": "done", "content": response, "token_usage": dict(token_usage)}
            return

        # Get final state — native async
        try:
            final_state = await self._graph.aget_state(invoke_config)
        except Exception:
            logger.warning("aget_state failed, skipping token usage")
            final_state = None

        result = {"messages": final_state.values.get("messages", [])} if final_state else {}
        token_usage = self._extract_token_usage(result)

        if not full_text:
            full_text = self._extract_response(result)

        self._store_conversation(message, full_text, context)

        yield {
            "type": "done",
            "content": full_text,
            "token_usage": dict(token_usage),
        }

    async def _maybe_compact(self, invoke_config: dict) -> None:
        """Check if conversation needs compaction and perform it if so."""
        import asyncio

        thread_id = invoke_config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return

        if not hasattr(self, "_compaction_locks"):
            self._compaction_locks: dict[str, asyncio.Lock] = {}
        if thread_id not in self._compaction_locks:
            self._compaction_locks[thread_id] = asyncio.Lock()

        if self._compaction_locks[thread_id].locked():
            return

        async with self._compaction_locks[thread_id]:
            await self._do_compact(invoke_config)

    async def _do_compact(self, invoke_config: dict) -> None:
        """Perform the actual compaction (called under lock). Native async."""
        try:
            # Native async state retrieval
            state = await self._graph.aget_state(invoke_config)
            if not state or not state.values:
                return

            messages = state.values.get("messages", [])
            if not needs_compaction({"messages": messages}):
                return

            logger.info(
                f"Compacting conversation ({len(messages)} messages) "
                f"for thread {invoke_config['configurable']['thread_id']}"
            )

            new_messages, summary = await compact_context(self._llm, messages)

            if summary:
                self.memory_store.store(
                    MemoryEntry(
                        content=f"[Conversation summary]: {summary}",
                        scope=MemoryScope.SHARED,
                        source="context_compaction",
                        importance=0.8,
                    )
                )

            # Native async state update
            await self._graph.aupdate_state(
                invoke_config,
                {"messages": new_messages},
            )
            logger.info(f"Compaction complete: {len(messages)} -> {len(new_messages)} messages")

        except Exception as e:
            self._compaction_failures = getattr(self, "_compaction_failures", 0) + 1
            if self._compaction_failures % 10 == 0:
                logger.error(
                    f"Context compaction failing consistently ({self._compaction_failures}x): {e}"
                )
            else:
                logger.warning(f"Context compaction failed (non-fatal): {e}")

    def _extract_response(self, result: Any) -> str:
        """Extract the final text response from agent result."""
        if isinstance(result, dict) and "messages" in result:
            messages = result["messages"]
            for msg in reversed(messages):
                if hasattr(msg, "content") and msg.content:
                    if hasattr(msg, "type") and msg.type == "ai":
                        return self._extract_text_content(msg.content)
                elif isinstance(msg, dict) and msg.get("role") == "assistant":
                    return self._extract_text_content(msg.get("content", ""))
            if messages:
                last = messages[-1]
                if hasattr(last, "content"):
                    return self._extract_text_content(last.content)
                if isinstance(last, dict):
                    return self._extract_text_content(last.get("content", ""))
        if isinstance(result, str):
            return result
        return str(result)

    @staticmethod
    def _extract_text_content(content: Any) -> str:
        """Extract plain text from content that may be a list of blocks."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        continue
                    elif block.get("type") == "thinking":
                        continue
                elif isinstance(block, str):
                    text_parts.append(block)
            return "\n".join(text_parts) if text_parts else str(content)
        return str(content)

    @staticmethod
    def _extract_token_usage(result: Any) -> TokenUsage:
        """Extract total token usage from all AI messages in the result."""
        input_tokens = 0
        output_tokens = 0
        if isinstance(result, dict) and "messages" in result:
            for msg in result["messages"]:
                usage = getattr(msg, "usage_metadata", None)
                if usage:
                    input_tokens += usage.get("input_tokens", 0)
                    output_tokens += usage.get("output_tokens", 0)
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

    def _store_conversation(self, user_message: str, response: str, context: ChatContext) -> None:
        """Store the conversation turn to memory."""
        scope = MemoryScope.PERSONAL if context.get("is_dm") else MemoryScope.CHANNEL
        scope_id = context.get("channel_id", "")

        self.memory_store.store(
            MemoryEntry(
                content=f"[{context.get('user_name', 'user')}]: {user_message}",
                scope=scope,
                scope_id=scope_id,
                source=f"{context.get('platform', 'chat')} message",
            )
        )

        self.memory_store.store(
            MemoryEntry(
                content=f"[{self.config.identity.name}]: {response}",
                scope=scope,
                scope_id=scope_id,
                source=f"{context.get('platform', 'chat')} response",
            )
        )
