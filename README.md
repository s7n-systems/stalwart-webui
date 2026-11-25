# Stalwart WebUI image

Stalwart does not ship its web interface in its container image: by default it downloads
`webui.zip` from GitHub at runtime and caches it for 90 days. This repository packages that
bundle, unmodified, as a container image pinned by version and checksum, so the WebUI is
deployed like every other component: reviewed in git, pinned by digest, signed, and served
without network access from the Stalwart pod.

The [Stalwart Helm chart](https://github.com/s7n-systems/stalwart-chart) copies the bundle into
the pod with an init container and points Stalwart's WebUI at it with a `file://` URL.

## Image

```
ghcr.io/s7n-systems/stalwart-webui:<webui version>
```

| Path | Content |
| --- | --- |
| `/webui/webui.zip` | The release asset `webui.zip` of [stalwartlabs/webui](https://github.com/stalwartlabs/webui/releases) |
| `/licenses/` | The WebUI's licence texts (AGPL-3.0-only, LicenseRef-SEL) |

The base is busybox, for the `cp` the init container runs. The image runs as UID 65532 and
needs no writable file system. The tag is the WebUI version without the `v`; the label
`eu.sovereign-systems.webui.sha256` holds the bundle's SHA-256. Platforms: `linux/amd64`,
`linux/arm64`, `linux/arm/v7`, `linux/ppc64le`, `linux/riscv64`, `linux/s390x`.

Use it without the chart by copying the bundle into a volume that Stalwart can read, then
setting the WebUI's `resourceUrl`:

```sh
cp /webui/webui.zip /opt/stalwart/webui/webui-2.1.1.zip     # in an init container
stalwart-cli update Application <id> --field resourceUrl=file:///opt/stalwart/webui/webui-2.1.1.zip
stalwart-cli create Action/UpdateApps
```

A new `resourceUrl` only drops Stalwart's stored bundle; running servers keep serving the one
they unpacked until `UpdateApps` (or a restart) loads it from the URL. Every node must have the
file before the URL names it, and Stalwart reports `UpdateApps` as done even when a node cannot
read the file, so check what each node serves. The chart's WebUI Job does all of this.

### Verify the signature

Images are signed keylessly with cosign from this repository's workflow:

```sh
cosign verify ghcr.io/s7n-systems/stalwart-webui:2.1.1 \
  --certificate-identity-regexp '^https://github\.com/s7n-systems/stalwart-webui/\.github/workflows/build\.yml@refs/heads/main$' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

## Build and publication

The workflow has three jobs:

1. **Lint:** YAML, the Renovate config, the scripts and the workflows.
2. **Build and verify**, with read-only permissions, for every pull request and push: builds all
   platforms into one OCI archive, then checks it on the runner without running anything from the
   image (`scripts/verify_archive.py`): exactly the built platforms (the bundle has none, but the
   init container runs BusyBox `cp`), and per platform the bundle's SHA-256 and manifest version,
   the licence texts and the image user. `scripts/test-copy.sh` then runs the runner's platform
   image as the chart's init container does: UID 2000, read-only root file system, no network,
   `cp` into a mounted volume, and hashes the copy on the runner.
3. **Publish and sign**, only on `main`, the only job with `packages: write` and `id-token: write`:
   pushes that same archive with its digests preserved to the `staging` tag, checks the pushed
   digest, signs it with cosign and verifies the signature, and only then points the version tag
   at it. The version tag therefore never shows an image that was not verified and signed.

Make **Lint** and **Build and verify** required checks for `main`.

Layer timestamps come from the commit (`SOURCE_DATE_EPOCH`), so rebuilding a commit is meant to
give the same image.

## Updates

Renovate opens and, where noted, merges the PRs once every check has passed:

| Dependency | Policy |
| --- | --- |
| WebUI releases ([stalwartlabs/webui](https://github.com/stalwartlabs/webui/releases)) | Stable `vX.Y.Z` only, version and checksum in one PR; merged automatically one day after the release |
| BusyBox patch and digest updates | Merged automatically three days after the release |
| BusyBox minor and major, Dockerfile frontend, GitHub Actions, cosign | Manual review |

The delays let broken or withdrawn releases surface first; they say little about a compromised
dependency. A WebUI release whose asset is replaced later fails the build on the pinned
checksum. Each merge republishes; the chart pins the image by digest, and its own Renovate PR is
reviewed there.

## Development

```sh
podman build -t stalwart-webui:dev .
DOCKER=podman scripts/test-copy.sh stalwart-webui:dev
```

`scripts/verify_archive.py <image.tar> Dockerfile <platforms>` checks an OCI archive of the image;
`<platforms>` is the comma-separated list the archive must hold, as in `PLATFORMS` of the workflow.

## License

Apache License 2.0 for this repository; see [NOTICE](NOTICE) for the software in the image.
