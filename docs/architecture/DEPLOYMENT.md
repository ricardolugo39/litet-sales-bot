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
INVENTORY_APP_URL=https://<inventory-service>.up.railway.app
ADMIN_UPLOAD_TOKEN=<same value as Railway>
```

Keep real values in `.env`; never commit them.

## Update workflow

1. Download Seller Central files into the existing OneDrive `Raw/incoming`
   directory.
2. Run `python scripts/update_and_sync.py`.
3. The established `update_all.py` pipeline imports the files and rebuilds
   Stage 1 dimensions/fees, Stage 2 profitability, and Stage 3 PPC analytics
   in dependency order. Placeholder-seed costs remain unverified assumptions
   until replaced by documented vendor receipts.
4. The synchronization command validates the complete SQLite database, sends a
   gzip-compressed snapshot over HTTPS to the decision dashboard and, when
   `INVENTORY_APP_URL` is set, to the inventory app, then refreshes the offline
   cache.
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

## Rebuilding payment lifecycle fees

A Deferred Order Payment and its later Released version are one payment even
when their dates differ. Stage 1 matches equal order IDs, product details and
normalized monetary components one-to-one, retaining the Released record and
its date. Separate Released payments, refunds, unmatched Deferred payments and
nonmatching amounts remain separate. Without a payment identifier, ambiguous
extra records are retained rather than silently deleted.

To rebuild fee-dependent marts without changing raw sources, dimensions, or
COGS, run:

```sh
python scripts/rebuild_fee_analytics.py original.db rebuilt.db
```

The destination must be new. The command rebuilds transactions, fee ledger and
reconciliation, sales profitability, and dependent PPC contribution metrics.
It validates the resulting database before it can be uploaded using the normal
snapshot workflow. Preserve the original database for rollback; review the
matched-date comparison before publishing the rebuilt candidate.
