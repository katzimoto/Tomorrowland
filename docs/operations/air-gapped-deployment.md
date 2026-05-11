# Air-Gapped Compose Deployment

This guide describes the release artifact path for installing Tomorrowland on a
host that cannot reach the internet. The platform archive contains the Compose
files, operator templates, scripts, documentation, and checksums. The Docker
image bundle is distributed as separate split-part files beside the platform
archive. A single wrapper script handles validation, image loading, and stack
management so operators do not need to run lower-level scripts directly.

## Required release files

Download all four files (and optionally the Ollama model bundle):

```text
tomorrowland-release-<version>.tar.gz        platform archive (small)
tomorrowland-release-<version>.tar.gz.sha256
tomorrowland-images-<version>.tar.part-000   Docker image bundle (split)
tomorrowland-images-<version>.tar.part-001
...
tomorrowland-images-<version>.tar.parts.sha256
```

Optional (for offline Q&A/RAG/local intelligence):

```text
tomorrowland-ollama-bundle-mistral-<version>.tar.gz
tomorrowland-ollama-bundle-mistral-<version>.tar.gz.sha256
```

The platform archive is small. The Docker image bundle is large and distributed
as split parts so each file stays within GitHub Release asset size limits.
Operators do not need to manually reassemble the parts; the wrapper script
handles streaming them into Docker.

A missing Ollama model bundle is a warning only. The platform starts and runs
without it, but offline Q&A/RAG/local intelligence is degraded until a model
bundle is loaded.

## Happy path (quick reference)

```bash
# Verify checksums before transfer or use
sha256sum -c tomorrowland-release-<version>.tar.gz.sha256
sha256sum -c tomorrowland-images-<version>.tar.parts.sha256

# Extract the platform archive
tar xzf tomorrowland-release-<version>.tar.gz
cd tomorrowland-release-<version>

# Configure environment
cp .env.airgap.example .env
nano .env   # replace every change-me-* placeholder

# Validate and load images (image parts auto-detected beside this directory)
./scripts/tomorrowland-airgap.sh validate --load-images

# Start the stack
./scripts/tomorrowland-airgap.sh up
```

## Artifact layout

The platform archive extracts to a directory named after the version:

```text
tomorrowland-release-<version>/
  docker-compose.yml
  docker-compose.airgap.yml
  .env.airgap.example
  release-manifest.json
  checksums.txt
  README-airgap.txt
  images/
    README-images.txt
  scripts/
    tomorrowland-airgap.sh        operator wrapper (primary entry point)
    load-airgap-images.sh
    validate-airgap-artifact.sh
    load-ollama-model-bundle.sh
    validate-ollama-model.sh
    validate-translation-languages.sh
    preflight-upgrade-check.sh
    backup-airgap-data.sh
    restore-airgap-data.sh
    upgrade-airgap.sh
  docs/
    air-gapped-deployment.md
    air-gapped-upgrade.md
    production-compose.md
    split-airgap-artifacts.md
```

The split image part files are placed **beside** the extracted directory, not
inside it:

```text
<download-dir>/
  tomorrowland-release-<version>/    (extracted platform archive)
  tomorrowland-images-<version>.tar.part-000
  tomorrowland-images-<version>.tar.part-001
  ...
  tomorrowland-images-<version>.tar.parts.sha256
```

`release-manifest.json` records the release version, commit, Compose files,
image tags, minimum Docker/Compose versions, migration expectation, persistent
data locations, and backup/restore script version.

Use `docker-compose.airgap.yml` for offline hosts. It contains only `image:`
references and does not require Docker builds. The root `docker-compose.yml` is
included for source traceability and connected environments that intentionally
build from source.

## Download and transfer

1. From a connected workstation, download the platform archive and its checksum:

   ```bash
   # (from GitHub Release assets or workflow artifacts)
   sha256sum -c tomorrowland-release-<version>.tar.gz.sha256
   ```

2. Download all split image part files and their checksum:

   ```bash
   sha256sum -c tomorrowland-images-<version>.tar.parts.sha256
   ```

3. Optionally download the Ollama model bundle (for offline Q&A/RAG):

   ```bash
   sha256sum -c tomorrowland-ollama-bundle-mistral-<version>.tar.gz.sha256
   ```

4. Copy all verified files to the air-gapped host using approved removable
   media or an approved transfer gateway. Keep the image parts in the same
   directory as the platform archive.

## Host prerequisites

Install on the air-gapped host before extracting the artifact:

- Docker Engine 24 or newer.
- Docker Compose plugin 2.20 or newer.
- Enough local disk for the image parts, extracted Docker images, named
  volumes, Elasticsearch/Qdrant indexes, uploaded files, translation cache,
  and Ollama model cache.
- Host firewall rules that expose only the intended frontend port. The
  air-gapped Compose file binds the direct API port and infrastructure ports
  to `127.0.0.1` by default.

Confirm versions:

```bash
docker --version
docker compose version
```

## Extract the platform archive

Extract in the directory that also contains the image part files:

```bash
tar xzf tomorrowland-release-<version>.tar.gz
cd tomorrowland-release-<version>
```

## Configure the environment

```bash
cp .env.airgap.example .env
```

Edit `.env` before starting. At minimum:

- Replace `POSTGRES_PASSWORD` with a strong password.
- Update `POSTGRES_URL` so the password, user, host, port, and database match
  the `POSTGRES_*` values; the default service host remains `postgres`.
- Replace `JWT_SECRET` with a long random value and keep it stable after users
  are created.
- Confirm `FILES_ROOT=/data` unless you intentionally change the container
  storage path.
- Set `CORS_ORIGINS` to the exact browser origin, for example
  `http://tomorrowland.example.local:8080`. Do not use a wildcard.
- Set `API_PORT` and `FRONTEND_PORT` for the host ports operators should reach.
- Leave the direct API and infrastructure ports bound to localhost unless a
  maintenance workflow explicitly requires host access.

The template contains placeholders only. Do not put real secrets back into the
release archive or commit them to source control.

## Validate and load images

Run validation and image loading together using the wrapper:

```bash
./scripts/tomorrowland-airgap.sh validate --load-images
```

This command:
- validates the platform archive structure after extraction
- verifies `docker-compose.airgap.yml` has no `build:` stanzas
- verifies all required scripts, docs, and environment files are present
- verifies image part metadata exists in `release-manifest.json`
- verifies image part checksums
- confirms image parts are contiguous
- auto-detects the split image parts in the parent directory (beside the
  platform archive); no manual reassembly needed
- loads images into the local Docker daemon
- confirms all images referenced by the air-gapped Compose file are present
- does not require internet access

If the image parts are in a non-default location, pass `--image-parts-dir`:

```bash
./scripts/tomorrowland-airgap.sh validate --load-images \
  --image-parts-dir /media/usb/tomorrowland-images
```

To validate without loading images (metadata and checksums only):

```bash
./scripts/tomorrowland-airgap.sh validate
```

To load images separately after validation:

```bash
./scripts/tomorrowland-airgap.sh load-images
# or with explicit location:
./scripts/tomorrowland-airgap.sh load-images --image-parts-dir /path/to/parts
```

## Start the stack

```bash
./scripts/tomorrowland-airgap.sh up
```

This starts the stack with no build and no internet pull using the air-gapped
Compose file. It requires `.env` to exist and never overwrites it.

Check service state and logs:

```bash
./scripts/tomorrowland-airgap.sh status
docker compose --env-file .env -f docker-compose.airgap.yml logs -f api frontend migrate
```

Health checks from the host:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/admin/readiness
curl -fsS http://localhost:8080/health
```

Open the frontend at `http://localhost:8080` or the host/port you configured
in `.env`.

## Ollama model bundle

The RC2 release ships with a default Ollama model bundle as a separate release
asset. Operators should transfer and load this bundle for offline Q&A/RAG
support. The main platform can still start without the model, but the default
RC2 release package includes the model bundle artifact and validation path.

The bundle is separate from the platform archive because model weights are
large, may require customer-specific approval, and may be replaced
independently from the application images. The default bundle follows this
naming pattern:

```text
tomorrowland-ollama-bundle-mistral-<version>.tar.gz
tomorrowland-ollama-bundle-mistral-<version>.tar.gz.sha256
```

Each bundle contains a `models/` directory in Ollama's storage layout,
`model-manifest.json`, `checksums.txt`, and `README-ollama-bundle.md`. The
manifest records the requested model, resolved model/tag, resolved digest,
Ollama runtime image/version, blob paths and SHA-256 checksums, model source,
and license/source/attribution fields. If the manifest license status is
`operator_required`, a release manager or operator must verify redistribution
and source metadata before publishing or deploying the bundle.

Load the bundle after images are loaded and before relying on Q&A/RAG:

```bash
bash scripts/load-ollama-model-bundle.sh \
  --bundle ../tomorrowland-ollama-bundle-mistral-<version>.tar.gz \
  --compose-file docker-compose.airgap.yml \
  --env-file .env
```

Validate that the configured model is available offline:

```bash
OLLAMA_URL=http://localhost:11434 \
OLLAMA_MODEL=mistral \
bash scripts/validate-ollama-model.sh
```

For an end-to-end local generation check:

```bash
OLLAMA_URL=http://localhost:11434 \
OLLAMA_MODEL=mistral \
bash scripts/validate-ollama-model.sh --smoke-test
```

The validation script checks `/api/tags` and never attempts to pull or download
a model. In `--smoke-test` mode it sends a tiny local generation request and
requires a non-empty response.

If the model is absent, platform startup, login, ingestion, search,
preview/download, permissions, and translation can still work. Features that
call Ollama, including Q&A/RAG and summaries routed through the local model,
should be treated as degraded until the model is loaded.

## Configure source connectors

Source definitions are created after login from the admin UI or admin API. Store
connector credentials in the Tomorrowland source configuration, not in the
release artifact.

### Folder connector

The air-gapped Compose file mounts a host folder into the API and migration
containers:

```env
TOMORROWLAND_FOLDER_SOURCE_HOST_PATH=./operator-data/folder-source
TOMORROWLAND_FOLDER_SOURCE_CONTAINER_PATH=/sources/folder
```

Create the host directory and copy source documents into it:

```bash
mkdir -p operator-data/folder-source
```

When adding a folder source in Tomorrowland, use the container path from `.env`,
for example `/sources/folder`. Do not use the host path in the source
definition; the API runs inside the container.

### Host-mounted SMB shares

For Windows or Samba file shares, the recommended interim deployment path is to
mount the SMB/CIFS share on the Docker host and expose it to Tomorrowland as a
read-only `folder` source. Use this path when operators already manage SMB
mounts at the OS level, SMB credentials should remain on the host instead of in
Tomorrowland source configuration, a read-only ingestion path is sufficient, or
the native SMB connector tracked in #77 is unavailable or not preferred. This
path is independent from #77 and does not mirror NTFS ACLs; optional NTFS ACL
sync is tracked separately in #79.

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

The `folder` connector sees the mounted SMB share as local files. The
Tomorrowland source path must be the container path, not
`/mnt/tomorrowland-smb/legal` on the host. Tomorrowland source permissions
control which groups can search and preview indexed documents, while the SMB
service account controls which files are visible to the mount. Do not rely on
Windows ACLs for per-user Tomorrowland authorization after ingestion.

Troubleshooting notes:

- If the container cannot see files, verify the host mount, the `api` service
  bind mount, and the rendered Compose config.
- If ingestion is empty, confirm the source uses the container path and that
  the mounted subtree contains regular files.
- If permission is denied, confirm the SMB service account, host mount
  permissions, and root-owned credential file permissions.
- If the mount disappears after reboot, validate `/etc/fstab` or the equivalent
  systemd mount before starting Tomorrowland.
- If scans are slow, narrow the mounted subtree or source scope and check
  network and SMB server performance.

### Confluence Server/Data Center

Add a Confluence source with:

- `base_url`, for example `https://wiki.local`.
- `username`, if the server requires basic authentication.
- `api_token` or password, stored as a sensitive source field.
- Optional `space_key` to limit sync scope.
- Optional `updated_since` to limit initial polling.

The connector is intended for Confluence Server/Data Center URLs reachable from
the air-gapped Docker network or host routing environment. Atlassian Cloud is
not the target deployment for this connector.

### Jira Server/Data Center

Add a Jira source with:

- `base_url`, for example `https://jira.local`.
- `username`, if the server requires basic authentication.
- `api_token` or password, stored as a sensitive source field.
- Optional `project_key`, `jql`, or `updated_since` to limit sync scope.

Confluence and Jira Server/Data Center connectors are implemented, but
Atlassian-native permission synchronization is not yet included. Use Tomorrowland
source grants, groups, and permissions to control access to synced documents.

### Windows / SMB share

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
NTLM/negotiate username-password authentication. Kerberos is not required for
the MVP and may need additional Linux system packages in a future release.

### NiFi

NiFi event ingestion is release-usable for operators that already provide a
Kafka/Redpanda event flow and an approved way to invoke Tomorrowland
`NiFiKafkaDrain`. The air-gapped artifact does not add a dedicated long-running
NiFi worker container and CI does not use live NiFi or Kafka.

## Configure local users, groups, and LDAP

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

## First admin checklist

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

## Upgrade existing deployments

For an existing air-gapped deployment, do not reinstall from scratch and do not
recreate volumes. Follow `docs/air-gapped-upgrade.md` from the release artifact.
The upgrade flow preserves `.env`, backs up PostgreSQL and files, loads images
from the local artifact, runs migrations, and warns against
`docker compose down -v`.

Primary upgrade command (run from the existing deployment directory):

```bash
./scripts/tomorrowland-airgap.sh upgrade \
  --artifact-dir ../tomorrowland-release-<version>
```

See `docs/operations/air-gapped-upgrade.md` for the full upgrade procedure.

## Stop, backup, and restore

Stop the stack without deleting data:

```bash
./scripts/tomorrowland-airgap.sh down
```

Create a backup (PostgreSQL dump, files volume, config):

```bash
./scripts/tomorrowland-airgap.sh backup
# or with a custom output directory:
./scripts/tomorrowland-airgap.sh backup --output-dir /backups/tomorrowland
```

**Never run `docker compose down -v`.** The `-v` flag deletes named volumes,
including PostgreSQL, Elasticsearch, Qdrant, files, model, and broker data.

Back up `postgres_data`, `files_data`, `elasticsearch_data`, and `qdrant_data`
together while the stack is stopped, or from a storage snapshot that captures
them at the same point in time. Keep a logical PostgreSQL dump with volume
backups when possible. For upgrades, prefer `scripts/backup-airgap-data.sh` and
`scripts/restore-airgap-data.sh`; see `docs/air-gapped-upgrade.md`.

Restore all consistency-sensitive volumes from the same backup set. Do not mix a
PostgreSQL backup from one point in time with Elasticsearch or Qdrant indexes
from another unless you are prepared to rebuild indexes.

## Legacy neverland-* asset names

Earlier releases may have produced asset names beginning with `neverland-`
rather than `tomorrowland-`. The `tomorrowland-*` names are now canonical.
If the connected environment still produces `neverland-*` files:

- `scripts/load-airgap-images.sh` and `scripts/validate-airgap-artifact.sh`
  look for `tomorrowland-images-*.tar.part-*` by pattern; rename or alias
  legacy parts before running the wrapper, or pass `--image-parts-dir` to
  point at the directory containing the parts.
- Docker image tags, volume names, environment variable names, Compose service
  names, and database names use `tomorrowland` internally and are not affected
  by release asset naming.
- The operator documentation uses `tomorrowland-*` asset names as the canonical
  form in all examples.

## Translation language support

The release artifact includes a pinned LibreTranslate image
(`tomorrowland/libretranslate:airgap`) with Argos Translate language packs
pre-installed at image build time. The air-gapped target host does not download
translation models at startup.

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

LibreTranslate routes non-English-to-non-English translation requests through
an English pivot (e.g., Arabic to French is translated as Arabic → English →
French). Direct non-English pairs are not installed; quality for indirect pairs
depends on the intermediate English translation step.

### Chinese language support

Chinese support in this RC means Chinese Simplified (`zh`) only. Chinese
Traditional (`zt`) is out of scope for this RC.

### Validating language support after startup

After the stack is healthy, run the translation validation script:

```bash
LIBRETRANSLATE_URL=http://localhost:5000 bash scripts/validate-translation-languages.sh
```

### Adding languages in future releases

1. Add the new language code to `SUPPORTED_TRANSLATION_SOURCE_LANGUAGES` and
   `SUPPORTED_TRANSLATION_TARGET_LANGUAGES` in both env example files.
2. Add the required `(lang, "en")` and `("en", lang)` pairs to `REQUIRED_PAIRS`
   in `docker/install-translation-packs.py`.
3. Rebuild the `tomorrowland/libretranslate:airgap` image in a connected
   environment.
4. Bundle the new image into the next release artifact.
5. Update the language matrix in this document.

### Unsupported-language behavior

Languages not listed in `SUPPORTED_TRANSLATION_SOURCE_LANGUAGES` and
`SUPPORTED_TRANSLATION_TARGET_LANGUAGES` are still indexed and searchable as
original text. Translation requests for unsupported language codes are rejected
or marked unavailable by the application.

## Current limitations

- Ollama model weights remain a separate release asset rather than being
  embedded in the platform archive. The default RC2 release distribution
  includes the platform artifact plus the default `mistral` model bundle, but
  operators may omit or replace the bundle; local Q&A/RAG features are degraded
  until a matching model is loaded into `ollama_data`.
- Long-running worker containers are not part of the current Compose runtime.
- NiFi event ingestion requires operator-provided drain invocation; no
  long-running worker container or live NiFi/Kafka CI validation is included.
- Atlassian-native permission synchronization is not present; use Tomorrowland
  source grants and groups.
- Direct non-English translation pairs are not installed; non-English-to-non-English
  translation uses an English pivot via LibreTranslate's built-in routing.
- Chinese support in this RC means Chinese Simplified (`zh`) only.
