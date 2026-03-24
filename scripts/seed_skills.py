"""Seed skills from disk into PostgresStore.

Scans the skills/ directory for SKILL.md files and writes them into
PostgresStore so the agent can discover them at runtime.

Usage:
    python scripts/seed_skills.py                    # Use DATABASE_URL env var
    python scripts/seed_skills.py --db-url "postgresql://..."
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
DEFAULT_AGENT_ID = "default"
MAX_FILE_SIZE = 1_000_000  # 1MB


def _namespace_for(agent_id: str) -> tuple[str, ...]:
    """Return the store namespace matching the agent's filesystem."""
    return ("agent", agent_id, "filesystem")


def _create_file_data(content: str) -> dict:
    """Create a file data dict compatible with the store format.

    Replaces the deepagents.backends.utils.create_file_data dependency.
    """
    now = datetime.now(timezone.utc).isoformat()
    return {
        "content": content.splitlines(),
        "created_at": now,
        "modified_at": now,
    }


def _iter_skill_files(skills_dir: Path):
    """Yield (virtual_path, content) for all skill files."""
    if not skills_dir.exists():
        logger.warning(f"Skills directory not found: {skills_dir}")
        return

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith((".", "_")):
            continue

        for file_path in sorted(skill_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.stat().st_size > MAX_FILE_SIZE:
                logger.warning(f"Skipping oversized file: {file_path}")
                continue

            relative = file_path.relative_to(skills_dir)
            virtual_path = f"/skills/{relative.as_posix()}"
            content = file_path.read_text(encoding="utf-8")
            yield virtual_path, content


def seed_skills(store, skills_dir: Path | None = None, *, agent_id: str = DEFAULT_AGENT_ID) -> int:
    """Seed all skills from disk into a LangGraph BaseStore (sync).

    Args:
        store: A LangGraph BaseStore instance (e.g. PostgresStore).
        skills_dir: Directory containing skill subdirectories. Defaults to project skills/.
        agent_id: Agent ID to determine the correct store namespace.

    Returns:
        Number of skill files seeded.
    """
    namespace = _namespace_for(agent_id)
    skills_dir = skills_dir or SKILLS_DIR

    count = 0
    for virtual_path, content in _iter_skill_files(skills_dir):
        file_data = _create_file_data(content)

        existing = store.get(namespace, virtual_path)
        if existing and existing.value.get("content") == file_data["content"]:
            logger.debug(f"Skill unchanged, skipping: {virtual_path}")
            continue

        store.put(namespace, virtual_path, file_data)
        logger.info(f"Seeded skill: {virtual_path}")
        count += 1

    return count


async def seed_skills_async(
    store, skills_dir: Path | None = None, *, agent_id: str = DEFAULT_AGENT_ID
) -> int:
    """Seed all skills from disk into an AsyncPostgresStore (native async).

    Args:
        store: A LangGraph AsyncBaseStore instance (e.g. AsyncPostgresStore).
        skills_dir: Directory containing skill subdirectories.
        agent_id: Agent ID to determine the correct store namespace.

    Returns:
        Number of skill files seeded.
    """
    namespace = _namespace_for(agent_id)
    skills_dir = skills_dir or SKILLS_DIR

    count = 0
    for virtual_path, content in _iter_skill_files(skills_dir):
        file_data = _create_file_data(content)

        existing = await store.aget(namespace, virtual_path)
        if existing and existing.value.get("content") == file_data["content"]:
            logger.debug(f"Skill unchanged, skipping: {virtual_path}")
            continue

        await store.aput(namespace, virtual_path, file_data)
        logger.info(f"Seeded skill: {virtual_path}")
        count += 1

    return count


def list_skills(store, *, agent_id: str = DEFAULT_AGENT_ID) -> list[dict]:
    """List all skills currently stored in PostgresStore.

    Returns:
        List of skill metadata dicts with name, description, path, and modified_at.
    """
    import yaml

    namespace = _namespace_for(agent_id)
    items = store.search(namespace, limit=1000)
    skills = {}

    for item in items:
        key = item.key
        if not key.startswith("/skills/"):
            continue

        # Extract skill name from path: /skills/git-ops/SKILL.md -> git-ops
        parts = key.split("/")
        if len(parts) < 3:
            continue
        skill_name = parts[2]

        if skill_name not in skills:
            skills[skill_name] = {
                "name": skill_name,
                "description": "",
                "files": [],
                "modified_at": "",
            }

        file_info = {
            "path": key,
            "modified_at": item.value.get("modified_at", ""),
        }
        skills[skill_name]["files"].append(file_info)

        # Parse SKILL.md frontmatter for metadata
        if key.endswith("/SKILL.md"):
            content = "\n".join(item.value.get("content", []))
            skills[skill_name]["modified_at"] = item.value.get("modified_at", "")
            # Extract YAML frontmatter
            if content.startswith("---"):
                try:
                    _, frontmatter, body = content.split("---", 2)
                    meta = yaml.safe_load(frontmatter)
                    if isinstance(meta, dict):
                        skills[skill_name]["description"] = meta.get("description", "")
                        skills[skill_name]["allowed_tools"] = meta.get("allowed-tools", "")
                        skills[skill_name]["category"] = meta.get("metadata", {}).get(
                            "category", ""
                        )
                        skills[skill_name]["version"] = meta.get("metadata", {}).get("version", "")
                        skills[skill_name]["content"] = body.strip()
                except (ValueError, yaml.YAMLError) as e:
                    logger.warning(f"Failed to parse frontmatter for {key}: {e}")

    return sorted(skills.values(), key=lambda s: s["name"])


if __name__ == "__main__":
    import argparse
    import os

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Seed skills into PostgresStore")
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
    args = parser.parse_args()

    db_url = args.db_url
    if not db_url:
        logger.error("DATABASE_URL not set. Use --db-url or set DATABASE_URL env var.")
        raise SystemExit(1)

    from langgraph.store.postgres import PostgresStore

    store_ctx = PostgresStore.from_conn_string(db_url)
    with store_ctx as store:
        store.setup()
        n = seed_skills(store, agent_id=args.agent_id)
        logger.info(f"Seeded {n} skill file(s).")
