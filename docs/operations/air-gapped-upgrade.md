# Air-Gapped Upgrade Without Data Loss

This guide explains how to upgrade an existing air-gapped Tomorrowland deployment
with a newer release artifact while preserving operator configuration and
persistent product data.

> **Never run `docker compose down -v` during an upgrade.** The `-v` flag deletes
> named volumes, including PostgreSQL, Elasticsearch, Qdrant, files, model, and
> broker data.

The upgrade invariant is simple: **replace images and run migrations; never
replace, delete, or recreate data volumes by default.**

## Prerequisites

- An existing Tomorrowland air-gapped deployment directory containing `.env` and the
  active Compose file, usually `docker-compose.airgap.yml`.
- Docker Engine and Docker Compose plugin already installed on the target host.
  The release manifest declares the minimum expected versions.
- A newer extracted `tomorrowland-release-<version>/` artifact copied to the
  air-gapped host.
- Enough free disk space for:
  - the new image bundle,
  - a PostgreSQL dump,
  - a files volume archive,
  - optional storage-level snapshots of Elasticsearch and Qdrant volumes,
  - the compressed Ollama model bundle and expanded model blobs when replacing
    the configured model.
- A maintenance window. Database migrations run before the upgraded API starts.

Do not perform the upgrade from inside a fresh artifact directory unless that is
also the long-lived deployment directory that contains the current `.env` and
volumes. Most operators should run upgrade commands from the existing deployment
directory and pass `--artifact-dir ../tomorrowland-release-<version>`.

## What data is preserved

The upgrade scripts preserve Docker volumes and operator configuration by
default. This includes:

- PostgreSQL metadata and application data: users, groups, permissions, source
  connector configuration, LDAP-related configuration, documents metadata,
  comments, annotations, subscriptions, notifications, activity, translations,
  summaries, entities, tags, DLQ, and audit records.
- `files_data`, containing ingested files and document storage under `FILES_ROOT`.
- Elasticsearch index data in `elasticsearch_data`.
- Qdrant vector data in `qdrant_data`.
- Redpanda/Kafka data in `kafka_data`.
- LibreTranslate and Ollama volumes.
- Optional monitoring data when the operator backs up monitoring volumes.
- `.env` and local Compose overrides.

Volume names are determined by `TOMORROWLAND_*_VOLUME` values in `.env`. Keep
these values stable across upgrades so Compose continues to mount the same
Docker volumes. If a volume name changes, Compose creates a new empty volume
with the new name and the existing data remains in the old volume. Migrate data
explicitly if you must rename volumes.

## Translation language pack upgrade notes

The `tomorrowland/libretranslate:airgap` image bundles Argos Translate language packs
at build time. When upgrading to a new release artifact:

- The new `tomorrowland/libretranslate:airgap` image in the artifact may include
  additional or updated language packs compared to the previous release.
- The `libretranslate_data` named volume persists across upgrades and retains
  packages from the previous image. On first startup after image replacement,
  Docker does not automatically merge new image packages into an existing volume.
- If you need to apply updated packages from the new image to an existing volume,
  stop the stack, remove only the `libretranslate_data` volume (this deletes
  cached translations but not document metadata), and restart. Docker will then
  copy the new image's packages into the empty volume.
- Before removing the volume, confirm that `postgres_data`, `files_data`,
  `elasticsearch_data`, and `qdrant_data` are all intact. Never use
  `docker compose down -v` during an upgrade.
- After startup, validate language support with:

  ```bash
  LIBRETRANSLATE_URL=http://localhost:5000 bash scripts/validate-translation-languages.sh
  ```

The scripts do not intentionally delete or recreate these volumes.

## Ollama model bundle upgrade notes

Ollama model bundles are optional release assets separate from the platform
archive. Reload the model bundle when any of these are true:

- the deployment has no existing `ollama_data` model for the configured
  `OLLAMA_MODEL`,
- release notes instruct operators to use a new default model/digest,
- the operator changes `OLLAMA_MODEL` in `.env`, or
- the operator's model approval process requires replacing the existing bundle.

If the existing model is already approved and the configured model name has not
changed, you can verify it instead of reloading:

```bash
OLLAMA_URL=http://localhost:${OLLAMA_PORT:-11434} \
OLLAMA_MODEL=${OLLAMA_MODEL:-mistral} \
bash scripts/validate-ollama-model.sh
```

To replace or upgrade the model safely:

1. Verify the transferred bundle checksum on the air-gapped host:

   ```bash
   sha256sum -c tomorrowland-ollama-bundle-mistral-<version>.tar.gz.sha256
   ```

2. Review `model-manifest.json` after extracting or by validating the bundle;
   confirm requested/resolved model, digest, runtime image/version, file
   checksums, and license/source/attribution metadata.
3. Set `OLLAMA_MODEL` in `.env` to the model recorded in the bundle manifest.
4. Load the bundle into the existing deployment volume:

   ```bash
   bash ../tomorrowland-release-<version>/scripts/load-ollama-model-bundle.sh \
     --bundle ../tomorrowland-ollama-bundle-mistral-<version>.tar.gz \
     --compose-file docker-compose.airgap.yml \
     --env-file .env
   ```

5. Validate availability, and optionally run a smoke test:

   ```bash
   OLLAMA_URL=http://localhost:${OLLAMA_PORT:-11434} \
   OLLAMA_MODEL=${OLLAMA_MODEL:-mistral} \
   bash ../tomorrowland-release-<version>/scripts/validate-ollama-model.sh --smoke-test
   ```

The load script is intentionally non-destructive: it merges bundled `models/`
files into `ollama_data`, stops/restarts only the Ollama service when needed, and
never runs `docker compose down -v`. Do not delete or recreate `ollama_data`
casually; it may contain an operator-approved model, locally cached blobs, or a
previous working model needed for rollback. If you must remove obsolete model
blobs later, do so only after backing up the volume and confirming the new model
passes validation.

## What the backup script captures

`scripts/backup-airgap-data.sh` (from the newer release artifact, or from the deployment directory after an upgrade installs helper scripts) creates a timestamped directory under `backups/`
by default. It captures:

- `.env`.
- Active Compose files and local override files.
- Rendered Compose configuration, image references, service state, Docker
  version, Compose version, and current volumes metadata.
- A PostgreSQL custom-format dump from the running `postgres` service.
- A compressed archive of the `files_data` named volume.
- Notes describing safe Elasticsearch and Qdrant backup/restore strategy.
- Notes for optional monitoring data if a monitoring profile or override exists.

Elasticsearch and Qdrant live snapshot repositories are deployment-specific, so
the script does not attempt to configure them automatically. For high-risk
upgrades, stop services without deleting volumes and take storage-level snapshots
or offline archives of `elasticsearch_data` and `qdrant_data` before continuing.

## Required commands before upgrade

On the connected machine, verify the downloaded archive checksum before moving it
to the air-gapped host:

```bash
sha256sum -c tomorrowland-release-<version>.tar.gz.sha256
```

On the air-gapped host, extract the release artifact near the deployment
directory:

```bash
tar xzf tomorrowland-release-<version>.tar.gz
```

From the existing deployment directory, confirm `.env` still contains the current
operator settings. The upgrade flow never overwrites `.env` automatically.

## Artifact checksum verification

If `checksums.txt` is present in the extracted artifact, the preflight script
verifies it. You can also verify manually:

```bash
cd tomorrowland-release-<version>
sha256sum -c checksums.txt
```

## Preflight command

Run preflight from the existing deployment directory:

```bash
../tomorrowland-release-<version>/scripts/preflight-upgrade-check.sh --artifact-dir ../tomorrowland-release-<version>
```

The `tomorrowland-airgap.sh upgrade` command also runs preflight automatically
as the first step (see Upgrade command below).

The preflight check is read-only. It validates the deployment directory, `.env`,
Compose files, Docker Engine, Docker Compose plugin, current service state,
current image tags, expected persistent volume names, configured folder-source
host path existence, artifact checksums, required artifact files,
`release-manifest.json`, air-gapped Compose rendering, absence of required
`build:` steps, and that every image referenced by the artifact Compose file is
bundled or already present locally. Artifact validation also rejects obvious
non-placeholder secrets in packaged environment templates.

Stop and resolve any preflight failure before continuing.

## Backup command

Create a backup from the existing deployment directory:

```bash
../tomorrowland-release-<version>/scripts/backup-airgap-data.sh --output-dir ./backups
```

The backup script fails closed: if PostgreSQL dumping or files archiving fails,
the script exits non-zero and leaves a partial backup marked with `FAILED.txt`
for inspection. Do not proceed with the upgrade until a complete backup contains
`SUCCESS.txt`.

For Elasticsearch and Qdrant, use the backup notes as the safe fallback:

```bash
docker compose --env-file .env -f docker-compose.airgap.yml stop
# take storage-level snapshots or offline archives of elasticsearch_data and qdrant_data
docker compose --env-file .env -f docker-compose.airgap.yml up -d
```

Do not add `-v` to any Compose stop or down command.

## Image loading command

The upgrade orchestrator loads images automatically, but you can load them
manually when validating an artifact:

```bash
cd ../tomorrowland-release-<version>
./scripts/tomorrowland-airgap.sh load-images
```

This auto-detects split image parts beside the release directory or the legacy
embedded `images/tomorrowland-images.tar`. It does not pull from the internet
and does not build images on the target host. To specify a custom location for
image parts:

```bash
./scripts/tomorrowland-airgap.sh load-images --image-parts-dir /media/usb/images
```

## Upgrade command

The primary upgrade command uses the wrapper script. Run from the **existing
deployment directory** (not the new artifact directory):

```bash
../tomorrowland-release-<version>/scripts/tomorrowland-airgap.sh upgrade \
  --artifact-dir ../tomorrowland-release-<version>
```

Or equivalently using the lower-level orchestrator directly:

```bash
../tomorrowland-release-<version>/scripts/upgrade-airgap.sh --artifact-dir ../tomorrowland-release-<version>
```

The orchestrator performs the following steps:

1. Runs the read-only preflight check.
2. Runs `scripts/backup-airgap-data.sh` unless `--skip-backup` is explicitly
   provided.
3. Loads images from the local release artifact.
4. Verifies every expected image tag exists locally.
5. Copies the new release Compose files into the deployment directory while
   preserving `.env`.
6. Stops services with `docker compose stop`, preserving all volumes.
7. Starts PostgreSQL and runs the `migrate` service/job.
8. Stops immediately if migrations fail.
9. Starts the upgraded stack.
10. Runs basic `/health` checks when `curl` is available.

Use `--skip-backup` only when you have already created and verified an equivalent
backup outside this script:

```bash
../tomorrowland-release-<version>/scripts/tomorrowland-airgap.sh upgrade \
  --artifact-dir ../tomorrowland-release-<version> --skip-backup
```

## Migration behavior

The air-gapped Compose file includes a `migrate` service that runs:

```bash
alembic upgrade head
```

The upgrade script starts PostgreSQL, runs this migration job, and refuses to
start the upgraded stack if migrations fail. This prevents the API and frontend
from running against a partially migrated database.


## Host-mounted SMB shares during upgrades

Host-mounted SMB/CIFS shares are external host state; they are not packaged
inside Tomorrowland release artifacts and are not recreated by the upgrade scripts.
If an existing deployment uses an SMB share through the `folder` connector, keep
both the host mount path, such as `/mnt/tomorrowland-smb/legal`, and the container
path, such as `/data/smb/legal`, stable across upgrades so existing source
configuration continues to work.

Before starting the upgraded stack in the #75 upgrade flow, remount or verify the
SMB share on the host:

```bash
mount | grep /mnt/tomorrowland-smb/legal
ls -la /mnt/tomorrowland-smb/legal
```

Back up `/etc/fstab` or the equivalent systemd mount configuration and the
root-owned SMB credential file outside Tomorrowland. Do not store real SMB
credentials in `.env`, release artifacts, Compose examples, documentation, or
screenshots. Do not use destructive volume commands to fix SMB mount issues;
repair the host mount, verify the `api` service bind mount, and then restart the
stack without deleting Tomorrowland volumes.

## Post-upgrade validation checklist

Complete this checklist before declaring the upgrade successful:

- API `GET /health` responds.
- Admin `GET /admin/readiness` responds for an admin user.
- Frontend is reachable.
- Login works.
- Existing admin users and groups are visible.
- Existing source connectors are visible.
- At least one existing document can be searched.
- At least one existing document can be previewed.
- Ollama model validation passes when Q&A/RAG/local intelligence is expected:
  `OLLAMA_MODEL=${OLLAMA_MODEL:-mistral} bash scripts/validate-ollama-model.sh`.
- Q&A route responds if enabled and the configured Ollama model is loaded.
- Comments and annotations remain visible if present.
- Subscriptions and notifications remain visible if present.
- PostgreSQL is not unexpectedly empty.
- Existing files are still present; no volume appears to have been recreated.
- Elasticsearch and Qdrant indexes are populated or rebuild behavior is understood
  and expected.

Useful commands:

```bash
docker compose --env-file .env -f docker-compose.airgap.yml ps
curl -fsS http://127.0.0.1:${API_PORT:-8000}/health
curl -fsS http://127.0.0.1:${FRONTEND_PORT:-8080}/health
```

## Restore and rollback procedure

If preflight, image loading, or backup fails, no runtime data should have changed.
Fix the failure and rerun preflight.

If migration or post-upgrade validation fails:

1. Do **not** run `docker compose down -v`.
2. Stop services without deleting volumes:

   ```bash
   docker compose --env-file .env -f docker-compose.airgap.yml stop
   ```

3. Restore the backup created before upgrade:

   ```bash
   scripts/restore-airgap-data.sh --backup-dir ./backups/tomorrowland-airgap-backup-<timestamp> --confirm-restore
   ```

4. Restore Elasticsearch and Qdrant storage snapshots if you created them.
5. Start the restored stack:

   ```bash
   docker compose --env-file .env -f docker-compose.airgap.yml up -d
   ```

The restore script intentionally requires `--confirm-restore`. It restores `.env`,
backed-up Compose files, the PostgreSQL dump, and the `files_data` archive. It
prints warnings before replacing database and files-volume contents. It does not
automate Elasticsearch or Qdrant snapshot restore; follow the notes in the backup
directory for those volumes.

## Common failure modes

| Failure | Safe response |
| --- | --- |
| Missing `.env` | Stop. Run from the existing deployment directory or restore `.env` from backup. |
| Missing `release-manifest.json` | Stop. The artifact is not compatible with this upgrade workflow. Use a #73-style artifact. |
| Checksum failure | Stop. Re-copy or re-download the artifact from the connected environment. |
| Compose config contains `build:` | Stop. Use the air-gapped Compose file from the release artifact; do not build on the target host. |
| Image missing after load | Stop. The artifact image bundle is incomplete or failed to load. |
| Ollama model missing | Continue only if local Q&A/RAG degradation is acceptable; otherwise load the matching model bundle and run `scripts/validate-ollama-model.sh`. |
| PostgreSQL dump fails | Stop. Do not upgrade without a successful database backup. |
| Files archive fails | Stop. Do not upgrade without a successful files backup or equivalent storage snapshot. |
| Migration fails | Stop. Do not start the upgraded API/frontend; restore from backup or investigate migration logs. |
| Health check fails | Keep volumes intact, inspect logs, and roll back if validation cannot be completed. |

## Compatibility notes between versions

- Upgrade only with release artifacts that include `release-manifest.json`,
  `docker-compose.airgap.yml`, checksums, upgrade scripts, and either split
  `tomorrowland-images-<version>.tar.part-*` files or the legacy embedded
  `images/tomorrowland-images.tar`.
- Review `release-manifest.json` before upgrade. Confirm the expected release
  version, commit SHA, Compose files, minimum Docker and Compose versions,
  migration expectation, persistent volumes, and backup/restore script version.
- Database migrations are expected to be forward migrations. Rollback requires a
  pre-upgrade backup; do not assume database schema downgrades are available.
- If persistent volume names change in a future release, stop and perform a
  manual migration plan rather than letting Compose create new empty volumes.

## Recovering when validation fails

- Keep services stopped or running as-is; do not delete volumes.
- Save logs for review:

  ```bash
  docker compose --env-file .env -f docker-compose.airgap.yml logs --no-color > upgrade-failure.log
  ```

- Check whether the failure is configuration-only, such as a port conflict or an
  incorrect `.env` value. Correct `.env` manually; scripts never overwrite it.
- If data appears missing, assume a wrong project name or volume path before
  assuming data loss. Inspect `docker volume ls` and the backup metadata.
- If validation cannot be repaired quickly, restore the pre-upgrade backup and
  Elasticsearch/Qdrant snapshots.

## Follow-up limitation text

Elasticsearch and Qdrant snapshot automation remains deployment-specific. A
follow-up issue should add optional, operator-configured snapshot repository
support that can validate a repository path, trigger snapshots, and restore them
without storing credentials or host-specific paths in release artifacts.
