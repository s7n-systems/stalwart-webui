#!/usr/bin/env bash
# Runs the image as the chart's init container does: a non-root user other than the image's,
# a read-only root file system, and `cp` into a writable volume. The copy is then checked on
# the host, with the host's tools, against the SHA-256 pinned in the Dockerfile.
# Usage: scripts/test-copy.sh <image>   (uses docker; set DOCKER=podman to use podman)
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <image>" >&2
  exit 2
fi
image="$1"
docker="${DOCKER:-docker}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
sha256="$(sed -n 's/^ARG WEBUI_SHA256=//p' "$repo/Dockerfile")"

out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
# The volume belongs to the runner's user; the container writes into it as UID/GID 2000 like
# the chart's pod, so it must be writable for that user.
chmod 0777 "$out"

"$docker" run --rm --user 2000:2000 --read-only --cap-drop ALL --security-opt no-new-privileges \
  --network none -v "$out:/opt/stalwart/webui" "$image" \
  cp /webui/webui.zip /opt/stalwart/webui/webui-test.zip

actual="$(sha256sum "$out/webui-test.zip" | awk '{print $1}')"
if [ "$actual" != "$sha256" ]; then
  echo "Copied webui.zip is $actual, the Dockerfile pins $sha256" >&2
  exit 1
fi
echo "OK: $image copies webui.zip ($sha256) as UID 2000 with a read-only root file system"
