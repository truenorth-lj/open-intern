"""Safety middleware — action classification and audit logging."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.config import AppConfig

logger = logging.getLogger(__name__)


class ActionLevel(str, Enum):
    READ = "read"  # observing info — always allowed
    WRITE_INTERNAL = "write_internal"  # notes, drafts — allowed, logged
    WRITE_EXTERNAL = "write_external"  # emails, public posts — may need approval
    DESTRUCTIVE = "destructive"  # deletions, merges — always needs approval


class ActionVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_APPROVAL = "needs_approval"


class AuditEntry(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action_type: str
    action_level: ActionLevel
    verdict: ActionVerdict
    description: str
    details: dict[str, Any] = Field(default_factory=dict)


def _create_audit_logger(audit_file: Path) -> logging.Logger:
    """Create a dedicated logger with rotating file handler for audit entries."""
    audit_file.parent.mkdir(parents=True, exist_ok=True)

    audit_logger = logging.getLogger("open_intern.audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False

    if not audit_logger.handlers:
        handler = RotatingFileHandler(
            audit_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        audit_logger.addHandler(handler)

        # Set file permissions to owner-only (on Unix)
        try:
            os.chmod(audit_file, 0o600)
        except OSError:
            pass

    return audit_logger


class SafetyMiddleware:
    """Every agent action passes through this middleware."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.audit_log: list[AuditEntry] = []
        self._audit_file = Path("logs/audit.jsonl")
        self._audit_logger = _create_audit_logger(self._audit_file)

    def classify_action(self, action_type: str) -> ActionLevel:
        """Classify an action into a safety level."""
        read_actions = {"read_channel", "read_message", "search_memory", "read_file", "view_pr"}
        write_internal = {"respond_to_mention", "respond_to_dm", "internal_note", "store_memory"}
        destructive = {"delete_anything", "delete_message", "merge_pr", "close_issue"}

        if action_type in read_actions:
            return ActionLevel.READ
        if action_type in write_internal:
            return ActionLevel.WRITE_INTERNAL
        if action_type in destructive:
            return ActionLevel.DESTRUCTIVE
        # Default: check config
        if action_type in self.config.safety.require_approval_for:
            return ActionLevel.WRITE_EXTERNAL
        if action_type in self.config.safety.auto_allow:
            return ActionLevel.WRITE_INTERNAL
        return ActionLevel.WRITE_EXTERNAL

    def check(self, action_type: str, description: str = "", **details: Any) -> ActionVerdict:
        """Check if an action is allowed. Returns verdict."""
        level = self.classify_action(action_type)

        if level == ActionLevel.READ:
            verdict = ActionVerdict.ALLOW
        elif level == ActionLevel.WRITE_INTERNAL:
            verdict = ActionVerdict.ALLOW
        elif level == ActionLevel.WRITE_EXTERNAL:
            if action_type in self.config.safety.auto_allow:
                verdict = ActionVerdict.ALLOW
            else:
                verdict = ActionVerdict.NEEDS_APPROVAL
        else:  # DESTRUCTIVE
            verdict = ActionVerdict.NEEDS_APPROVAL

        entry = AuditEntry(
            action_type=action_type,
            action_level=level,
            verdict=verdict,
            description=description,
            details=details,
        )
        self._log(entry)

        return verdict

    def _log(self, entry: AuditEntry) -> None:
        """Append to in-memory log and audit file (via rotating handler)."""
        self.audit_log.append(entry)
        try:
            self._audit_logger.info(entry.model_dump_json())
        except OSError:
            logger.warning("Failed to write audit log entry", exc_info=True)
        logger.info(f"[AUDIT] {entry.verdict.value}: {entry.action_type} - {entry.description}")

    def get_recent_audit(self, limit: int = 20) -> list[AuditEntry]:
        """Get recent audit entries."""
        return self.audit_log[-limit:]
