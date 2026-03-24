"""Backend protocol types — standalone replacements for deepagents.backends.protocol.

These dataclasses define the interface between the agent's filesystem tools
and the sandbox backend (E2B, local shell, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class SandboxStatus(str, Enum):
    """Canonical sandbox lifecycle states.

    Used by the status API so frontend and backend always agree on state.
    """

    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class FileInfo:
    path: str
    is_dir: bool = False
    size: int | None = None


@dataclass
class WriteResult:
    path: str = ""
    error: str | None = None


@dataclass
class EditResult:
    path: str = ""
    occurrences: int = 0
    error: str | None = None


@dataclass
class ExecuteResponse:
    output: str = ""
    exit_code: int = 0
    truncated: bool = False


@dataclass
class GrepMatch:
    path: str = ""
    line: int = 0
    text: str = ""


@dataclass
class FileUploadResponse:
    path: str = ""
    error: str | None = None


@dataclass
class FileDownloadResponse:
    path: str = ""
    content: bytes | None = None
    error: str | None = None


@runtime_checkable
class SandboxBackendProtocol(Protocol):
    """Protocol for sandbox backends that support file ops + shell execution."""

    def ls_info(self, path: str) -> list[FileInfo]: ...
    async def als_info(self, path: str) -> list[FileInfo]: ...

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str: ...
    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> str: ...

    def write(self, file_path: str, content: str) -> WriteResult: ...
    async def awrite(self, file_path: str, content: str) -> WriteResult: ...

    def edit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> EditResult: ...
    async def aedit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> EditResult: ...

    def grep_raw(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> list[GrepMatch] | str: ...
    async def agrep_raw(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> list[GrepMatch] | str: ...

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]: ...
    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]: ...

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse: ...
    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse: ...

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]: ...
    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]: ...
