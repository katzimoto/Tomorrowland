# tomorrowland

Tomorrowland is a local-first knowledge intelligence system for private document
corpora. The canonical product spec is `spec-v4.pdf`.

## How To Run

Tomorrowland includes a production-style Docker Compose runtime. It starts the API,
frontend container, migration job, and required infrastructure as separate
services.

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` before using real data. At minimum, change:

   - `POSTGRES_PASSWORD`
   - `POSTGRES_URL` so it uses the same password
   - `JWT_SECRET`

3. Start the local product:

   ```bash
   docker compose up --build
   ```

4. Open the runtime:

   - Frontend: `http://localhost:8080`
   - API health: `http://localhost:8000/health`
   - Frontend health: `http://localhost:8080/health`

Useful commands:

```bash
docker compose config
docker compose run --rm migrate
docker compose logs -f api frontend migrate
docker compose down
# Destructive reset only; never use during upgrades because it deletes volumes.
docker compose down -v
```

See `docs/operations/production-compose.md` for the full operations guide,
including service layout, annotated environment variables, reset behavior,
backup and restore guidance, health checks, troubleshooting, and current
limitations.

## Air-Gapped Release Artifact

Tomorrowland also publishes a versioned release archive for offline Compose
deployments. The archive includes prebuilt first-party images, required
third-party runtime images, an air-gapped Compose file with no build steps, an
operator `.env` template, validation/loading scripts, checksums, and deployment
documentation.

Connected release operator flow:

```bash
# Download tomorrowland-release-<version>.tar.gz and its .sha256 from GitHub
sha256sum -c tomorrowland-release-<version>.tar.gz.sha256
```

Air-gapped host flow:

```bash
tar xzf tomorrowland-release-<version>.tar.gz
cd tomorrowland-release-<version>
bash scripts/validate-airgap-artifact.sh .
bash scripts/load-airgap-images.sh .
cp .env.airgap.example .env
# edit .env secrets, ports, storage paths, LDAP, and connector mount settings
docker compose --env-file .env -f docker-compose.airgap.yml up -d
```

See `docs/operations/air-gapped-deployment.md` for the complete
download-to-first-use guide, including folder, Atlassian, SMB, and NiFi
event-ingestion setup, local users/groups, LDAP, health checks, backup,
restore, and current limitations. For existing offline
deployments, follow `docs/operations/air-gapped-upgrade.md` to load a newer
release, run migrations, and preserve data volumes.

## NiFi Event Ingestion

Tomorrowland includes a release-usable, bounded NiFi Kafka drain for deployments
that already provide NiFi-produced Kafka events. Events are validated, normalized
into `nifi` documents tied to `ingestion_sources`, processed by the standard
pipeline, and routed to DLQ on terminal failures. The repository tests this path
with fakes only; there is no live NiFi/Kafka CI dependency and no dedicated
long-running worker container in this phase. See
`docs/operations/production-compose.md` for the required event envelope, staged
file requirements, DLQ behavior, offset semantics, and current limitations.

## Host-Mounted SMB Shares

Operators who already mount Windows/SMB shares on the Docker host can expose the
mounted path to Tomorrowland as a read-only bind mount and ingest it with the
existing `folder` connector. See `docs/operations/production-compose.md` for the
host-mounted SMB guide, including CIFS mount examples, read-only service-account
guidance, the container path to use in the `folder` source, and upgrade notes.
