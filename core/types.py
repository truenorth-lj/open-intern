"""Shared type definitions to replace untyped dicts."""

from __future__ import annotations

from typing import TypedDict


class ChatContext(TypedDict, total=False):
    """Context passed alongside a chat message."""

    platform: str
    channel_id: str
    user_id: str
    user_name: str
    is_dm: bool
    thread_id: str


class TokenUsage(TypedDict):
    """Token usage from a single agent invocation."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
