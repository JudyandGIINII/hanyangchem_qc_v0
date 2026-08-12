.PHONY: bootstrap contracts contracts-check backend-check frontend-check migration-check p2-postgres-check p3-postgres-check p3-e2e p6-backup-restore-verify p4-golden-check p4-benchmark-fixture p4-preflight-check local-ocr-bootstrap p4-local-ocr-preflight p4-local-ocr-smoke secret-scan sensitive-documents-check check

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
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend pytest -q -m "not postgres and not local_ocr_runtime"
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

p6-backup-restore-verify:
	@set -eu; \
	root="$(PWD)"; \
	port=$$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'); \
	project="hyc-p6-backup-$$(date +%s)-$$$$"; \
	source_storage=$$(mktemp -d "$${TMPDIR:-/tmp}/hyc-p6-source-storage.XXXXXX"); \
	restore_storage=$$(mktemp -d "$${TMPDIR:-/tmp}/hyc-p6-restore-storage.XXXXXX"); \
	backup_dir=$$(mktemp -d "$${TMPDIR:-/tmp}/hyc-p6-backup-output.XXXXXX"); \
	source_db="hyc_p6_disposable_$$(date +%s)_$$$$"; \
	restore_db="hyc_p6_restore_$$(date +%s)_$$$$"; \
	cleanup() { docker compose -p "$$project" down --volumes --remove-orphans >/dev/null 2>&1 || true; for path in "$$source_storage" "$$restore_storage" "$$backup_dir"; do if [ -d "$$path" ]; then find "$$path" -depth -delete; fi; test ! -e "$$path"; done; test -z "$$(docker ps -aq --filter label=com.docker.compose.project=$$project)"; test -z "$$(docker network ls -q --filter label=com.docker.compose.project=$$project)"; test -z "$$(docker volume ls -q --filter label=com.docker.compose.project=$$project)"; }; \
	trap cleanup EXIT INT TERM; \
	COMPOSE_BAKE=0 DOCKER_BUILDKIT=0 HYC_POSTGRES_HOST_PORT="$$port" docker compose -p "$$project" up --detach --wait postgres; \
	docker compose -p "$$project" exec -T postgres createdb --username local_user "$$source_db"; \
	docker compose -p "$$project" exec -T postgres createdb --username local_user "$$restore_db"; \
	source_dsn="postgresql+psycopg://local_user:local-placeholder-only@127.0.0.1:$$port/$$source_db"; \
	restore_dsn="postgresql+psycopg://local_user:local-placeholder-only@127.0.0.1:$$port/$$restore_db"; \
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$$root/.uv-cache}" uv run --project "$$root/backend" python -c 'from alembic import command; from alembic.config import Config; import sys; config = Config(sys.argv[1]); config.set_main_option("sqlalchemy.url", sys.argv[2]); command.upgrade(config, "head")' "$$root/backend/alembic.ini" "$$source_dsn"; \
	docker compose -p "$$project" exec -T postgres psql -v ON_ERROR_STOP=1 --username local_user --dbname "$$source_db" --command "CREATE TABLE p6_backup_probe (id integer PRIMARY KEY, value text NOT NULL); INSERT INTO p6_backup_probe (id, value) VALUES (1, 'backup-restore-rehearsal');"; \
	cp "$$root/.env.example" "$$source_storage/p6-backup-probe.env"; \
	HYC_P6_DISPOSABLE=1 "$$root/scripts/backup.sh" --database-url "$$source_dsn" --storage-root "$$source_storage" --output-dir "$$backup_dir"; \
	HYC_P6_DISPOSABLE=1 "$$root/scripts/restore-verify.sh" --database-url "$$restore_dsn" --storage-root "$$restore_storage" --backup-dir "$$backup_dir"; \
	true

p6-report-check:
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend pytest -q backend/tests/unit/reports

p4-golden-check:
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend pytest -q backend/tests/golden backend/tests/contract/test_extraction_contract.py backend/tests/contract/test_extraction_port.py

p4-benchmark-fixture:
	@set -eu; \
	root="$(PWD)"; \
	fixture="$$root/backend/tests/fixtures/p4/synthetic/p4a_edge_dataset.v1.json"; \
	temp_root=$$(mktemp -d "$${TMPDIR:-/tmp}/hyc-p4a-benchmark.XXXXXX"); \
	cleanup() { if [ -d "$$temp_root" ]; then find "$$temp_root" -depth -delete; fi; test ! -e "$$temp_root"; }; \
	trap cleanup EXIT INT TERM; \
	mkdir "$$temp_root/one" "$$temp_root/two"; \
	(cd "$$temp_root/one" && TZ=UTC LC_ALL=C XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$$root/.uv-cache}" uv run --project "$$root/backend" python "$$root/backend/scripts/run_p4_golden.py" --fixture "$$fixture" --output report.json); \
	(cd "$$temp_root/two" && TZ=Pacific/Honolulu LC_ALL=C XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$$root/.uv-cache}" uv run --project "$$root/backend" python "$$root/backend/scripts/run_p4_golden.py" --fixture "$$fixture" --output report.json); \
	cmp "$$temp_root/one/report.json" "$$temp_root/two/report.json"; \
	python3 -c 'import hashlib,json,pathlib,sys; output=pathlib.Path(sys.argv[1]); fixture=pathlib.Path(sys.argv[2]); payload=json.loads(output.read_text()); print("p4-benchmark-fixture: repeatable output=" + hashlib.sha256(output.read_bytes()).hexdigest() + " report=" + payload["report_sha256"] + " fixture=" + hashlib.sha256(fixture.read_bytes()).hexdigest())' "$$temp_root/one/report.json" "$$fixture"

p4-preflight-check:
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend pytest -q backend/tests/preflight
	@set -eu; \
	root="$(PWD)"; \
	temp_root=$$(mktemp -d "$${TMPDIR:-/tmp}/hyc-p4-preflight.XXXXXX"); \
	cleanup() { if [ -d "$$temp_root" ]; then find "$$temp_root" -depth -delete; fi; test ! -e "$$temp_root"; }; \
	trap cleanup EXIT INT TERM; \
	mkdir "$$temp_root/one" "$$temp_root/two"; \
	(cd "$$temp_root/one" && TZ=UTC LC_ALL=C XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$$root/.uv-cache}" uv run --project "$$root/backend" python "$$root/backend/scripts/run_p4_preflight.py" > result.json); \
	(cd "$$temp_root/two" && TZ=Pacific/Honolulu LC_ALL=C XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$$root/.uv-cache}" uv run --project "$$root/backend" python "$$root/backend/scripts/run_p4_preflight.py" > result.json); \
	cmp "$$temp_root/one/result.json" "$$temp_root/two/result.json"; \
	python3 -c 'import hashlib,json,pathlib,sys; output=pathlib.Path(sys.argv[1]); payload=json.loads(output.read_text()); print("p4-preflight-check: repeatable output=" + hashlib.sha256(output.read_bytes()).hexdigest() + " aggregate=" + payload["local_pilot"]["aggregate_sha256"] + " default=" + payload["ap02"]["default_status"] + " complete=" + payload["ap02"]["complete_status"] + " side_effects=" + payload["ap02"]["side_effects"])' "$$temp_root/one/result.json"

local-ocr-bootstrap:
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv sync --project backend --extra dev --extra local-ocr
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --project backend --extra local-ocr python backend/scripts/bootstrap_local_ocr_models.py --models-root "$(PWD)/.local-ocr-models/models" --archives-root "$(PWD)/.local-ocr-models/archives"

p4-local-ocr-preflight:
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --offline --frozen --project backend --extra local-ocr python backend/scripts/preflight_local_ocr.py --models-root "$(PWD)/.local-ocr-models/models" --initialize-engine
	XDG_CACHE_HOME="$${XDG_CACHE_HOME:-$(PWD)/.uv-cache}" uv run --offline --frozen --project backend --extra local-ocr pytest -q backend/tests/local_ocr

p4-local-ocr-smoke:
	@set -eu; \
	root="$(PWD)"; \
	temp_root=$$(mktemp -d "$${TMPDIR:-/tmp}/hyc-local-ocr-smoke.XXXXXX"); \
	cleanup() { if [ -d "$$temp_root" ]; then find "$$temp_root" -depth -delete; fi; test ! -e "$$temp_root"; }; \
	trap cleanup EXIT INT TERM; \
	XDG_CACHE_HOME="$$root/.local-ocr-models/cache" uv run --offline --frozen --project backend --extra local-ocr python backend/scripts/run_local_ocr_smoke.py --models-root "$$root/.local-ocr-models/models" --output "$$temp_root/one.json"; \
	XDG_CACHE_HOME="$$root/.local-ocr-models/cache" uv run --offline --frozen --project backend --extra local-ocr python backend/scripts/run_local_ocr_smoke.py --models-root "$$root/.local-ocr-models/models" --output "$$temp_root/two.json"; \
	cmp "$$temp_root/one.json" "$$temp_root/two.json"; \
	python3 -c 'import hashlib,json,pathlib,sys; p=pathlib.Path(sys.argv[1]); data=json.loads(p.read_text()); print("p4-local-ocr-smoke: output=" + hashlib.sha256(p.read_bytes()).hexdigest() + " aggregate=" + data["aggregate_sha256"] + " headers=" + data["required_header_accuracy"] + " numeric=" + data["numeric_accuracy"] + " review=" + data["review_trigger_exposure"] + " init_network=" + str(data["initialization_network_attempt_count"]) + " predict_network=" + str(data["prediction_network_attempt_count"]))' "$$temp_root/one.json"

secret-scan:
	python3 scripts/scan_secrets.py

sensitive-documents-check:
	python3 scripts/check_sensitive_documents.py

check: contracts-check backend-check frontend-check migration-check secret-scan sensitive-documents-check
	docker compose config --quiet
