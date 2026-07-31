from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command

ROOT = Path(__file__).resolve().parents[2]


def run_cycle(database_url: str) -> None:
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        if revision != "20260731_0001":
            raise RuntimeError(f"unexpected migration head: {revision}")
    finally:
        engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres-url")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "p1-migration-check.sqlite"
        run_cycle(f"sqlite:///{database}")
    if args.postgres_url:
        run_cycle(args.postgres_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
