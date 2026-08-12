#!/usr/bin/env sh
set -eu

usage() {
  echo "usage: HYC_P6_DISPOSABLE=1 $0 --database-url URL --storage-root PATH --output-dir PATH" >&2
  exit 2
}

database_url=${DATABASE_URL:-}
storage_root=${P6_STORAGE_ROOT:-}
output_dir=${P6_BACKUP_OUTPUT_DIR:-}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --database-url) database_url=${2:-}; shift 2 ;;
    --storage-root) storage_root=${2:-}; shift 2 ;;
    --output-dir) output_dir=${2:-}; shift 2 ;;
    *) usage ;;
  esac
done

[ "${HYC_P6_DISPOSABLE:-}" = "1" ] || { echo "backup: HYC_P6_DISPOSABLE=1 is required" >&2; exit 2; }
[ -n "$database_url" ] && [ -n "$storage_root" ] && [ -n "$output_dir" ] || usage
[ -d "$storage_root" ] || { echo "backup: storage root does not exist: $storage_root" >&2; exit 2; }

postgres_url=$(python3 - "$database_url" "hyc_p6_disposable_" <<'PY'
import sys
from urllib.parse import unquote, urlsplit, urlunsplit

url, prefix = sys.argv[1:]
parts = urlsplit(url)
database = unquote(parts.path.lstrip("/").split("/", 1)[0])
if parts.scheme not in {"postgresql", "postgresql+psycopg"}:
    raise SystemExit("backup: database URL must use postgresql or postgresql+psycopg")
if (parts.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("backup: disposable database URL must use a loopback host")
if not database.startswith(prefix):
    raise SystemExit(f"backup: disposable database name must start with {prefix}")
print(urlunsplit(("postgresql", parts.netloc, parts.path, parts.query, parts.fragment)))
PY
)

for command in pg_dump psql tar python3; do
  command -v "$command" >/dev/null 2>&1 || { echo "backup: required command not found: $command" >&2; exit 2; }
done

if find "$storage_root" -type l -print -quit | grep -q .; then
  echo "backup: symlinks in storage are not supported" >&2
  exit 2
fi
if find "$storage_root" ! -type d ! -type f -print -quit | grep -q .; then
  echo "backup: storage contains an unsupported file type" >&2
  exit 2
fi

if [ -e "$output_dir" ]; then
  [ -d "$output_dir" ] || { echo "backup: output path is not a directory: $output_dir" >&2; exit 2; }
else
  mkdir -p "$output_dir"
fi
[ -z "$(find "$output_dir" -mindepth 1 -maxdepth 1 -print -quit)" ] || { echo "backup: output directory must be empty" >&2; exit 2; }

temp_root=$(mktemp -d "${TMPDIR:-/tmp}/hyc-p6-backup.XXXXXX")
cleanup() {
  if [ -d "$temp_root" ]; then find "$temp_root" -depth -delete; fi
  test ! -e "$temp_root"
}
trap cleanup EXIT INT TERM

pg_dump --dbname "$postgres_url" --format=custom --no-owner --no-privileges --file "$temp_root/database.dump"
tar -C "$storage_root" -czf "$temp_root/storage.tar.gz" .

python3 - "$postgres_url" "$storage_root" "$temp_root/manifest.json" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

database_url, storage_root, manifest_path = sys.argv[1:]

def psql(query: str) -> str:
    result = subprocess.run(
        ["psql", "--dbname", database_url, "--no-psqlrc", "--tuples-only", "--no-align", "--quiet", "--command", query],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout

relations = [
    line
    for line in psql(
        "SELECT quote_ident(schemaname) || '.' || quote_ident(tablename) "
        "FROM pg_catalog.pg_tables "
        "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') "
        "ORDER BY schemaname, tablename"
    ).splitlines()
    if line
]
tables = []
for relation in relations:
    count = psql(f"SELECT count(*) FROM {relation}").strip()
    tables.append({"name": relation, "row_count": int(count)})

root = Path(storage_root)
files = []
for path in sorted(root.rglob("*")):
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        files.append({"path": path.relative_to(root).as_posix(), "sha256": digest.hexdigest()})
    elif not path.is_dir():
        raise SystemExit(f"backup: unsupported storage entry: {path}")

Path(manifest_path).write_text(
    json.dumps({"format_version": 1, "tables": tables, "files": files}, ensure_ascii=True, indent=2) + "\n",
    encoding="utf-8",
)
PY

mv "$temp_root/database.dump" "$temp_root/storage.tar.gz" "$temp_root/manifest.json" "$output_dir/"
echo "backup: wrote database.dump, storage.tar.gz, manifest.json"
