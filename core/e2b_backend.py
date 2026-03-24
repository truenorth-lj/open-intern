"""E2B sandbox backend — runs agent shell commands in isolated cloud microVMs."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from dataclasses import dataclass

from core.backend_types import (
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    SandboxBackendProtocol,
    WriteResult,
)

logger = logging.getLogger(__name__)

# Maximum output bytes before truncation
MAX_OUTPUT_BYTES = 100_000


@dataclass
class E2BSandboxInfo:
    """Tracks sandbox state for an agent."""

    sandbox_id: str
    agent_id: str


class E2BSandboxBackend(SandboxBackendProtocol):
    """Backend that executes commands and file ops in an E2B cloud sandbox.

    Each agent gets its own isolated Firecracker microVM via E2B.
    Supports pause/resume for cost optimization.
    """

    def __init__(
        self,
        agent_id: str,
        *,
        template: str = "base",
        timeout: int = 3600,
        api_key: str | None = None,
        sandbox_id: str | None = None,
    ):
        self._agent_id = agent_id
        self._template = template
        self._default_timeout = timeout
        self._api_key = api_key
        self._sandbox = None
        self._existing_sandbox_id = sandbox_id
        self._reconnecting = False  # guard against infinite reconnect loops
        self._on_reconnect: list = []  # callbacks invoked after reconnect
        self._on_idle: list = []  # callbacks invoked before idle pause (e.g. R2 backup)
        self._idle_timeout_secs = 300  # pause after 5 min idle
        self._idle_timer: threading.Timer | None = None
        self._idle_lock = threading.Lock()
        self._pausing = False  # guard: don't reset timer during pause

    @property
    def id(self) -> str:
        if self._sandbox:
            return self._sandbox.sandbox_id
        return self._existing_sandbox_id or f"e2b-{self._agent_id}-pending"

    def connect(self) -> None:
        """Create or resume an E2B sandbox."""
        from e2b import Sandbox

        kwargs = {}
        if self._api_key:
            kwargs["api_key"] = self._api_key

        if self._existing_sandbox_id:
            try:
                self._sandbox = Sandbox.connect(self._existing_sandbox_id, **kwargs)
                logger.info(
                    f"Reconnected to E2B sandbox {self._existing_sandbox_id} "
                    f"for agent {self._agent_id}"
                )
                return
            except Exception as e:
                error_msg = str(e).lower()
                if "not found" in error_msg or "does not exist" in error_msg:
                    # Sandbox is permanently gone — clear stale ID
                    logger.warning(
                        f"Sandbox {self._existing_sandbox_id} no longer exists, "
                        f"clearing stale ID for agent {self._agent_id}"
                    )
                    self._existing_sandbox_id = None
                else:
                    # Possibly transient error — keep ID for future retry
                    logger.warning(
                        f"Could not reconnect to sandbox {self._existing_sandbox_id} "
                        f"({e}), creating new one but keeping ID"
                    )

        self._sandbox = Sandbox.create(
            template=self._template,
            timeout=self._default_timeout,
            metadata={"agent_id": self._agent_id},
            **kwargs,
        )
        logger.info(f"Created E2B sandbox {self._sandbox.sandbox_id} for agent {self._agent_id}")

    # Errors that indicate the sandbox VM is dead and needs reconnection
    _DEAD_SANDBOX_MARKERS = (
        "not found",
        "does not exist",
        "sandbox is not running",
        "sandbox is paused",
        "connection refused",
        "502",
        "503",
        "504",
    )

    def _is_sandbox_dead(self, error: Exception) -> bool:
        """Check if an error indicates the sandbox VM is gone or unresponsive."""
        if self._reconnecting:
            return False  # already reconnecting, don't recurse
        msg = str(error).lower()
        return any(marker in msg for marker in self._DEAD_SANDBOX_MARKERS)

    def _ensure_sandbox(self):
        if self._sandbox is None:
            self.connect()
            logger.info(f"E2B sandbox connected (lazy): {self._sandbox.sandbox_id}")
        self._reset_idle_timer()
        return self._sandbox

    # --- Idle auto-pause ---

    def _reset_idle_timer(self) -> None:
        """Reset the idle timer. Called on every sandbox access."""
        with self._idle_lock:
            if self._pausing:
                return  # don't reset while mid-pause
            if self._idle_timer is not None:
                self._idle_timer.cancel()
            self._idle_timer = threading.Timer(self._idle_timeout_secs, self._idle_pause)
            self._idle_timer.daemon = True
            self._idle_timer.start()

    def _idle_pause(self) -> None:
        """Called when sandbox has been idle — backup and pause to save costs."""
        try:
            with self._idle_lock:
                self._idle_timer = None
                if self._sandbox is None:
                    return
                self._pausing = True

            logger.info(
                f"Sandbox {self._sandbox.sandbox_id} idle for "
                f"{self._idle_timeout_secs}s, backing up and pausing..."
            )

            # Run pre-pause callbacks (e.g. R2 backup)
            for cb in self._on_idle:
                try:
                    cb()
                except Exception as exc:
                    logger.warning(f"Idle callback failed: {exc}")

            # Pause sandbox (preserves state, stops billing)
            sandbox_id = self.pause()
            if sandbox_id:
                self._existing_sandbox_id = sandbox_id
                logger.info(f"Sandbox paused after idle: {sandbox_id} for agent {self._agent_id}")
            else:
                # Pause failed — sandbox may be dead already
                self._existing_sandbox_id = None
                logger.warning(
                    f"Failed to pause sandbox for agent {self._agent_id}, "
                    "will create new on next use"
                )
            self._sandbox = None
        except Exception as e:
            logger.error(f"Idle pause failed for agent {self._agent_id}: {e}")
        finally:
            with self._idle_lock:
                self._pausing = False

    def _reconnect_sandbox(self) -> None:
        """Force-reconnect by clearing stale sandbox and creating a new one."""
        old_id = self._sandbox.sandbox_id if self._sandbox else self._existing_sandbox_id
        logger.warning(f"Sandbox {old_id} is dead for agent {self._agent_id}, reconnecting...")
        self._reconnecting = True
        try:
            self._sandbox = None
            self._existing_sandbox_id = None
            self.connect()
            logger.info(
                f"Reconnected to new sandbox {self._sandbox.sandbox_id} for agent {self._agent_id}"
            )
            # Run post-reconnect hooks (e.g. R2 restore, skill seeding)
            for cb in self._on_reconnect:
                try:
                    cb()
                except Exception as exc:
                    logger.warning(f"Reconnect callback failed: {exc}")
        finally:
            self._reconnecting = False

    # --- Execute ---

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        sbx = self._ensure_sandbox()
        effective_timeout = timeout or self._default_timeout
        try:
            result = sbx.commands.run(command, timeout=effective_timeout)
            stdout = result.stdout or ""
            stderr = result.stderr or ""

            parts = []
            if stdout:
                parts.append(stdout)
            if stderr:
                parts.append("\n".join(f"[stderr] {line}" for line in stderr.splitlines()))

            output = "\n".join(parts) if parts else "<no output>"
            truncated = len(output.encode()) > MAX_OUTPUT_BYTES
            if truncated:
                output = output[:MAX_OUTPUT_BYTES] + "\n... (output truncated)"

            exit_code = result.exit_code

            if exit_code and exit_code != 0:
                output += f"\n\nExit code: {exit_code}"

            return ExecuteResponse(output=output, exit_code=exit_code, truncated=truncated)
        except Exception as e:
            if self._is_sandbox_dead(e):
                self._reconnect_sandbox()
                return self.execute(command, timeout=timeout)
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                return ExecuteResponse(
                    output=f"Command timed out after {effective_timeout}s",
                    exit_code=124,
                )
            return ExecuteResponse(output=f"Execution error: {error_msg}", exit_code=1)

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return await asyncio.to_thread(self.execute, command, timeout=timeout)

    # --- File operations ---

    def ls_info(self, path: str) -> list[FileInfo]:
        sbx = self._ensure_sandbox()
        try:
            entries = sbx.files.list(path)
            return [
                FileInfo(
                    path=f"{path.rstrip('/')}/{e.name}",
                    is_dir=e.type == "dir",
                    size=getattr(e, "size", None),
                )
                for e in entries
            ]
        except Exception as e:
            if self._is_sandbox_dead(e):
                self._reconnect_sandbox()
                return self.ls_info(path)
            logger.warning(f"E2B ls_info error: {e}")
            return []

    async def als_info(self, path: str) -> list[FileInfo]:
        return await asyncio.to_thread(self.ls_info, path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        sbx = self._ensure_sandbox()
        try:
            content = sbx.files.read(file_path)
            lines = content.splitlines()
            # Apply offset/limit (1-indexed for display)
            selected = lines[offset : offset + limit]
            # Format with line numbers (cat -n style)
            numbered = []
            for i, line in enumerate(selected, start=offset + 1):
                numbered.append(f"{i:>6}\t{line}")
            return "\n".join(numbered)
        except Exception as e:
            if self._is_sandbox_dead(e):
                self._reconnect_sandbox()
                return self.read(file_path, offset, limit)
            return f"Error reading {file_path}: {e}"

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        return await asyncio.to_thread(self.read, file_path, offset, limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        sbx = self._ensure_sandbox()
        try:
            sbx.files.write(file_path, content)
            return WriteResult(path=file_path)
        except Exception as e:
            if self._is_sandbox_dead(e):
                self._reconnect_sandbox()
                return self.write(file_path, content)
            return WriteResult(error=str(e))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return await asyncio.to_thread(self.write, file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        sbx = self._ensure_sandbox()
        try:
            content = sbx.files.read(file_path)
            if old_string not in content:
                return EditResult(error=f"String not found in {file_path}")

            if replace_all:
                count = content.count(old_string)
                new_content = content.replace(old_string, new_string)
            else:
                if content.count(old_string) > 1:
                    return EditResult(
                        error=f"Multiple occurrences found in {file_path}. "
                        "Use replace_all=True or provide more context."
                    )
                count = 1
                new_content = content.replace(old_string, new_string, 1)

            sbx.files.write(file_path, new_content)
            return EditResult(path=file_path, occurrences=count)
        except Exception as e:
            if self._is_sandbox_dead(e):
                self._reconnect_sandbox()
                return self.edit(file_path, old_string, new_string, replace_all)
            return EditResult(error=str(e))

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return await asyncio.to_thread(self.edit, file_path, old_string, new_string, replace_all)

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        sbx = self._ensure_sandbox()
        try:
            # Build grep command with proper shell escaping
            import shlex

            cmd_parts = ["grep", "-rn"]
            if glob:
                cmd_parts.extend(["--include", shlex.quote(glob)])
            cmd_parts.extend(["--", shlex.quote(pattern)])
            cmd_parts.append(shlex.quote(path or "/home/user"))

            result = sbx.commands.run(" ".join(cmd_parts), timeout=30)
            stdout = result.stdout or ""
            if not stdout.strip():
                return []

            matches = []
            for line in stdout.splitlines()[:100]:  # limit results
                # Format: path:line:text
                m = re.match(r"^(.+?):(\d+):(.*)$", line)
                if m:
                    matches.append(
                        GrepMatch(path=m.group(1), line=int(m.group(2)), text=m.group(3))
                    )
            return matches
        except Exception as e:
            if self._is_sandbox_dead(e):
                self._reconnect_sandbox()
                return self.grep_raw(pattern, path, glob)
            return f"Grep error: {e}"

    async def agrep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        return await asyncio.to_thread(self.grep_raw, pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        sbx = self._ensure_sandbox()
        try:
            import shlex

            result = sbx.commands.run(
                f"find {shlex.quote(path)} -path {shlex.quote(pattern)} -type f",
                timeout=15,
            )
            stdout = result.stdout or ""
            return [
                FileInfo(path=p.strip(), is_dir=False) for p in stdout.splitlines() if p.strip()
            ][:100]  # limit results
        except Exception as e:
            if self._is_sandbox_dead(e):
                self._reconnect_sandbox()
                return self.glob_info(pattern, path)
            return []

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        return await asyncio.to_thread(self.glob_info, pattern, path)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        sbx = self._ensure_sandbox()
        results = []
        for file_path, content in files:
            try:
                sbx.files.write(file_path, content)
                results.append(FileUploadResponse(path=file_path, error=None))
            except Exception:
                results.append(FileUploadResponse(path=file_path, error="permission_denied"))
        return results

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return await asyncio.to_thread(self.upload_files, files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        sbx = self._ensure_sandbox()
        results = []
        for file_path in paths:
            try:
                content = sbx.files.read(file_path, format="bytes")
                results.append(FileDownloadResponse(path=file_path, content=content, error=None))
            except Exception:
                results.append(
                    FileDownloadResponse(path=file_path, content=None, error="file_not_found")
                )
        return results

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return await asyncio.to_thread(self.download_files, paths)

    # --- R2 Backup/Restore ---

    def backup_to_r2(self, r2) -> str | None:
        """Tar /home/user and upload to R2. Returns backup key or None on failure."""
        from core.r2_storage import R2Storage

        if not isinstance(r2, R2Storage) or not r2.enabled:
            return None

        sbx = self._ensure_sandbox()
        try:
            # Tar user's home directory (excluding caches)
            tar_result = sbx.commands.run(
                "tar czf /tmp/sandbox_backup.tar.gz "
                "--exclude='__pycache__' --exclude='.cache' "
                "--exclude='node_modules' --exclude='.venv/lib' "
                "-C /home/user .",
                timeout=120,
            )
            if tar_result.exit_code != 0:
                logger.warning(f"Tar failed: {tar_result.stderr}")
                return None

            # Capture pip packages
            pip_result = sbx.commands.run("pip freeze 2>/dev/null || true", timeout=15)
            requirements = pip_result.stdout or ""

            # Download tar from sandbox
            tar_bytes = sbx.files.read("/tmp/sandbox_backup.tar.gz", format="bytes")

            # Upload to R2
            key = r2.upload_backup(self._agent_id, tar_bytes, requirements)
            logger.info(f"Backup complete for agent {self._agent_id}: {key}")
            return key
        except Exception as e:
            logger.warning(f"Backup failed for agent {self._agent_id}: {e}")
            return None

    def restore_from_r2(self, r2) -> bool:
        """Download latest backup from R2 and restore into sandbox. Returns success."""
        from core.r2_storage import R2Storage

        if not isinstance(r2, R2Storage) or not r2.enabled:
            return False

        try:
            tar_bytes, requirements = r2.download_latest_backup(self._agent_id)
            if tar_bytes is None:
                logger.info(f"No backup to restore for agent {self._agent_id}")
                return False

            sbx = self._ensure_sandbox()

            # Upload tar to sandbox
            sbx.files.write("/tmp/restore.tar.gz", tar_bytes)

            # Extract
            result = sbx.commands.run(
                "tar xzf /tmp/restore.tar.gz -C /home/user && rm /tmp/restore.tar.gz",
                timeout=120,
            )
            if result.exit_code != 0:
                logger.warning(f"Restore extract failed: {result.stderr}")
                return False

            # Reinstall pip packages (best-effort)
            if requirements and requirements.strip():
                sbx.files.write("/tmp/requirements.txt", requirements)
                sbx.commands.run(
                    "pip install -q -r /tmp/requirements.txt 2>/dev/null || true",
                    timeout=120,
                )

            logger.info(f"Restore complete for agent {self._agent_id}")
            return True
        except Exception as e:
            logger.warning(f"Restore failed for agent {self._agent_id}: {e}")
            return False

    # --- Lifecycle ---

    def pause(self) -> str | None:
        """Pause the sandbox and return the sandbox_id for later resume."""
        if self._sandbox:
            try:
                sandbox_id = self._sandbox.pause()
                logger.info(f"Paused E2B sandbox {sandbox_id} for agent {self._agent_id}")
                return sandbox_id
            except Exception as e:
                logger.error(f"Failed to pause sandbox: {e}")
        return None

    def kill(self) -> None:
        """Kill the sandbox permanently."""
        with self._idle_lock:
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None
        if self._sandbox:
            try:
                self._sandbox.kill()
                logger.info(f"Killed E2B sandbox for agent {self._agent_id}")
            except Exception as e:
                logger.warning(f"Failed to kill sandbox: {e}")
            self._sandbox = None

    @property
    def sandbox_id(self) -> str | None:
        if self._sandbox:
            return self._sandbox.sandbox_id
        return self._existing_sandbox_id
