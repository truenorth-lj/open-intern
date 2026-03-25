"""Messaging — unified cross-platform message sending and contact directory."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy
from langchain_core.tools import tool

from core.database import get_engine

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

VALID_PLATFORMS = {"lark", "discord", "telegram"}


# ---------------------------------------------------------------------------
# Contact CRUD (low-level, used by auto-capture and tools)
# ---------------------------------------------------------------------------


async def upsert_contact(
    database_url: str,
    platform: str,
    platform_id: str,
    contact_type: str,
    display_name: str,
    source: str = "auto",
    metadata: dict[str, Any] | None = None,
) -> dict:
    """Insert or update a contact. Returns the contact dict."""
    engine = get_engine(database_url)
    now = datetime.now(timezone.utc)
    contact_id = str(uuid4())
    meta_json = json.dumps(metadata or {})

    def _do():
        with engine.connect() as conn:
            # Atomic upsert: insert or update display_name on conflict
            result = conn.execute(
                sqlalchemy.text(
                    "INSERT INTO contacts "
                    "(id, platform, platform_id, type, display_name, "
                    "metadata_json, source, created_at, updated_at) "
                    "VALUES (:id, :platform, :pid, :type, :name, "
                    ":meta, :source, :now, :now) "
                    "ON CONFLICT (platform, platform_id) "
                    "DO UPDATE SET display_name = EXCLUDED.display_name, "
                    "updated_at = EXCLUDED.updated_at "
                    "RETURNING id, display_name, "
                    "(xmax::text::int > 0) AS was_updated"
                ),
                {
                    "id": contact_id,
                    "platform": platform,
                    "pid": platform_id,
                    "type": contact_type,
                    "name": display_name,
                    "meta": meta_json,
                    "source": source,
                    "now": now,
                },
            )
            row = result.fetchone()
            conn.commit()
            return {
                "id": row[0],
                "display_name": row[1],
                "updated": bool(row[2]),
            }

    return await asyncio.to_thread(_do)


def search_contacts_db(
    database_url: str,
    query: str = "",
    platform: str = "",
    contact_type: str = "",
    limit: int = 20,
) -> list[dict]:
    """Search contacts by name, platform, and/or type."""
    engine = get_engine(database_url)
    conditions = []
    params: dict[str, Any] = {"limit": limit}

    if query:
        conditions.append("LOWER(display_name) LIKE :query")
        params["query"] = f"%{query.lower()}%"
    if platform:
        conditions.append("platform = :platform")
        params["platform"] = platform
    if contact_type:
        conditions.append("type = :type")
        params["type"] = contact_type

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with engine.connect() as conn:
        rows = conn.execute(
            sqlalchemy.text(
                f"SELECT id, platform, platform_id, type, display_name, "  # noqa: S608
                f"metadata_json, source, created_at, updated_at "
                f"FROM contacts {where} "
                f"ORDER BY updated_at DESC LIMIT :limit"
            ),
            params,
        ).fetchall()

    return [
        {
            "id": r[0],
            "platform": r[1],
            "platform_id": r[2],
            "type": r[3],
            "display_name": r[4],
            "metadata": json.loads(r[5]) if r[5] else {},
            "source": r[6],
            "created_at": r[7].isoformat() if r[7] else "",
            "updated_at": r[8].isoformat() if r[8] else "",
        }
        for r in rows
    ]


def resolve_contact(
    database_url: str,
    to: str,
    default_platform: str = "",
) -> dict | None:
    """Resolve a recipient string to a contact.

    Supports:
    - Explicit platform prefix: "lark:ou_xxx"
    - Display name search: "LJ" (prefers default_platform if ambiguous)
    """
    engine = get_engine(database_url)

    # 1. Explicit prefix: "lark:ou_xxx"
    if ":" in to:
        parts = to.split(":", 1)
        if parts[0] in VALID_PLATFORMS:
            platform, pid = parts
            with engine.connect() as conn:
                row = conn.execute(
                    sqlalchemy.text(
                        "SELECT id, platform, platform_id, type, display_name "
                        "FROM contacts WHERE platform = :p AND platform_id = :pid"
                    ),
                    {"p": platform, "pid": pid},
                ).fetchone()
                if row:
                    return {
                        "id": row[0],
                        "platform": row[1],
                        "platform_id": row[2],
                        "type": row[3],
                        "display_name": row[4],
                    }
            # Not in contacts but valid explicit ID — return raw
            return {
                "id": "",
                "platform": platform,
                "platform_id": pid,
                "type": "user",
                "display_name": to,
            }

    # 2. Search by display name (case-insensitive exact match first)
    with engine.connect() as conn:
        rows = conn.execute(
            sqlalchemy.text(
                "SELECT id, platform, platform_id, type, display_name "
                "FROM contacts WHERE LOWER(display_name) = LOWER(:name) "
                "ORDER BY updated_at DESC"
            ),
            {"name": to},
        ).fetchall()

    if not rows:
        # Fuzzy match
        with engine.connect() as conn:
            rows = conn.execute(
                sqlalchemy.text(
                    "SELECT id, platform, platform_id, type, display_name "
                    "FROM contacts WHERE LOWER(display_name) LIKE :pattern "
                    "ORDER BY updated_at DESC LIMIT 5"
                ),
                {"pattern": f"%{to.lower()}%"},
            ).fetchall()

    if not rows:
        return None

    if len(rows) == 1:
        r = rows[0]
        return {
            "id": r[0],
            "platform": r[1],
            "platform_id": r[2],
            "type": r[3],
            "display_name": r[4],
        }

    # Multiple matches — prefer default platform
    if default_platform:
        for r in rows:
            if r[1] == default_platform:
                return {
                    "id": r[0],
                    "platform": r[1],
                    "platform_id": r[2],
                    "type": r[3],
                    "display_name": r[4],
                }

    # Return first match
    r = rows[0]
    return {
        "id": r[0],
        "platform": r[1],
        "platform_id": r[2],
        "type": r[3],
        "display_name": r[4],
    }


# ---------------------------------------------------------------------------
# MessageRouter — routes send_message calls to the right platform bot
# ---------------------------------------------------------------------------


class MessageRouter:
    """Routes messages from agents to platform recipients."""

    def __init__(
        self,
        agent_id: str,
        database_url: str,
        default_platform: str = "",
    ):
        self.agent_id = agent_id
        self.database_url = database_url
        self.default_platform = default_platform

    async def send(self, to: str, content: str, platform: str = "") -> str:
        """Send a message to a contact or raw ID. Returns status string."""
        from server import get_bot

        contact = resolve_contact(
            self.database_url, to, default_platform=platform or self.default_platform
        )
        if not contact:
            return f"Contact not found: {to}"

        target_platform = platform or contact["platform"] or self.default_platform
        if not target_platform:
            return "Cannot determine platform — specify platform or set a default."

        bot = get_bot(target_platform, self.agent_id)
        if not bot:
            return f"No {target_platform} bot available for this agent."

        try:
            if contact["type"] == "user":
                await bot.send_to_user(contact["platform_id"], content)
            else:
                await bot.send_message(contact["platform_id"], content)
            return f"Message sent to {contact['display_name']} via {target_platform}."
        except Exception as e:
            logger.exception("Failed to send message to %s", to)
            return f"Failed to send message: {e}"


# ---------------------------------------------------------------------------
# Agent tools — created per-agent, bound to a MessageRouter
# ---------------------------------------------------------------------------


def create_messaging_tools(
    router: MessageRouter,
    database_url: str,
) -> list:
    """Create LangChain tools for sending messages and managing contacts."""

    @tool
    async def send_message(to: str, content: str, platform: str = "") -> str:
        """Send a message to a person or channel.

        Args:
            to: Who to send to. Can be:
                - A contact name (e.g., "LJ", "Alice")
                - A channel name (e.g., "#dev-updates")
                - A platform-specific ID with prefix (e.g., "lark:ou_xxx",
                  "discord:123456", "telegram:789")
            content: The message text to send.
            platform: Override platform (default: your primary platform).
                      Options: "lark", "discord", "telegram".
        """
        return await router.send(to, content, platform)

    @tool
    def list_contacts(
        platform: str = "",
        contact_type: str = "",
        limit: int = 20,
    ) -> str:
        """List known contacts (people and groups).

        Args:
            platform: Filter by platform ("lark", "discord", "telegram").
                      Empty = all platforms.
            contact_type: Filter by type ("user" or "group").
                          Empty = all types.
            limit: Max results (default 20).
        """
        contacts = search_contacts_db(
            database_url,
            platform=platform,
            contact_type=contact_type,
            limit=limit,
        )
        if not contacts:
            return "No contacts found."
        lines = []
        for c in contacts:
            lines.append(
                f"- {c['display_name']} [{c['platform']}:{c['platform_id'][:12]}] type={c['type']}"
            )
        return "\n".join(lines)

    @tool
    def search_contacts(query: str) -> str:
        """Search contacts by name.

        Args:
            query: Name or partial name to search for.
        """
        contacts = search_contacts_db(database_url, query=query, limit=10)
        if not contacts:
            return f"No contacts matching '{query}'."
        lines = []
        for c in contacts:
            lines.append(
                f"- {c['display_name']} [{c['platform']}:{c['platform_id'][:12]}] type={c['type']}"
            )
        return "\n".join(lines)

    @tool
    async def add_contact(
        name: str,
        platform: str,
        platform_id: str,
        contact_type: str = "user",
    ) -> str:
        """Manually add a contact to the directory.

        Args:
            name: Display name (e.g., "Alice", "#dev-updates").
            platform: Platform ("lark", "discord", "telegram").
            platform_id: The platform-specific ID (e.g., open_id, user ID, chat_id).
            contact_type: "user" or "group" (default "user").
        """
        if platform not in VALID_PLATFORMS:
            return f"Invalid platform. Must be one of: {', '.join(VALID_PLATFORMS)}"
        if contact_type not in ("user", "group"):
            return "contact_type must be 'user' or 'group'."
        result = await upsert_contact(
            database_url=database_url,
            platform=platform,
            platform_id=platform_id,
            contact_type=contact_type,
            display_name=name,
            source="manual",
        )
        action = "Updated" if result.get("updated") else "Added"
        return f"{action} contact: {name} [{platform}:{platform_id}]"

    return [send_message, list_contacts, search_contacts, add_contact]
