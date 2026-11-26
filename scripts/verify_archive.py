#!/usr/bin/env python3
"""Checks a multi-platform OCI archive of the image from the outside: nothing in the image runs.

For every platform image: /webui/webui.zip has the SHA-256 pinned in the Dockerfile, the zip's
stalwart-app.json names the pinned version, the licence texts are present, any user can read
them and enter their directories (the chart copies as a UID of its own), and the image runs as
UID 65532. The platforms are exactly the expected ones: the init container runs BusyBox cp,
which has an architecture even though the bundle does not. Prints the digest of the archive's
top-level index, which publishing preserves.

Usage: python3 -I scripts/verify_archive.py <image.tar> <Dockerfile> <platforms>
  platforms: comma-separated, as given to the build, e.g. linux/amd64,linux/arm/v7
"""
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
import zipfile

WANTED = {"webui/webui.zip", "licenses/AGPL-3.0-only.txt", "licenses/LicenseRef-SEL.txt"}
INDEX_TYPES = {"application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json"}


def fail(message):
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def platform_name(os_, architecture, variant=None):
    """os/arch[/variant], with arm64/v8 as plain arm64, as containerd normalizes it."""
    if architecture == "arm64" and variant in ("v8", "8"):
        variant = None
    return "/".join(filter(None, (os_, architecture, variant)))


def pinned(dockerfile):
    text = open(dockerfile, encoding="utf-8").read()
    version = re.search(r"^ARG WEBUI_VERSION=(v\d+\.\d+\.\d+)$", text, re.M)
    sha256 = re.search(r"^ARG WEBUI_SHA256=([a-f0-9]{64})$", text, re.M)
    if not version or not sha256:
        fail("WEBUI_VERSION (vX.Y.Z) or WEBUI_SHA256 missing in the Dockerfile")
    return version.group(1), sha256.group(1)


class Archive:
    def __init__(self, path):
        self.tar = tarfile.open(path)
        # Member names with or without a leading "./", as tar writes them for a directory.
        self.members = {m.name.removeprefix("./"): m for m in self.tar.getmembers() if m.isfile()}

    def read(self, name):
        if name not in self.members:
            fail(f"{name} missing from the archive")
        return self.tar.extractfile(self.members[name]).read()

    def blob(self, digest):
        algorithm, value = digest.split(":", 1)
        data = self.read(f"blobs/{algorithm}/{value}")
        if algorithm != "sha256" or hashlib.sha256(data).hexdigest() != value:
            fail(f"blob {digest} does not match its digest")
        return data

    def json(self, digest):
        return json.loads(self.blob(digest))

    def images(self, descriptor):
        """(platform, manifest) for every image below a descriptor, skipping attestations."""
        if descriptor["mediaType"] in INDEX_TYPES:
            for child in self.json(descriptor["digest"])["manifests"]:
                yield from self.images(child)
            return
        platform = descriptor.get("platform", {})
        if platform.get("os") == "unknown":
            return
        yield platform, self.json(descriptor["digest"])


def layer_files(data, modes):
    """Regular files in a layer, by path; later layers override earlier ones. Records the mode
    of the wanted files and of every directory in modes."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as layer:
        for member in layer:
            name = member.name.lstrip("./").rstrip("/")
            if member.isfile() and name in WANTED:
                files[name] = layer.extractfile(member).read()
                modes[name] = member.mode
            elif member.isdir():
                modes[name] = member.mode
    return files


def unreadable(modes):
    """Wanted files others cannot read, and directories on their paths others cannot enter."""
    problems = []
    for name in sorted(WANTED):
        if not modes.get(name, 0) & 0o004:
            problems.append(f"{name} {oct(modes.get(name, 0))}")
        parts = name.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            directory = "/".join(parts[:i])
            # A directory missing from the layers comes from the base image (0755 there).
            if directory in modes and not modes[directory] & 0o001:
                problems.append(f"{directory}/ {oct(modes[directory])}")
    return sorted(set(problems))


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    version, sha256 = pinned(sys.argv[2])
    expected = [platform_name(*p.strip().split("/")) for p in sys.argv[3].split(",") if p.strip()]
    archive = Archive(sys.argv[1])
    index = json.loads(archive.read("index.json"))
    if len(index["manifests"]) != 1:
        fail(f"expected one top-level manifest, found {len(index['manifests'])}")
    top = index["manifests"][0]

    platforms = []
    for platform, manifest in archive.images(top):
        name = platform_name(platform.get("os"), platform.get("architecture"), platform.get("variant"))
        files, modes = {}, {}
        for layer in manifest["layers"]:
            files.update(layer_files(archive.blob(layer["digest"]), modes))
        missing = WANTED - files.keys()
        if missing:
            fail(f"{name}: missing {', '.join(sorted(missing))}")
        problems = unreadable(modes)
        if problems:
            fail(f"{name}: not readable for other users: {', '.join(problems)}")
        actual = hashlib.sha256(files["webui/webui.zip"]).hexdigest()
        if actual != sha256:
            fail(f"{name}: webui.zip is {actual}, the Dockerfile pins {sha256}")
        app = json.loads(zipfile.ZipFile(io.BytesIO(files["webui/webui.zip"])).read("stalwart-app.json"))
        if app.get("id") != "webui" or f"v{app.get('version')}" != version:
            fail(f"{name}: bundle manifest says {app}, the Dockerfile pins {version}")
        user = archive.json(manifest["config"]["digest"]).get("config", {}).get("User", "")
        if user.split(":")[0] != "65532":
            fail(f"{name}: image user is {user!r}, expected 65532")
        platforms.append(name)

    if not platforms:
        fail("no platform images in the archive")
    if len(set(platforms)) != len(platforms):
        fail(f"a platform appears twice: {', '.join(platforms)}")
    if set(platforms) != set(expected):
        missing, extra = sorted(set(expected) - set(platforms)), sorted(set(platforms) - set(expected))
        fail(f"platforms differ from the build's: missing {', '.join(missing) or 'none'}, unexpected {', '.join(extra) or 'none'}")
    print(f"OK: webui {version} ({sha256}) in {', '.join(platforms)}")
    print(f"index digest: {top['digest']}")


if __name__ == "__main__":
    main()
