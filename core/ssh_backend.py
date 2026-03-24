"""SSH backend — runs agent shell commands on a remote machine via SSH/SFTP."""

from __future__ import annotations

import asyncio
import logging
import re
import shlex
import stat
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

MAX_OUTPUT_BYTES = 100_000


@dataclass
class SSHConnectionInfo:
    """SSH connection parameters."""

    host: str
    port: int = 22
    username: str = "user"
    private_key: str = ""  # PEM-encoded private key string
    password: str = ""  # fallback if no key


class SSHBackend(SandboxBackendProtocol):
    """Backend that executes commands and file ops on a remote machine via SSH.

    Connects to any machine reachable over SSH — Mac Mini, Raspberry Pi,
    cloud VM, etc. Uses paramiko for SSH + SFTP.
    """

    def __init__(
        self,
        agent_id: str,
        *,
        connection: SSHConnectionInfo,
        default_timeout: int = 30,
    ):
        self._agent_id = agent_id
        self._conn_info = connection
        self._default_timeout = default_timeout
        self._client = None
        self._sftp = None

    @property
    def id(self) -> str:
        return f"ssh-{self._conn_info.host}-{self._agent_id}"

    def connect(self) -> None:
        """Establish SSH connection."""
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs: dict = {
            "hostname": self._conn_info.host,
            "port": self._conn_info.port,
            "username": self._conn_info.username,
            "timeout": 10,
        }

        if self._conn_info.private_key:
            import io

            key_file = io.StringIO(self._conn_info.private_key)
            try:
                pkey = paramiko.RSAKey.from_private_key(key_file)
            except paramiko.SSHException:
                key_file.seek(0)
                try:
                    pkey = paramiko.Ed25519Key.from_private_key(key_file)
                except paramiko.SSHException:
                    key_file.seek(0)
                    pkey = paramiko.ECDSAKey.from_private_key(key_file)
            kwargs["pkey"] = pkey
        elif self._conn_info.password:
            kwargs["password"] = self._conn_info.password
        # else: rely on ssh-agent or default keys

        client.connect(**kwargs)
        self._client = client
        self._sftp = client.open_sftp()
        logger.info(
            f"SSH connected to {self._conn_info.host}:{self._conn_info.port} "
            f"as {self._conn_info.username} for agent {self._agent_id}"
        )

    def _ensure_connected(self):
        """Ensure SSH connection is alive, reconnect if needed."""
        if self._client is None or self._client.get_transport() is None:
            self.connect()
            return
        transport = self._client.get_transport()
        if not transport.is_active():
            logger.warning(f"SSH connection lost for agent {self._agent_id}, reconnecting...")
            self.connect()

    def _ensure_sftp(self):
        """Ensure SFTP session is alive."""
        self._ensure_connected()
        if self._sftp is None:
            self._sftp = self._client.open_sftp()
        return self._sftp

    # --- Execute ---

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        self._ensure_connected()
        effective_timeout = timeout or self._default_timeout
        try:
            _, stdout_ch, stderr_ch = self._client.exec_command(command, timeout=effective_timeout)
            stdout = stdout_ch.read().decode("utf-8", errors="replace")
            stderr = stderr_ch.read().decode("utf-8", errors="replace")
            exit_code = stdout_ch.channel.recv_exit_status()

            parts = []
            if stdout:
                parts.append(stdout)
            if stderr:
                parts.append("\n".join(f"[stderr] {line}" for line in stderr.splitlines()))

            output = "\n".join(parts) if parts else "<no output>"
            truncated = len(output.encode()) > MAX_OUTPUT_BYTES
            if truncated:
                output = output[:MAX_OUTPUT_BYTES] + "\n... (output truncated)"

            if exit_code and exit_code != 0:
                output += f"\n\nExit code: {exit_code}"

            return ExecuteResponse(output=output, exit_code=exit_code, truncated=truncated)
        except Exception as e:
            error_msg = str(e)
            if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
                return ExecuteResponse(
                    output=f"Command timed out after {effective_timeout}s",
                    exit_code=124,
                )
            return ExecuteResponse(output=f"Execution error: {error_msg}", exit_code=1)

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return await asyncio.to_thread(self.execute, command, timeout=timeout)

    # --- File operations ---

    def ls_info(self, path: str) -> list[FileInfo]:
        sftp = self._ensure_sftp()
        try:
            entries = sftp.listdir_attr(path)
            results = []
            for e in entries:
                full_path = f"{path.rstrip('/')}/{e.filename}"
                is_dir = stat.S_ISDIR(e.st_mode) if e.st_mode else False
                results.append(
                    FileInfo(
                        path=full_path,
                        is_dir=is_dir,
                        size=e.st_size,
                    )
                )
            return results
        except FileNotFoundError:
            logger.warning(f"SSH ls_info: path not found: {path}")
            return []
        except Exception as e:
            logger.warning(f"SSH ls_info error: {e}")
            return []

    async def als_info(self, path: str) -> list[FileInfo]:
        return await asyncio.to_thread(self.ls_info, path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        sftp = self._ensure_sftp()
        try:
            with sftp.open(file_path, "r") as f:
                content = f.read().decode("utf-8", errors="replace")
            lines = content.splitlines()
            selected = lines[offset : offset + limit]
            numbered = []
            for i, line in enumerate(selected, start=offset + 1):
                numbered.append(f"{i:>6}\t{line}")
            return "\n".join(numbered)
        except Exception as e:
            return f"Error reading {file_path}: {e}"

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        return await asyncio.to_thread(self.read, file_path, offset, limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        sftp = self._ensure_sftp()
        try:
            # Ensure parent directory exists
            parent = "/".join(file_path.rsplit("/", 1)[:-1])
            if parent:
                self.execute(f"mkdir -p {shlex.quote(parent)}")
            with sftp.open(file_path, "w") as f:
                f.write(content.encode("utf-8"))
            return WriteResult(path=file_path)
        except Exception as e:
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
        sftp = self._ensure_sftp()
        try:
            with sftp.open(file_path, "r") as f:
                content = f.read().decode("utf-8", errors="replace")

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

            with sftp.open(file_path, "w") as f:
                f.write(new_content.encode("utf-8"))
            return EditResult(path=file_path, occurrences=count)
        except Exception as e:
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
        try:
            cmd_parts = ["grep", "-rn"]
            if glob:
                cmd_parts.extend(["--include", shlex.quote(glob)])
            cmd_parts.extend(["--", shlex.quote(pattern)])
            cmd_parts.append(shlex.quote(path or "/home/user"))

            result = self.execute(" ".join(cmd_parts), timeout=30)
            stdout = result.output
            if not stdout.strip() or result.exit_code == 1:
                return []

            matches = []
            for line in stdout.splitlines()[:100]:
                m = re.match(r"^(.+?):(\d+):(.*)$", line)
                if m:
                    matches.append(
                        GrepMatch(path=m.group(1), line=int(m.group(2)), text=m.group(3))
                    )
            return matches
        except Exception as e:
            return f"Grep error: {e}"

    async def agrep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        return await asyncio.to_thread(self.grep_raw, pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        try:
            result = self.execute(
                f"find {shlex.quote(path)} -path {shlex.quote(pattern)} -type f",
                timeout=15,
            )
            stdout = result.output
            return [
                FileInfo(path=p.strip(), is_dir=False) for p in stdout.splitlines() if p.strip()
            ][:100]
        except Exception:
            return []

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        return await asyncio.to_thread(self.glob_info, pattern, path)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        sftp = self._ensure_sftp()
        results = []
        for file_path, content in files:
            try:
                parent = "/".join(file_path.rsplit("/", 1)[:-1])
                if parent:
                    self.execute(f"mkdir -p {shlex.quote(parent)}")
                with sftp.open(file_path, "wb") as f:
                    f.write(content)
                results.append(FileUploadResponse(path=file_path, error=None))
            except Exception as e:
                results.append(FileUploadResponse(path=file_path, error=str(e)))
        return results

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        sftp = self._ensure_sftp()
        results = []
        for file_path in paths:
            try:
                with sftp.open(file_path, "rb") as f:
                    content = f.read()
                results.append(FileDownloadResponse(path=file_path, content=content, error=None))
            except Exception:
                results.append(
                    FileDownloadResponse(path=file_path, content=None, error="file_not_found")
                )
        return results

    # --- Lifecycle ---

    def disconnect(self) -> None:
        """Close SSH connection."""
        if self._sftp:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        logger.info(f"SSH disconnected for agent {self._agent_id}")

    @property
    def sandbox_id(self) -> str | None:
        """Compatibility with E2B backend — SSH has no sandbox ID."""
        return None
