# Backup and restore rehearsal

P6-7 creates a PostgreSQL logical dump and a compressed archive of one file-storage root. It is intentionally constrained to disposable local PostgreSQL databases: backup URLs must name `hyc_p6_disposable_*`, restore URLs must name `hyc_p6_restore_*`, both must use a loopback host, and `HYC_P6_DISPOSABLE=1` is required.

Run the complete rehearsal from the repository root:

```sh
COMPOSE_BAKE=0 DOCKER_BUILDKIT=0 make p6-backup-restore-verify
```

The Make target starts a uniquely named disposable Compose PostgreSQL, migrates a disposable source database, places a non-empty probe file in a temporary storage root, and runs the two commands below. Its EXIT/INT/TERM trap removes its Compose containers, network, volumes, and all temporary paths.

To create a backup yourself, provide only a disposable source URL and an empty caller-supplied output directory:

```sh
HYC_P6_DISPOSABLE=1 scripts/backup.sh \
  --database-url "$DATABASE_URL" \
  --storage-root "$P6_STORAGE_ROOT" \
  --output-dir "$P6_BACKUP_OUTPUT_DIR"
```

This writes `database.dump` (a PostgreSQL custom-format logical dump), `storage.tar.gz`, and `manifest.json`. The manifest proves that every user table has the same row count after restoration and that every regular stored file has the same relative path and SHA-256 digest. It does not prove semantic correctness beyond those checks, nor validate database roles, external services, application configuration, or a recovery into a non-disposable environment.

Rehearse a backup against an existing empty disposable database and storage directory:

```sh
HYC_P6_DISPOSABLE=1 scripts/restore-verify.sh \
  --database-url "$RESTORE_DATABASE_URL" \
  --storage-root "$P6_RESTORE_STORAGE_ROOT" \
  --backup-dir "$P6_BACKUP_DIR"
```

`restore-verify.sh` refuses a restore database that already has user tables, restores the dump and archive, recomputes the manifest, and runs a unified diff. Any restore, archive, row-count, path, or digest mismatch exits non-zero; success prints `restore-verify: manifest diff passed`.

No retention period, expiry rule, or deletion rule is defined: RET-001 and AP-08 are unapproved. This slice does not add scheduling or cron, target a production database, claim any RPO or RTO, define restoration authorization, or constitute a production backup policy.
