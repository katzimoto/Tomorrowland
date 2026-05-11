# Split Air-Gapped Release Artifacts

Large air-gapped releases are distributed as several files so each GitHub Release asset stays below the per-file upload limit while the deployment still works without runtime internet access.

## Files

A split release contains these assets:

```text
tomorrowland-release-<version>.tar.gz
tomorrowland-release-<version>.tar.gz.sha256
tomorrowland-images-<version>.tar.part-000
tomorrowland-images-<version>.tar.part-001
tomorrowland-images-<version>.tar.part-002
...
tomorrowland-images-<version>.tar.parts.sha256
```

The `tomorrowland-release-<version>.tar.gz` archive is the small platform archive. It contains Compose files, environment templates, scripts, docs, checksums, and release metadata.

The `tomorrowland-images-<version>.tar.part-*` files are the split Docker image bundle. Together, they represent the image archive that is loaded into Docker on the air-gapped host.

## Download and transfer

Download every file for the same version. Keep the file names unchanged.

Verify checksums on the connected workstation before transfer:

```bash
sha256sum -c tomorrowland-release-<version>.tar.gz.sha256
sha256sum -c tomorrowland-images-<version>.tar.parts.sha256
```

Transfer the verified files to the air-gapped host using the approved transfer process.

## Extract and validate

Keep the image parts beside the platform archive:

```text
transfer-dir/
  tomorrowland-release-<version>.tar.gz
  tomorrowland-release-<version>.tar.gz.sha256
  tomorrowland-images-<version>.tar.part-000
  tomorrowland-images-<version>.tar.part-001
  tomorrowland-images-<version>.tar.parts.sha256
```

Then extract and validate:

```bash
tar xzf tomorrowland-release-<version>.tar.gz
cd tomorrowland-release-<version>
bash scripts/validate-airgap-artifact.sh --load-images .
```

The validation script automatically looks for split image parts in the parent directory. Use `--image-parts-dir <dir>` if the parts are somewhere else:

```bash
bash scripts/validate-airgap-artifact.sh --load-images --image-parts-dir /path/to/parts .
```

## Load images

The loader supports both layouts:

1. Legacy embedded image tar: `images/tomorrowland-images.tar`
2. Split image parts: `tomorrowland-images-<version>.tar.part-*`

To load images from the default layout:

```bash
bash scripts/load-airgap-images.sh .
```

To load image parts from another directory:

```bash
bash scripts/load-airgap-images.sh --image-parts-dir /path/to/parts .
```

For split assets, the loader streams the ordered parts into `docker load`. It does not require runtime internet access and it does not run Docker builds on the air-gapped host.

## Backward compatibility

Local/manual builds can still produce the legacy embedded layout by running:

```bash
SPLIT_IMAGE_BUNDLE=0 bash scripts/build-release-artifact.sh <version>
```

Release builds should keep split mode enabled:

```bash
SPLIT_IMAGE_BUNDLE=1 IMAGE_PART_SIZE=1900m bash scripts/build-release-artifact.sh <version>
```

`1900m` leaves margin below the 2 GiB per-asset limit.

## Troubleshooting

If validation cannot find the image parts, confirm that:

- all `tomorrowland-images-<version>.tar.part-*` files are present;
- `tomorrowland-images-<version>.tar.parts.sha256` is present;
- the part files are in the parent directory of the extracted release archive, or `--image-parts-dir` points to their directory;
- the part suffixes are contiguous: `000`, `001`, `002`, and so on.

If checksum validation fails, re-copy the image parts from the connected workstation. Do not load partially copied image bundles.
