.PHONY: bootstrap contracts contracts-check backend-check frontend-check migration-check p2-postgres-check p3-postgres-check p3-e2e secret-scan sensitive-documents-check check

bootstrap:
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv sync --project backend --extra dev
	cd frontend && corepack pnpm install --frozen-lockfile

contracts:
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend python backend/scripts/generate_contracts.py
	cd frontend && corepack pnpm generate:client

contracts-check:
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend python backend/scripts/generate_contracts.py --check
	cd frontend && corepack pnpm check:client

backend-check:
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend ruff check --force-exclude backend/src backend/scripts backend/alembic backend/tests scripts
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/scripts backend/alembic scripts
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend pytest -q -m "not postgres"
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend python -m compileall -q backend/src backend/scripts backend/alembic backend/tests scripts

frontend-check:
	cd frontend && corepack pnpm lint
	cd frontend && corepack pnpm typegen
	cd frontend && corepack pnpm typecheck
	cd frontend && corepack pnpm test
	cd frontend && corepack pnpm build

migration-check:
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend pytest -q backend/tests/contract/test_migrations.py

p2-postgres-check:
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" sh backend/scripts/run_p2_postgres_tests.sh

p3-postgres-check:
	@set -eu; \
	port=$$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'); \
	project="hyc-p3-pg-$$(date +%s)-$$$$"; \
	storage=$$(mktemp -d "$${TMPDIR:-/tmp}/hyc-p3-storage.XXXXXX"); \
	cleanup() { docker compose -p "$$project" down --volumes --remove-orphans >/dev/null 2>&1 || true; if [ -d "$$storage" ]; then find "$$storage" -depth -delete; fi; test ! -e "$$storage"; test -z "$$(docker ps -aq --filter label=com.docker.compose.project=$$project)"; test -z "$$(docker network ls -q --filter label=com.docker.compose.project=$$project)"; test -z "$$(docker volume ls -q --filter label=com.docker.compose.project=$$project)"; }; \
	trap cleanup EXIT INT TERM; \
	HYC_POSTGRES_HOST_PORT="$$port" docker compose -p "$$project" up --detach --wait postgres; \
	docker compose -p "$$project" exec -T postgres psql -v ON_ERROR_STOP=1 --username local_user --dbname hyc --command "CREATE ROLE hyc_app_test LOGIN PASSWORD 'local-placeholder-only'; GRANT CONNECT ON DATABASE hyc TO hyc_app_test;"; \
	owner_dsn="postgresql+psycopg://local_user:local-placeholder-only@127.0.0.1:$$port/hyc"; \
	app_dsn="postgresql+psycopg://hyc_app_test:local-placeholder-only@127.0.0.1:$$port/hyc"; \
	HYC_APP_ROLE=hyc_app_test uv run --project backend python backend/scripts/check_migrations.py --postgres-url "$$owner_dsn"; \
	HYC_P3_TEST_POSTGRES_DSN="$$owner_dsn" HYC_P3_TEST_APP_DSN="$$app_dsn" HYC_P3_TEST_STORAGE="$$storage" uv run --project backend pytest -q -m postgres backend/tests/integration/api; \
	true

p3-e2e:
	@set -eu; \
	ports=$$(python3 -c 'import socket; xs=[]; [xs.append((lambda s:(s.bind(("127.0.0.1",0)),s.getsockname()[1],s.close()))(socket.socket())[1]) for _ in range(3)]; print(*xs)'); \
	set -- $$ports; web_port=$$1; api_port=$$2; pg_port=$$3; \
	project="hyc-p3-e2e-$$(date +%s)-$$$$"; \
	browser_cache="$${TMPDIR:-/tmp}/hyc-p3-playwright-browsers"; \
	cleanup() { docker compose -p "$$project" down --volumes --remove-orphans >/dev/null 2>&1 || true; test -z "$$(docker ps -aq --filter label=com.docker.compose.project=$$project)"; test -z "$$(docker network ls -q --filter label=com.docker.compose.project=$$project)"; test -z "$$(docker volume ls -q --filter label=com.docker.compose.project=$$project)"; }; \
	trap cleanup EXIT INT TERM; \
	mkdir -p "$$browser_cache"; \
	cd frontend && PLAYWRIGHT_BROWSERS_PATH="$$browser_cache" corepack pnpm playwright:install:chromium; cd ..; \
	HYC_WEB_HOST_PORT="$$web_port" HYC_API_HOST_PORT="$$api_port" HYC_POSTGRES_HOST_PORT="$$pg_port" docker compose -p "$$project" up --build --detach --wait; \
	set +e; \
	cd frontend && P3_WEB_BASE_URL="http://127.0.0.1:$$web_port" P3_API_BASE_URL="http://127.0.0.1:$$api_port" PLAYWRIGHT_BROWSERS_PATH="$$browser_cache" corepack pnpm test:e2e:p3; status=$$?; cd ..; \
	set -e; \
	if [ "$$status" -ne 0 ]; then docker compose -p "$$project" logs --no-color api web postgres redis; fi; \
	cleanup; trap - EXIT INT TERM; exit "$$status"

secret-scan:
	python3 scripts/scan_secrets.py

sensitive-documents-check:
	python3 scripts/check_sensitive_documents.py

check: contracts-check backend-check frontend-check migration-check secret-scan sensitive-documents-check
	docker compose config --quiet
