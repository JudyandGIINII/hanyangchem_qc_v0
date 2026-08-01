from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config
backend_src = Path(__file__).resolve().parents[1] / "src"
if str(backend_src) not in sys.path:
    sys.path.insert(0, str(backend_src))
from hyc_data.models import Base  # noqa: E402

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
