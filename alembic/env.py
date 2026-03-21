import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from memory.store import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve DB URL: DATABASE_URL env var > app config > alembic.ini fallback
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    try:
        from core.config import load_config

        app_config = load_config()
        db_url = app_config.database_url
    except Exception:
        pass
if db_url:
    # Normalise to psycopg2 driver (same as MemoryStore)
    if db_url.startswith("postgresql+psycopg://"):
        db_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)
    config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata

# Exclude langgraph checkpoint tables from autogenerate
EXCLUDE_TABLES = {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"}


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name in EXCLUDE_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
