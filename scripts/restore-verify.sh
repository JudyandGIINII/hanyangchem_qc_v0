#!/usr/bin/env sh
set -eu

usage() {
  echo "usage: HYC_P6_DISPOSABLE=1 $0 --database-url URL --storage-root PATH --backup-dir PATH" >&2
  exit 2
}

database_url=${RESTORE_DATABASE_URL:-${DATABASE_URL:-}}
storage_root=${P6_RESTORE_STORAGE_ROOT:-${P6_STORAGE_ROOT:-}}
backup_dir=${P6_BACKUP_DIR:-}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --database-url) database_url=${2:-}; shift 2 ;;
    --storage-root) storage_root=${2:-}; shift 2 ;;
    --backup-dir) backup_dir=${2:-}; shift 2 ;;
    *) usage ;;
  esac
done

[ "${HYC_P6_DISPOSABLE:-}" = "1" ] || { echo "restore-verify: HYC_P6_DISPOSABLE=1 is required" >&2; exit 2; }
[ -n "$database_url" ] && [ -n "$storage_root" ] && [ -n "$backup_dir" ] || usage
[ -d "$storage_root" ] || { echo "restore-verify: storage root does not exist: $storage_root" >&2; exit 2; }
[ -d "$backup_dir" ] || { echo "restore-verify: backup directory does not exist: $backup_dir" >&2; exit 2; }
for path in "$backup_dir/database.dump" "$backup_dir/storage.tar.gz" "$backup_dir/manifest.json"; do
  [ -f "$path" ] || { echo "restore-verify: required backup file is missing: $path" >&2; exit 2; }
done

postgres_url=$(python3 - "$database_url" "hyc_p6_restore_" <<'PY'
import sys
from urllib.parse import unquote, urlsplit, urlunsplit

url, prefix = sys.argv[1:]
parts = urlsplit(url)
database = unquote(parts.path.lstrip("/").split("/", 1)[0])
if parts.scheme not in {"postgresql", "postgresql+psycopg"}:
    raise SystemExit("restore-verify: database URL must use postgresql or postgresql+psycopg")
if (parts.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("restore-verify: disposable database URL must use a loopback host")
if not database.startswith(prefix):
    raise SystemExit(f"restore-verify: disposable database name must start with {prefix}")
print(urlunsplit(("postgresql", parts.netloc, parts.path, parts.query, parts.fragment)))
PY
)

for command in pg_restore psql tar python3 diff; do
  command -v "$command" >/dev/null 2>&1 || { echo "restore-verify: required command not found: $command" >&2; exit 2; }
done

[ -z "$(find "$storage_root" -mindepth 1 -maxdepth 1 -print -quit)" ] || { echo "restore-verify: storage root must be empty" >&2; exit 2; }
table_count=$(psql --dbname "$postgres_url" --no-psqlrc --tuples-only --no-align --quiet --command "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')" | tr -d '[:space:]')
[ "$table_count" = "0" ] || { echo "restore-verify: restore database must contain no user tables" >&2; exit 2; }

python3 - "$backup_dir/storage.tar.gz" <<'PY'
import sys
import tarfile
from pathlib import PurePosixPath

with tarfile.open(sys.argv[1], "r:gz") as archive:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f"restore-verify: unsafe storage archive member: {member.name}")
PY

temp_root=$(mktemp -d "${TMPDIR:-/tmp}/hyc-p6-restore.XXXXXX")
cleanup() {
  if [ -d "$temp_root" ]; then find "$temp_root" -depth -delete; fi
  test ! -e "$temp_root"
}
trap cleanup EXIT INT TERM

pg_restore --dbname "$postgres_url" --exit-on-error --no-owner --no-privileges "$backup_dir/database.dump"
tar -C "$storage_root" -xzf "$backup_dir/storage.tar.gz"

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
        raise SystemExit(f"restore-verify: unsupported storage entry: {path}")

Path(manifest_path).write_text(
    json.dumps({"format_version": 1, "tables": tables, "files": files}, ensure_ascii=True, indent=2) + "\n",
    encoding="utf-8",
)
PY

diff -u "$backup_dir/manifest.json" "$temp_root/manifest.json"
echo "restore-verify: manifest diff passed"
