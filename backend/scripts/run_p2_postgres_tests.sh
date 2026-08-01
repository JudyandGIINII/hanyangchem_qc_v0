#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$root"
if [ -n "${HYC_P2_TEST_POSTGRES_PORT:-}" ]; then
  port="$HYC_P2_TEST_POSTGRES_PORT"
else
  port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
fi
export HYC_P2_TEST_POSTGRES_PORT="$port"
project="hyc-p2-test-$(date +%s)-$$"
compose_file="$root/compose.p2-test.yaml"

cleanup() {
  docker compose -p "$project" -f "$compose_file" down --volumes --remove-orphans >/dev/null 2>&1 || true
  test -z "$(docker ps -aq --filter "label=com.docker.compose.project=$project")"
  test -z "$(docker network ls -q --filter "label=com.docker.compose.project=$project")"
  test -z "$(docker volume ls -q --filter "label=com.docker.compose.project=$project")"
}
trap cleanup EXIT INT TERM

docker compose -p "$project" -f "$compose_file" up --detach --wait
owner_dsn="postgresql+psycopg://p2_test:TEST_FIXTURE_ONLY_P2_OWNER_PASSWORD@127.0.0.1:${port}/hyc_p2_test"
app_dsn="postgresql+psycopg://hyc_app_test:TEST_FIXTURE_ONLY_P2_APP_PASSWORD@127.0.0.1:${port}/hyc_p2_test"
HYC_APP_ROLE=hyc_app_test \
HYC_P2_TEST_POSTGRES_DSN="$owner_dsn" \
HYC_P2_TEST_APP_DSN="$app_dsn" \
  uv run --project "$root/backend" pytest -q -m postgres "$root/backend/tests/integration/db/test_p2_postgres_invariants.py"
uv run --project "$root/backend" python "$root/backend/scripts/check_migrations.py" --postgres-url "$owner_dsn"
