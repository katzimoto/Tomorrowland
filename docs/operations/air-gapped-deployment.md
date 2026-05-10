# Air-Gapped Compose Deployment

This guide describes the release artifact path for installing Neverland on a
host that cannot reach the internet. The artifact contains the Compose files,
operator templates, validation scripts, documentation, checksums, and a Docker
image bundle with every first-party and third-party runtime image needed by the
default Compose deployment.

## Artifact Layout

A release archive is named `neverland-release-<version>.tar.gz` and extracts to:

```text
neverland-release-<version>/
  docker-compose.yml
  docker-compose.airgap.yml
  .env.airgap.example
  images/
    neverland-images.tar
  scripts/
    load-airgap-images.sh
    validate-airgap-artifact.sh
    preflight-upgrade-check.sh
    backup-airgap-data.sh
    restore-airgap-data.sh
    upgrade-airgap.sh
  docs/
    air-gapped-deployment.md
    air-gapped-upgrade.md
    production-compose.md
  release-manifest.json
  checksums.txt
  README-airgap.txt
```

`release-manifest.json` records the release version, commit, Compose files, image tags, minimum Docker/Compose versions, migration expectation, persistent data locations, and backup/restore script version.

Use `docker-compose.airgap.yml` for offline hosts. It contains only `image:`
references and does not require Docker builds. The root `docker-compose.yml` is
included for source traceability and connected environments that intentionally
build from source.

## Download And Transfer

1. From a connected workstation, download the archive from one of these release
   paths:
   - the `release-artifact` GitHub Actions workflow artifact for a manually
     triggered run; or
   - the GitHub Release assets for a `v*` tag when a tagged release is created.
2. Download the matching `neverland-release-<version>.tar.gz.sha256` file.
3. Verify the archive checksum before transfer:

   ```bash
   sha256sum -c neverland-release-<version>.tar.gz.sha256
   ```

4. Copy the verified `.tar.gz` file to the air-gapped host using approved
   removable media or an approved transfer gateway.

## Host Prerequisites

Install these prerequisites on the air-gapped host before extracting the
artifact:

- Docker Engine 24 or newer.
- Docker Compose plugin 2.20 or newer.
- Enough local disk for the image bundle, extracted images, named volumes,
  Elasticsearch/Qdrant indexes, uploaded files, translation cache, and Ollama
  model cache.
- Host firewall rules that expose only the intended frontend port. The
  air-gapped compose file binds the direct API port and infrastructure ports to
  `127.0.0.1` by default; browser API traffic should normally flow through the
  frontend proxy.

Confirm versions:

```bash
docker --version
docker compose version
```

## Extract And Validate The Artifact

Extract the archive and validate the packaged files:

```bash
tar xzf neverland-release-<version>.tar.gz
cd neverland-release-<version>
sha256sum -c checksums.txt
bash scripts/validate-airgap-artifact.sh .
```

The validation script fails if required files are missing, checksums do not
match, Compose cannot render the air-gapped file, a `build:` step appears in the
air-gapped Compose path, or a referenced image is not present in
`images/neverland-images.tar`.

## Load Images

Load the bundled Docker images:

```bash
bash scripts/load-airgap-images.sh .
```

Optionally re-run validation against the local Docker daemon:

```bash
bash scripts/validate-airgap-artifact.sh --load-images .
```

You can also inspect the required image list:

```bash
docker compose --env-file .env.airgap.example -f docker-compose.airgap.yml config --images
```

## Configure Environment

Create the runtime environment file:

```bash
cp .env.airgap.example .env
```

Edit `.env` before starting the product. At minimum:

- Replace `POSTGRES_PASSWORD` with a strong password.
- Update `POSTGRES_URL` so the password, user, host, port, and database match
  `POSTGRES_*`; the default service host remains `postgres`.
- Replace `JWT_SECRET` with a long random value and keep it stable after users
  are created.
- Confirm `FILES_ROOT=/data` unless you intentionally change the container
  storage path.
- Set `CORS_ORIGINS` to the exact browser origin, such as
  `http://neverland.example.local:8080`; do not use a wildcard.
- Set `API_PORT` and `FRONTEND_PORT` for the host ports operators should reach.
- Leave the direct API and infrastructure ports bound to localhost unless a
  maintenance workflow explicitly requires host access. Put any public access
  behind an approved reverse proxy and access control boundary.

The template contains placeholders only. Do not put real secrets back into the
release archive or commit them to source control.

## Configure Source Connectors

Source definitions are created after login from the admin UI or admin API. Store
connector credentials in the Neverland source configuration, not in the release
artifact.

### Folder Connector

The air-gapped compose file mounts a host folder into the API and migration
containers:

```env
NEVERLAND_FOLDER_SOURCE_HOST_PATH=./operator-data/folder-source
NEVERLAND_FOLDER_SOURCE_CONTAINER_PATH=/sources/folder
```

Create the host directory and copy source documents into it:

```bash
mkdir -p operator-data/folder-source
```

When adding a folder source in Neverland, use the container path from `.env`, for
example `/sources/folder`. Do not use the host path in the source definition;
the API runs inside the container.


### Host-Mounted SMB Shares

For Windows or Samba file shares, the recommended interim deployment path is to
mount the SMB/CIFS share on the Docker host and expose it to Neverland as a
read-only `folder` source. Use this path when operators already manage SMB
mounts at the OS level, SMB credentials should remain on the host instead of in
Neverland source configuration, a read-only ingestion path is sufficient, or the
native SMB connector tracked in #77 is unavailable or not preferred. This path is
independent from #77 and does not mirror NTFS ACLs; optional NTFS ACL sync is
tracked separately in #79.

On the air-gapped host, install CIFS tooling such as `cifs-utils` from approved
offline packages, then create and verify the host mount before starting
Neverland:

```bash
sudo mkdir -p /mnt/neverland-smb/legal
sudo mount -t cifs //fileserver/department /mnt/neverland-smb/legal \
  -o credentials=/etc/neverland/smb-legal.credentials,ro,vers=3.0,iocharset=utf8
```

Example credential file format, with placeholders only:

```ini
username=neverland-reader
password=REPLACE_WITH_SECRET
domain=CORP
```

Secure the host credential file and keep real SMB secrets out of the release
artifact, `.env`, Compose files, Git, docs, and screenshots:

```bash
sudo chown root:root /etc/neverland/smb-legal.credentials
sudo chmod 600 /etc/neverland/smb-legal.credentials
```

Optional `/etc/fstab` entry:

```fstab
//fileserver/department /mnt/neverland-smb/legal cifs credentials=/etc/neverland/smb-legal.credentials,ro,vers=3.0,iocharset=utf8,nofail 0 0
```

Verify the mount before starting or upgrading the stack:

```bash
mount | grep /mnt/neverland-smb/legal
ls -la /mnt/neverland-smb/legal
```

Add a read-only bind mount to the `api` service in a local Compose override,
using a stable container path such as `/data/smb/<source-name>`:

```yaml
services:
  api:
    volumes:
      - /mnt/neverland-smb/legal:/data/smb/legal:ro
```

The host source path must exist before `docker compose up`. Keep the host mount
path and container path stable across upgrades; the SMB mount is external host
state and is not packaged inside Neverland release artifacts.

Create the Neverland source with:

```text
Source type: folder
Path: /data/smb/legal
```

The `folder` connector sees the mounted SMB share as local files. The Neverland
source path must be the container path, not `/mnt/neverland-smb/legal` on the
host. Neverland source permissions control which groups can search and preview
indexed documents, while the SMB service account controls which files are visible
to the mount. Do not rely on Windows ACLs for per-user Neverland authorization
after ingestion.

Troubleshooting notes:

- If the container cannot see files, verify the host mount, the `api` service
  bind mount, and the rendered Compose config.
- If ingestion is empty, confirm the source uses the container path and that the
  mounted subtree contains regular files.
- If permission is denied, confirm the SMB service account, host mount
  permissions, and root-owned credential file permissions.
- If the mount disappears after reboot, validate `/etc/fstab` or the equivalent
  systemd mount before starting Neverland.
- If scans are slow, narrow the mounted subtree or source scope and check network
  and SMB server performance.

### Confluence Server/Data Center

Add a Confluence source with:

- `base_url`, for example `https://wiki.local`.
- `username`, if the server requires basic authentication.
- `api_token` or password, stored as a sensitive source field.
- Optional `space_key` to limit sync scope.
- Optional `updated_since` to limit initial polling.

The connector is intended for Confluence Server/Data Center URLs reachable from
the air-gapped Docker network or host routing environment. Atlassian Cloud is not
the target deployment for this connector.

### Jira Server/Data Center

Add a Jira source with:

- `base_url`, for example `https://jira.local`.
- `username`, if the server requires basic authentication.
- `api_token` or password, stored as a sensitive source field.
- Optional `project_key`, `jql`, or `updated_since` to limit sync scope.

Confluence and Jira Server/Data Center connectors are implemented, but
Atlassian-native permission synchronization is not yet included. Use Neverland
source grants, groups, and permissions to control access to synced documents.


### Windows / SMB Share

Add an SMB source with:

- `server`, for example `fileserver.local`.
- `share`, for example `department`.
- Optional `base_path`, for example `/legal/contracts`.
- Optional `domain`, for example `CORP`.
- `username` and sensitive `password` for a service account.
- Optional string settings: `recursive` (`true` or `false`), comma-separated
  `include_globs`, comma-separated `exclude_globs`, and integer
  `max_file_size_mb`.

The native SMB connector uses the Python `smbprotocol` / `smbclient` stack and
NTLM/negotiate username-password authentication. Kerberos is not required for the
MVP and may need additional Linux system packages in a future release. DFS path
handling is also a follow-up limitation. The connector reads files with the
configured service account and then applies Neverland source grants for search
and preview authorization; NTFS ACLs are not mirrored.

Operators that prefer host-level CIFS mounts can still mount the share on the
Docker host and ingest it with the existing folder connector using the container
path.

### NiFi

NiFi event ingestion is release-usable for operators that already provide a
Kafka/Redpanda event flow and an approved way to invoke Neverland
`NiFiKafkaDrain`. The air-gapped artifact does not add a dedicated long-running
NiFi worker container and CI does not use live NiFi or Kafka.

Create an enabled `nifi` source and grant it to groups before sending events.
Events must include `source_id` or `source_key`, `external_id`, `title` or
`filename`, `mime_type`, and either an `inline_text` payload or a `staged_file`
payload. Optional fields are `source_language`, lowercase hex `sha256`,
JSON-object `metadata`, `event_timestamp`, `correlation_id`, and `dlq_id`.
Staged files must already be present inside the API runtime. `staged_file`
payloads require `config.staging_root` to be set; events using this strategy
are rejected when `staging_root` is not configured, and the staged path must
resolve under that root.

NiFi documents are inserted with the normal `ingestion_sources` linkage and go
through the standard pipeline. DLQ routing handles malformed events, unknown or
disabled sources, inaccessible staged files, checksum mismatches, normalization
failures, and pipeline failures with sanitized reason text. Kafka offsets are
committed only after successful pipeline processing or successful DLQ routing; a
failed DLQ write leaves the offset uncommitted for retry.

## Configure Local Users, Groups, And LDAP

Set `AUTH_PROVIDER` in `.env`:

- `local`: local users created by an admin can log in.
- `ldap`: LDAP credentials are accepted; local-password login is disabled.
- `both`: local and LDAP login are both available.

For local users and groups, log in as an administrator and use the admin screens
or admin API to:

1. Create groups.
2. Create local users with temporary passwords.
3. Mark the appropriate users as administrators.
4. Grant groups access to sources/documents according to your operating model.

For LDAP, configure:

```env
AUTH_PROVIDER=ldap
LDAP_URL=ldap://domain-controller:389
LDAP_BASE_DN=DC=company,DC=local
LDAP_BIND_USER=cn=svc-search,DC=company,DC=local
LDAP_BIND_PASSWORD=change-me-ldap-bind-password
```

LDAP users authenticate against the configured directory. Group behavior depends
on the current Neverland auth boundary and configured/admin-created Neverland
groups; verify expected membership and access with a non-admin test account
before loading sensitive corpora.

## Start Neverland

Render the final Compose configuration:

```bash
docker compose --env-file .env -f docker-compose.airgap.yml config
```

Start in the background:

```bash
docker compose --env-file .env -f docker-compose.airgap.yml up -d
```

Check service state and logs:

```bash
docker compose --env-file .env -f docker-compose.airgap.yml ps
docker compose --env-file .env -f docker-compose.airgap.yml logs -f api frontend migrate
```

Health checks from the host:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/admin/readiness
curl -fsS http://localhost:8080/health
curl -fsS http://localhost:8080/api/health
```

Open the frontend at `http://localhost:8080` or the host/port you configured in
`.env`.

## First Admin Checklist

After the stack is healthy:

1. Log in as an administrator.
2. Create or configure local users, or verify LDAP login if LDAP is enabled.
3. Create groups and assign permissions.
4. Add a source: folder, Confluence Server/Data Center, or Jira Server/Data
   Center.
5. Sync the source.
6. Search for synced content.
7. Open a document preview.
8. Ask a Q&A question if RAG is enabled and the Ollama model is available.
9. Add a comment or annotation if those feature flags remain enabled.
10. Review `/admin/readiness` and service logs for degraded dependencies.

## Upgrade Existing Deployments

For an existing air-gapped deployment, do not reinstall from scratch and do not recreate volumes. Follow `docs/air-gapped-upgrade.md` from the release artifact, or `docs/operations/air-gapped-upgrade.md` in the source tree. The upgrade flow preserves `.env`, backs up PostgreSQL and files, loads images from the local artifact, runs migrations, and repeatedly warns against `docker compose down -v`.

## Stop, Reset, Backup, And Restore

Stop without deleting data:

```bash
docker compose --env-file .env -f docker-compose.airgap.yml down
```

Reset all named volumes, deleting metadata, files, indexes, caches, and Kafka
data. This is a destructive first-run reset command only; never use it for upgrades:

```bash
docker compose --env-file .env -f docker-compose.airgap.yml down -v
```

Back up `postgres_data`, `files_data`, `elasticsearch_data`, and `qdrant_data`
together while the stack is stopped, or from a storage snapshot that captures
them at the same point in time. Keep a logical PostgreSQL dump with volume
backups when possible. For upgrades, prefer `scripts/backup-airgap-data.sh` and `scripts/restore-airgap-data.sh`; see `docs/air-gapped-upgrade.md`. See `docs/production-compose.md` for detailed volume copy
commands and restore sequencing.

Restore all consistency-sensitive volumes from the same backup set. Do not mix a
PostgreSQL backup from one point in time with Elasticsearch or Qdrant indexes
from another unless you are prepared to rebuild indexes.

## Current Limitations

- The default artifact does not include pre-downloaded Ollama model weights.
  If the configured model is not already present in `ollama_data`, transfer an
  approved model bundle separately or load it during a connected staging step
  before moving the volume into the air-gapped environment.
- Long-running worker containers are not part of the current Compose runtime.
- NiFi event ingestion requires operator-provided drain invocation; no
  long-running worker container or live NiFi/Kafka CI validation is included.
- Atlassian-native permission synchronization is not present; use Neverland
  source grants and groups.
