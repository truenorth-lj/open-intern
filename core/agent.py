"""Core agent — wraps Deep Agents with open_intern's memory, safety, and identity."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.tools import tool

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
        # Anthropic-compatible providers (MiniMax, etc.)
        # Set env vars so deepagents subagents also use the correct endpoint
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
        # Native LangChain providers (Claude, OpenAI, Ollama)
        model_string = _resolve_model_string(config)
        kwargs: dict = {"temperature": config.llm.temperature}
        if config.llm.api_key:
            kwargs["api_key"] = config.llm.api_key
        return init_chat_model(model_string, **kwargs)


def _resolve_model_string(config: AppConfig) -> str:
    """Convert config to init_chat_model format like 'anthropic:claude-sonnet-4-6'."""
    provider = PROVIDER_MAP.get(config.llm.provider, config.llm.provider)
    return f"{provider}:{config.llm.model}"


def create_memory_tools(memory_store: MemoryStore) -> list:
    """Create LangChain tools for memory operations."""

    @tool
    def recall_memory(query: str, scope: str = "shared") -> str:
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
    def store_memory(content: str, scope: str = "shared", source: str = "") -> str:
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


class OpenInternAgent:
    """The main agent that ties Deep Agents + Memory + Safety together."""

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
        self._agent = None
        self._checkpointer = None
        self._store_ctx = None
        self._postgres_store = None
        self._e2b_backend = None

    @property
    def is_initialized(self) -> bool:
        """Whether the agent has been fully initialized."""
        return self._agent is not None

    def initialize(self) -> None:
        """Initialize all subsystems and create the Deep Agent."""
        # Initialize memory
        self.memory_store.initialize()
        logger.info("Memory store ready")

        # Create LLM
        llm = _create_llm(self.config)
        logger.info(f"LLM ready: {self.config.llm.provider}:{self.config.llm.model}")

        # Build system prompt with identity
        system_prompt = build_system_prompt(self.config)

        # Create memory tools + any extra tools (e.g., scheduler)
        memory_tools = create_memory_tools(self.memory_store)
        all_tools = memory_tools + self.extra_tools

        # Create checkpointer for conversation threading (persisted to PostgreSQL)
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
        logger.info("Checkpointer ready (PostgreSQL)")

        # Create PostgresStore for persistent file storage
        from langgraph.store.postgres import PostgresStore

        self._store_ctx = PostgresStore.from_conn_string(self.config.database_url)
        self._postgres_store = self._store_ctx.__enter__()
        self._postgres_store.setup()
        logger.info("PostgresStore ready")

        # Seed skills from disk into PostgresStore
        from scripts.seed_skills import seed_skills

        n = seed_skills(self._postgres_store, agent_id=self.agent_id)
        if n:
            logger.info(f"Seeded {n} skill file(s) into store")

        # Create backend: CompositeBackend
        # - Files (read/write/edit/grep/glob) → StoreBackend → PostgreSQL (persistent)
        # - Shell execution (execute) → E2B sandbox or LocalShellBackend
        from deepagents.backends.composite import CompositeBackend
        from deepagents.backends.store import StoreBackend

        shell_backend = self._create_shell_backend()

        _agent_id = self.agent_id

        def _backend_factory(rt):
            return CompositeBackend(
                default=shell_backend,
                routes={
                    "/": StoreBackend(
                        rt,
                        namespace=lambda ctx: ("agent", _agent_id, "filesystem"),
                    ),
                },
            )

        logger.info("Backend ready (CompositeBackend: StoreBackend + LocalShellBackend)")

        # Create the Deep Agent
        from deepagents import create_deep_agent

        self._agent = create_deep_agent(
            model=llm,
            tools=all_tools,
            system_prompt=system_prompt,
            checkpointer=self._checkpointer,
            store=self._postgres_store,
            backend=_backend_factory,
            skills=["/skills/"],
        )
        logger.info(f"Agent '{self.config.identity.name}' initialized")

    def _create_shell_backend(self):
        """Create the shell backend based on sandbox_mode: none | base | desktop."""
        if self.sandbox_mode in ("base", "desktop"):
            try:
                api_key = os.environ.get("E2B_API_KEY", "")
                if not api_key:
                    logger.warning(
                        f"E2B sandbox ({self.sandbox_mode}) enabled for agent "
                        f"{self.agent_id} but E2B_API_KEY not set. "
                        "Falling back to local shell."
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
                    f"{pkg} package not installed. Falling back to local shell. "
                    f"Install with: pip install {pkg}"
                )
                logger.debug("Import error details: %s", exc)
            except Exception as e:
                logger.error(f"E2B sandbox failed: {e}. Falling back to local shell.")

        # Fallback: local shell backend
        from deepagents.backends.local_shell import LocalShellBackend

        workspace_dir = Path(f"/tmp/open_intern_workspace/{self.agent_id}")
        workspace_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using local shell backend (agent: {self.agent_id})")
        return LocalShellBackend(
            root_dir=workspace_dir,
            virtual_mode=True,
            inherit_env=True,
        )

    async def chat(
        self, message: str, context: ChatContext | None = None, thread_id: str | None = None
    ) -> tuple[str, TokenUsage]:
        """Send a message to the agent and get a response.

        Args:
            message: The user message.
            context: Optional context (channel_id, user_id, platform, etc.)
            thread_id: Optional thread ID for conversation continuity.

        Returns:
            Tuple of (response text, token usage).
        """
        if self._agent is None:
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

        # Build context-aware message
        enriched_message = message
        if context.get("channel_id") and context.get("platform") != "web":
            enriched_message = (
                f"[Context: channel={context.get('channel_id', '')}, "
                f"user={context.get('user_name', 'unknown')}, "
                f"platform={context.get('platform', 'unknown')}]\n\n"
                f"{message}"
            )

        # Build invoke config with thread_id for conversation continuity
        invoke_config = {}
        if thread_id:
            invoke_config = {"configurable": {"thread_id": thread_id}}

        # Context compaction: check if we need to summarize old messages
        if thread_id:
            await self._maybe_compact(invoke_config)

        # Invoke the agent in a thread pool (checkpointer doesn't support async)
        import asyncio

        result = await asyncio.to_thread(
            self._agent.invoke,
            {"messages": [{"role": "user", "content": enriched_message}]},
            invoke_config,
        )

        # Extract response text
        response = self._extract_response(result)

        # Extract token usage from result
        token_usage = self._extract_token_usage(result)

        # Store conversation to memory
        self._store_conversation(message, response, context)

        return response, token_usage

    async def chat_stream(
        self, message: str, context: ChatContext | None = None, thread_id: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream a response token-by-token via astream_events.

        Yields dicts with:
          {"type": "token", "content": "..."}   — incremental text chunk
          {"type": "done", "content": "...", "token_usage": {...}}  — final result

        Falls back to non-streaming chat() if astream_events is unavailable.
        """
        if self._agent is None:
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

        # Safety check (same as chat())
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

        # Build context-aware message
        enriched_message = message
        if context.get("channel_id") and context.get("platform") != "web":
            enriched_message = (
                f"[Context: channel={context.get('channel_id', '')}, "
                f"user={context.get('user_name', 'unknown')}, "
                f"platform={context.get('platform', 'unknown')}]\n\n"
                f"{message}"
            )

        invoke_config = {}
        if thread_id:
            invoke_config = {"configurable": {"thread_id": thread_id}}

        # Context compaction
        if thread_id:
            await self._maybe_compact(invoke_config)

        input_data = {"messages": [{"role": "user", "content": enriched_message}]}
        full_text = ""

        try:
            async for event in self._agent.astream_events(input_data, invoke_config, version="v2"):
                kind = event.get("event", "")
                # on_chat_model_stream emits individual tokens from the LLM
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
            # Fallback: use non-streaming chat()
            logger.warning("astream_events failed, falling back to non-streaming chat()")
            response, token_usage = await self.chat(message, context, thread_id)
            yield {"type": "done", "content": response, "token_usage": dict(token_usage)}
            return

        # Get final state for token usage
        import asyncio

        try:
            final_state = await asyncio.wait_for(
                asyncio.to_thread(self._agent.get_state, invoke_config),
                timeout=30.0,
            )
        except TimeoutError:
            logger.warning("get_state timed out after 30s, skipping token usage")
            final_state = None
        # Extract token usage from the final messages
        result = {"messages": final_state.values.get("messages", [])} if final_state else {}
        token_usage = self._extract_token_usage(result)

        # If no tokens were streamed, extract from final state
        if not full_text:
            full_text = self._extract_response(result)

        # Store conversation to memory
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

        # Per-thread lock to prevent concurrent compaction
        if not hasattr(self, "_compaction_locks"):
            self._compaction_locks: dict[str, asyncio.Lock] = {}
        if thread_id not in self._compaction_locks:
            self._compaction_locks[thread_id] = asyncio.Lock()

        if self._compaction_locks[thread_id].locked():
            return  # Another compaction in progress for this thread

        async with self._compaction_locks[thread_id]:
            await self._do_compact(invoke_config)

    async def _do_compact(self, invoke_config: dict) -> None:
        """Perform the actual compaction (called under lock)."""
        import asyncio

        try:
            state = await asyncio.to_thread(self._agent.get_state, invoke_config)
            if not state or not state.values:
                return

            messages = state.values.get("messages", [])
            if not needs_compaction({"messages": messages}):
                return

            logger.info(
                f"Compacting conversation ({len(messages)} messages) "
                f"for thread {invoke_config['configurable']['thread_id']}"
            )

            llm = _create_llm(self.config)
            new_messages, summary = await compact_context(llm, messages)

            # Store the summary to memory for long-term recall
            if summary:
                self.memory_store.store(
                    MemoryEntry(
                        content=f"[Conversation summary]: {summary}",
                        scope=MemoryScope.SHARED,
                        source="context_compaction",
                        importance=0.8,
                    )
                )

            # Update the checkpoint with compacted messages
            await asyncio.to_thread(
                self._agent.update_state,
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
            # Find the last AI message
            for msg in reversed(messages):
                if hasattr(msg, "content") and msg.content:
                    if hasattr(msg, "type") and msg.type == "ai":
                        return self._extract_text_content(msg.content)
                elif isinstance(msg, dict) and msg.get("role") == "assistant":
                    return self._extract_text_content(msg.get("content", ""))
            # Fallback: last message content
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
        """Extract plain text from content that may be a list of blocks (MiniMax/Anthropic format).

        Handles both plain strings and list-of-dicts format like:
        [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "Hello!"}]
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        continue  # skip tool calls
                    elif block.get("type") == "thinking":
                        continue  # skip thinking blocks
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

        # Store user message
        self.memory_store.store(
            MemoryEntry(
                content=f"[{context.get('user_name', 'user')}]: {user_message}",
                scope=scope,
                scope_id=scope_id,
                source=f"{context.get('platform', 'chat')} message",
            )
        )

        # Store agent response
        self.memory_store.store(
            MemoryEntry(
                content=f"[{self.config.identity.name}]: {response}",
                scope=scope,
                scope_id=scope_id,
                source=f"{context.get('platform', 'chat')} response",
            )
        )
