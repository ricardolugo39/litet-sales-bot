# Decision Dashboard deployment

## Runtime model

Railway runs one dashboard instance and mounts a persistent volume at `/data`.
The canonical writable database is `/data/litet.db`. Local applications use the
latest downloaded cache when offline; the cache is not a source of truth.

Railway builds the root `Dockerfile`, which intentionally installs only
`decision_dashboard_v2/requirements.txt`. The repository-wide requirements are
reserved for the other local applications and are not part of this service.

Required Railway variables:

```text
LITET_DB_PATH=/data/litet.db
HASTEN_DECISION_DB=/data/litet.db
ADMIN_UPLOAD_TOKEN=<long random value>
```

Required local synchronization variables:

```text
LITET_DB_PATH=/Users/.../Reports/SQLite/litet.db
LITET_OFFLINE_CACHE=/Users/.../offline_cache/litet.db
DASHBOARD_URL=https://<service>.up.railway.app
ADMIN_UPLOAD_TOKEN=<same value as Railway>
```

Keep real values in `.env`; never commit them.

## Update workflow

1. Download Seller Central files into the existing OneDrive `Raw/incoming`
   directory.
2. Run `python scripts/update_and_sync.py`.
3. The established `update_all.py` pipeline imports the files and rebuilds PPC
   analytics.
4. The synchronization command validates the complete SQLite database, sends a
   gzip-compressed snapshot over HTTPS, and refreshes the offline cache.
5. Railway validates the candidate database and atomically replaces the
   canonical file. Existing intervention records are copied into the candidate
   before replacement.

The upload refuses databases that fail SQLite integrity checks or omit required
dashboard tables.

## Initial deployment

1. Create a Railway service from this GitHub repository.
2. Mount a persistent volume at `/data`.
3. Set the required variables above.
4. Deploy. The health check will remain unavailable until the initial database
   is uploaded.
5. Set the local variables and run `python scripts/sync_database.py` to perform
   the first upload.
6. Confirm `/health` returns `{"status":"ok"}`.

## Recovery

The local source database and offline cache provide recoverable snapshots. To
restore Railway, point `LITET_DB_PATH` locally at the desired validated snapshot
and rerun `scripts/sync_database.py`. The current Railway intervention table is
preserved during restoration.
