.PHONY: bootstrap contracts contracts-check backend-check frontend-check migration-check p2-postgres-check secret-scan sensitive-documents-check check

bootstrap:
	XDG_CACHE_HOME="$(PWD)/.uv-cache" uv sync --project backend --extra dev
	cd frontend && corepack pnpm install --frozen-lockfile

contracts:
	XDG_CACHE_HOME="$(PWD)/.uv-cache" uv run --project backend python backend/scripts/generate_contracts.py
	cd frontend && corepack pnpm generate:client

contracts-check:
	XDG_CACHE_HOME="$(PWD)/.uv-cache" uv run --project backend python backend/scripts/generate_contracts.py --check
	cd frontend && corepack pnpm check:client

backend-check:
	XDG_CACHE_HOME="$(PWD)/.uv-cache" uv run --project backend ruff check --force-exclude backend/src backend/scripts backend/alembic backend/tests scripts
	XDG_CACHE_HOME="$(PWD)/.uv-cache" uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/scripts backend/alembic scripts
	XDG_CACHE_HOME="$(PWD)/.uv-cache" uv run --project backend pytest -q -m "not postgres"
	XDG_CACHE_HOME="$(PWD)/.uv-cache" uv run --project backend python -m compileall -q backend/src backend/scripts backend/alembic backend/tests scripts

frontend-check:
	cd frontend && corepack pnpm lint
	cd frontend && corepack pnpm typegen
	cd frontend && corepack pnpm typecheck
	cd frontend && corepack pnpm test
	cd frontend && corepack pnpm build

migration-check:
	XDG_CACHE_HOME="$(PWD)/.uv-cache" uv run --project backend pytest -q backend/tests/contract/test_migrations.py

p2-postgres-check:
	XDG_CACHE_HOME="$(PWD)/.uv-cache" sh backend/scripts/run_p2_postgres_tests.sh

secret-scan:
	python3 scripts/scan_secrets.py

sensitive-documents-check:
	python3 scripts/check_sensitive_documents.py

check: contracts-check backend-check frontend-check migration-check secret-scan sensitive-documents-check
	docker compose config --quiet
