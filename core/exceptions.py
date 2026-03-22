"""Domain-specific exceptions for consistent error handling."""

from __future__ import annotations


class OpenInternError(Exception):
    """Base exception for all open_intern errors."""


class AgentNotFoundError(OpenInternError):
    """Raised when a requested agent does not exist."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        super().__init__(f"Agent '{agent_id}' not found")


class DuplicateAgentError(OpenInternError):
    """Raised when creating an agent with an ID that already exists."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        super().__init__(f"Agent '{agent_id}' already exists")


class AgentInitializationError(OpenInternError):
    """Raised when an agent fails to initialize."""

    def __init__(self, agent_id: str, reason: str):
        self.agent_id = agent_id
        self.reason = reason
        super().__init__(f"Failed to initialize agent '{agent_id}': {reason}")


class AgentNotInitializedError(OpenInternError):
    """Raised when trying to use an agent that hasn't been initialized."""

    def __init__(self, agent_id: str = "unknown"):
        self.agent_id = agent_id
        super().__init__(f"Agent '{agent_id}' not initialized. Call initialize() first.")


class ConfigurationError(OpenInternError):
    """Raised for missing or invalid configuration."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class SettingNotFoundError(OpenInternError):
    """Raised when a system setting does not exist."""

    def __init__(self, key: str):
        self.key = key
        super().__init__(f"Setting '{key}' not found")
