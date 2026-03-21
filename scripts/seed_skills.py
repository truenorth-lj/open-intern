"""Seed skills from disk into PostgresStore.

Scans the skills/ directory for SKILL.md files and writes them into
PostgresStore so Deep Agents can discover them at runtime.

Usage:
    python scripts/seed_skills.py                    # Use DATABASE_URL env var
    python scripts/seed_skills.py --db-url "postgresql://..."
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
NAMESPACE = ("filesystem",)
MAX_FILE_SIZE = 1_000_000  # 1MB


def seed_skills(store, skills_dir: Path | None = None) -> int:
    """Seed all skills from disk into a LangGraph BaseStore.

    Args:
        store: A LangGraph BaseStore instance (e.g. PostgresStore).
        skills_dir: Directory containing skill subdirectories. Defaults to project skills/.

    Returns:
        Number of skill files seeded.
    """
    from deepagents.backends.utils import create_file_data

    skills_dir = skills_dir or SKILLS_DIR
    if not skills_dir.exists():
        logger.warning(f"Skills directory not found: {skills_dir}")
        return 0

    count = 0
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith((".", "_")):
            continue

        for file_path in sorted(skill_dir.rglob("*")):
            if not file_path.is_file():
                continue

            # Skip oversized files
            if file_path.stat().st_size > MAX_FILE_SIZE:
                logger.warning(f"Skipping oversized file: {file_path}")
                continue

            # Build virtual path: /skills/git-ops/SKILL.md
            relative = file_path.relative_to(skills_dir)
            virtual_path = f"/skills/{relative.as_posix()}"

            content = file_path.read_text(encoding="utf-8")
            file_data = create_file_data(content)

            # Check if file already exists with same content
            existing = store.get(NAMESPACE, virtual_path)
            if existing and existing.value.get("content") == file_data["content"]:
                logger.debug(f"Skill unchanged, skipping: {virtual_path}")
                continue

            store.put(NAMESPACE, virtual_path, file_data)
            logger.info(f"Seeded skill: {virtual_path}")
            count += 1

    return count


def list_skills(store) -> list[dict]:
    """List all skills currently stored in PostgresStore.

    Returns:
        List of skill metadata dicts with name, description, path, and modified_at.
    """
    import yaml

    items = store.search(NAMESPACE, limit=1000)
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
    args = parser.parse_args()

    db_url = args.db_url
    if not db_url:
        logger.error("DATABASE_URL not set. Use --db-url or set DATABASE_URL env var.")
        raise SystemExit(1)

    from langgraph.store.postgres import PostgresStore

    store_ctx = PostgresStore.from_conn_string(db_url)
    with store_ctx as store:
        store.setup()
        n = seed_skills(store)
        logger.info(f"Seeded {n} skill file(s).")
