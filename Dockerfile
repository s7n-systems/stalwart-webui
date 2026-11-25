# syntax=docker.io/docker/dockerfile:1.29@sha256:572cebbc2b15e6f84c077742952674889cb63cd5e9b80abdffcbe587b6f19183

# Stalwart's WebUI bundle, unmodified, for Stalwart to load from a local file instead of
# downloading it from GitHub at runtime. busybox provides `cp` for the init container that
# copies the bundle into the Stalwart pod; the bundle itself is architecture-independent.
FROM docker.io/library/busybox:1.38.0-musl@sha256:80e38f9a1b39188b8bdb28879178edb322a4402b081a9aedda1924609decd6f6

# The release and the SHA-256 of its webui.zip. Renovate updates both together; the build
# fails if the downloaded file does not match.
# renovate: datasource=github-release-attachments depName=stalwartlabs/webui
ARG WEBUI_VERSION=v2.1.1
ARG WEBUI_SHA256=2c650f9c155bdb7b4087c0a55dd94f4a211dc0b160f49611cb5ad80383d1b1b7

ADD --checksum=sha256:${WEBUI_SHA256} --chmod=0444 \
    https://github.com/stalwartlabs/webui/releases/download/${WEBUI_VERSION}/webui.zip /webui/webui.zip
COPY --chmod=0444 licenses/ /licenses/

LABEL org.opencontainers.image.title="Stalwart WebUI bundle" \
      org.opencontainers.image.description="Unmodified webui.zip of stalwartlabs/webui ${WEBUI_VERSION}, for Stalwart to load from a file:// resource URL" \
      org.opencontainers.image.version="${WEBUI_VERSION}" \
      org.opencontainers.image.source="https://github.com/s7n-systems/stalwart-webui" \
      org.opencontainers.image.url="https://github.com/stalwartlabs/webui/releases/tag/${WEBUI_VERSION}" \
      org.opencontainers.image.licenses="AGPL-3.0-only OR LicenseRef-SEL" \
      eu.sovereign-systems.webui.sha256="${WEBUI_SHA256}"

USER 65532:65532
