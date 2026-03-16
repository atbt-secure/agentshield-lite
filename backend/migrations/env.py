import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── Import all models so Alembic can detect schema changes ───────────────────
# (must happen before target_metadata is set)
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base  # noqa: E402
import models  # noqa: E402, F401  — registers all ORM models

# Alembic Config object — provides access to values in alembic.ini
config = context.config

# Set the database URL from environment (overrides the empty placeholder in alembic.ini)
_db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentshield.db")
# Alembic's sync engine needs the sync driver variant
_sync_url = (
    _db_url
    .replace("sqlite+aiosqlite", "sqlite")
    .replace("postgresql+asyncpg", "postgresql+psycopg2")
)
config.set_main_option("sqlalchemy.url", _sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ── Offline migrations (generate SQL without a live DB) ───────────────────────

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations (against a live DB) ────────────────────────────────────

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
