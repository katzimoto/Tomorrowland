# Air-Gapped Compose Deployment

This guide describes the release artifact path for installing Tomorrowland on a
host that cannot reach the internet. The artifact contains the Compose files,
operator templates, validation scripts, documentation, checksums, and a Docker
image bundle with every first-party and third-party runtime image needed by the
default Compose deployment.

## Artifact Layout

A release archive is named `tomorrowland-release-<version>.tar.gz` and extracts to:

```text
tomorrowland-release-<version>/
  docker-compose.yml
  docker-compose.airgap.yml
  .env.airgap.example
  images/
    tomorrowland-images.tar
  scripts/
    load-airgap-images.sh
    validate-airgap-artifact.sh
    load-ollama-model-bundle.sh
    validate-ollama-model.sh
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
2. Download the matching `tomorrowland-release-<version>.tar.gz.sha256` file.
3. Verify the archive checksum before transfer:

   ```bash
   sha256sum -c tomorrowland-release-<version>.tar.gz.sha256
   ```

4. For RC2 and later, also download the default Ollama model bundle release
   asset and checksum, for example
   `tomorrowland-ollama-bundle-mistral-<version>.tar.gz` and
   `tomorrowland-ollama-bundle-mistral-<version>.tar.gz.sha256`.
5. Verify the model bundle checksum before transfer:

   ```bash
   sha256sum -c tomorrowland-ollama-bundle-mistral-<version>.tar.gz.sha256
   ```

6. Copy the verified platform archive and model bundle archive to the air-gapped
   host using approved removable media or an approved transfer gateway.

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
tar xzf tomorrowland-release-<version>.tar.gz
cd tomorrowland-release-<version>
sha256sum -c checksums.txt
bash scripts/validate-airgap-artifact.sh .
```

If the model bundle is in the same directory as the extracted artifact, or if you
pass it explicitly, validation also checks its outer checksum when present,
`model-manifest.json`, `checksums.txt`, model identity fields, and license/source
metadata fields:

```bash
bash scripts/validate-airgap-artifact.sh \
  --model-bundle ../tomorrowland-ollama-bundle-mistral-<version>.tar.gz \
  .
```

The validation script fails if required platform files are missing, checksums do
not match, Compose cannot render the air-gapped file, a `build:` step appears in
the air-gapped Compose path, or a referenced image is not present in
`images/tomorrowland-images.tar`. A missing Ollama model bundle is a warning only:
the base platform artifact remains valid, but Q&A/RAG/local intelligence is
degraded until the configured model is loaded.

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

## Ollama Model Bundle

The RC2 release ships with a default Ollama model bundle as a separate release
asset. Operators should transfer and load this bundle for offline Q&A/RAG support.
The main platform can still start without the model, but the default RC2 release
package includes the model bundle artifact and validation path.

The bundle is separate from `tomorrowland-release-<version>.tar.gz` because model
weights are large, may require customer-specific approval, and may be replaced
independently from the application images. The default bundle follows this naming
pattern:

```text
tomorrowland-ollama-bundle-mistral-<version>.tar.gz
tomorrowland-ollama-bundle-mistral-<version>.tar.gz.sha256
```

Each bundle contains a `models/` directory in Ollama's storage layout,
`model-manifest.json`, `checksums.txt`, and `README-ollama-bundle.md`. The
manifest records the requested model, resolved model/tag, resolved digest,
Ollama runtime image/version, blob paths and SHA-256 checksums, model source, and
license/source/attribution fields. If the manifest license status is
`operator_required`, a release manager or operator must verify redistribution and
source metadata before publishing or deploying the bundle.

Load the bundle after images are loaded and before relying on Q&A/RAG:

```bash
bash scripts/load-ollama-model-bundle.sh \
  --bundle ../tomorrowland-ollama-bundle-mistral-<version>.tar.gz \
  --compose-file docker-compose.airgap.yml \
  --env-file .env
```

The load script extracts the bundle, verifies inner checksums, copies `models/`
into the Compose `ollama_data` volume, and restarts only the `ollama` service if
needed. It is non-destructive by default and does not run `docker compose down -v`.

Validate that the configured model is available offline:

```bash
OLLAMA_URL=http://localhost:11434 \
OLLAMA_MODEL=mistral \
bash scripts/validate-ollama-model.sh
```

For an end-to-end local generation check, run:

```bash
OLLAMA_URL=http://localhost:11434 \
OLLAMA_MODEL=mistral \
bash scripts/validate-ollama-model.sh --smoke-test
```

The validation script checks `/api/tags` and never attempts to pull or download a
model. In `--smoke-test` mode it sends a tiny local generation request and
requires a non-empty response.

If the model is absent, platform startup, login, ingestion, search,
preview/download, permissions, and translation can still work. Features that call
Ollama, including Q&A/RAG and summaries routed through the local model, should be
treated as degraded until the model is loaded.

To replace the default model, build or obtain an approved bundle for the
replacement model, set `OLLAMA_MODEL` in `.env` to match the bundle manifest, load
it with `scripts/load-ollama-model-bundle.sh`, and run
`scripts/validate-ollama-model.sh`. Keep the previous bundle and volume backup
until the replacement has passed validation.

Reserve disk for both the compressed bundle and expanded Ollama blobs. The
`mistral` bundle can require multiple gigabytes, and replacement models may be
larger.

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
  `http://tomorrowland.example.local:8080`; do not use a wildcard.
- Set `API_PORT` and `FRONTEND_PORT` for the host ports operators should reach.
- Leave the direct API and infrastructure ports bound to localhost unless a
  maintenance workflow explicitly requires host access. Put any public access
  behind an approved reverse proxy and access control boundary.

The template contains placeholders only. Do not put real secrets back into the
release archive or commit them to source control.

## Configure Source Connectors

Source definitions are created after login from the admin UI or admin API. Store
connector credentials in the Tomorrowland source configuration, not in the release
artifact.

### Folder Connector

The air-gapped compose file mounts a host folder into the API and migration
containers:

```env
TOMORROWLAND_FOLDER_SOURCE_HOST_PATH=./operator-data/folder-source
TOMORROWLAND_FOLDER_SOURCE_CONTAINER_PATH=/sources/folder
```

Create the host directory and copy source documents into it:

```bash
mkdir -p operator-data/folder-source
```

When adding a folder source in Tomorrowland, use the container path from `.env`, for
example `/sources/folder`. Do not use the host path in the source definition;
the API runs inside the container.


### Host-Mounted SMB Shares

For Windows or Samba file shares, the recommended interim deployment path is to
mount the SMB/CIFS share on the Docker host and expose it to Tomorrowland as a
read-only `folder` source. Use this path when operators already manage SMB
mounts at the OS level, SMB credentials should remain on the host instead of in
Tomorrowland source configuration, a read-only ingestion path is sufficient, or the
native SMB connector tracked in #77 is unavailable or not preferred. This path is
independent from #77 and does not mirror NTFS ACLs; optional NTFS ACL sync is
tracked separately in #79.

On the air-gapped host, install CIFS tooling such as `cifs-utils` from approved
offline packages, then create and verify the host mount before starting
Tomorrowland:

```bash
sudo mkdir -p /mnt/tomorrowland-smb/legal
sudo mount -t cifs //fileserver/department /mnt/tomorrowland-smb/legal \
  -o credentials=/etc/tomorrowland/smb-legal.credentials,ro,vers=3.0,iocharset=utf8
```

Example credential file format, with placeholders only:

```ini
username=tomorrowland-reader
password=REPLACE_WITH_SECRET
domain=CORP
```

Secure the host credential file and keep real SMB secrets out of the release
artifact, `.env`, Compose files, Git, docs, and screenshots:

```bash
sudo chown root:root /etc/tomorrowland/smb-legal.credentials
sudo chmod 600 /etc/tomorrowland/smb-legal.credentials
```

Optional `/etc/fstab` entry:

```fstab
//fileserver/department /mnt/tomorrowland-smb/legal cifs credentials=/etc/tomorrowland/smb-legal.credentials,ro,vers=3.0,iocharset=utf8,nofail 0 0
```

Verify the mount before starting or upgrading the stack:

```bash
mount | grep /mnt/tomorrowland-smb/legal
ls -la /mnt/tomorrowland-smb/legal
```

Add a read-only bind mount to the `api` service in a local Compose override,
using a stable container path such as `/data/smb/<source-name>`:

```yaml
services:
  api:
    volumes:
      - /mnt/tomorrowland-smb/legal:/data/smb/legal:ro
```

The host source path must exist before `docker compose up`. Keep the host mount
path and container path stable across upgrades; the SMB mount is external host
state and is not packaged inside Tomorrowland release artifacts.

Create the Tomorrowland source with:

```text
Source type: folder
Path: /data/smb/legal
```

The `folder` connector sees the mounted SMB share as local files. The Tomorrowland
source path must be the container path, not `/mnt/tomorrowland-smb/legal` on the
host. Tomorrowland source permissions control which groups can search and preview
indexed documents, while the SMB service account controls which files are visible
to the mount. Do not rely on Windows ACLs for per-user Tomorrowland authorization
after ingestion.

Troubleshooting notes:

- If the container cannot see files, verify the host mount, the `api` service
  bind mount, and the rendered Compose config.
- If ingestion is empty, confirm the source uses the container path and that the
  mounted subtree contains regular files.
- If permission is denied, confirm the SMB service account, host mount
  permissions, and root-owned credential file permissions.
- If the mount disappears after reboot, validate `/etc/fstab` or the equivalent
  systemd mount before starting Tomorrowland.
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
Atlassian-native permission synchronization is not yet included. Use Tomorrowland
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
configured service account and then applies Tomorrowland source grants for search
and preview authorization; NTFS ACLs are not mirrored.

Operators that prefer host-level CIFS mounts can still mount the share on the
Docker host and ingest it with the existing folder connector using the container
path.

### NiFi

NiFi event ingestion is release-usable for operators that already provide a
Kafka/Redpanda event flow and an approved way to invoke Tomorrowland
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
on the current Tomorrowland auth boundary and configured/admin-created Tomorrowland
groups; verify expected membership and access with a non-admin test account
before loading sensitive corpora.

## Start Tomorrowland

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

## Translation Language Support

The release artifact includes a pinned LibreTranslate image (`tomorrowland/libretranslate:airgap`)
with Argos Translate language packs pre-installed at image build time. The air-gapped
target host does not download translation models at startup.

### Supported RC language matrix

| Code | Language             | To English | From English |
|------|----------------------|------------|--------------|
| `en` | English              | —          | —            |
| `ar` | Arabic               | Yes        | Yes          |
| `fr` | French               | Yes        | Yes          |
| `ru` | Russian              | Yes        | Yes          |
| `es` | Spanish              | Yes        | Yes          |
| `zh` | Chinese Simplified   | Yes        | Yes          |
| `ko` | Korean               | Yes        | Yes          |
| `th` | Thai                 | Yes        | Yes          |
| `he` | Hebrew               | Yes        | Yes          |

### Direct non-English pairs

LibreTranslate routes non-English-to-non-English translation requests through an
English pivot (e.g., Arabic to French is translated as Arabic → English → French).
Direct non-English pairs are not installed; quality for indirect pairs depends on
the intermediate English translation step.

### Chinese language support

Chinese support in this RC means Chinese Simplified (`zh`) only. Chinese
Traditional (`zt`) is out of scope for this RC.

### Validating language support after startup

After the stack is healthy, run the translation validation script against the
running LibreTranslate service:

```bash
LIBRETRANSLATE_URL=http://localhost:5000 bash scripts/validate-translation-languages.sh
```

The script checks:

1. `/languages` is reachable.
2. Required language codes (`en`, `ar`, `fr`, `ru`, `es`, `zh`, `ko`, `th`, `he`)
   are present.
3. Each required non-English language can translate to and from English.

### Adding languages in future releases

To add a language in a future release:

1. Add the new language code to `SUPPORTED_TRANSLATION_SOURCE_LANGUAGES` and
   `SUPPORTED_TRANSLATION_TARGET_LANGUAGES` in both env example files.
2. Add the required `(lang, "en")` and `("en", lang)` pairs to `REQUIRED_PAIRS`
   in `docker/install-translation-packs.py`.
3. Rebuild the `tomorrowland/libretranslate:airgap` image in a connected environment.
4. Bundle the new image into the next release artifact.
5. Update the language matrix in this document.

### Unsupported-language behavior

Languages not listed in `SUPPORTED_TRANSLATION_SOURCE_LANGUAGES` and
`SUPPORTED_TRANSLATION_TARGET_LANGUAGES` are still indexed and searchable as
original text. Translation requests for unsupported language codes are rejected or
marked unavailable by the application; they are not silently passed to
LibreTranslate. Operators should not infer that a language is translated simply
because it appears in document metadata.

### Artifact size impact

Each Argos Translate language pair adds approximately 50–300 MB to the
`tomorrowland/libretranslate:airgap` image. The bundled image for the required
language set is approximately 3–5 GB larger than the base `libretranslate:v1.6.3`
image. Operators should reserve additional disk space for the expanded image
bundle. See `Host Prerequisites` above for overall disk guidance.

## Current Limitations

- Ollama model weights remain a separate release asset rather than being embedded
  in the platform archive. The default RC2 release distribution includes the
  platform artifact plus the default `mistral` model bundle, but operators may
  omit or replace the bundle; local Q&A/RAG features are degraded until a matching
  model is loaded into `ollama_data`.
- Long-running worker containers are not part of the current Compose runtime.
- NiFi event ingestion requires operator-provided drain invocation; no
  long-running worker container or live NiFi/Kafka CI validation is included.
- Atlassian-native permission synchronization is not present; use Tomorrowland
  source grants and groups.
- Direct non-English translation pairs are not installed; non-English-to-non-English
  translation uses an English pivot via LibreTranslate's built-in routing.
- Chinese support in this RC means Chinese Simplified (`zh`) only; Chinese
  Traditional (`zt`) is out of scope for this RC.
