# Watchman binaries for Debian trixie

This project builds [facebook/watchman](https://github.com/facebook/watchman) releases into downloadable archives, so development images can install Watchman without compiling its C++, Rust, and third-party dependencies.

The initial target is **Debian 13 (trixie), Linux x86-64 (`amd64`)**. Builds run with `docker run` using `debian:trixie-slim`. Each archive contains Watchman and its non-system shared libraries, installed under `/usr/local`. EdenFS support is disabled; the native Linux inotify watcher is enabled. These archives target trixie; they are not intended for Alpine or older Debian releases.

## Release automation

[The GitHub Actions workflow](.github/workflows/releases.yml) checks upstream every hour at minute 17. GitHub does not deliver another repository's release events to this repository, so detection uses polling. Scheduled runs can be delayed by GitHub.

On its first run, the workflow builds the latest stable upstream release. Thereafter it builds all missing stable releases published since that initial release, including releases missed during downtime. Drafts and prereleases are skipped automatically. A manual run can build or rebuild a specific upstream release by setting `upstream_tag`, for example `v2026.10.19.00`. Leave it empty to run the normal check.

For each release, the workflow:

1. Checks out the upstream release tag.
2. Installs build tools and Rust in a Debian trixie container, then builds with upstream's `getdeps.py`.
3. Bundles and strips non-system shared libraries using `fixup-dyn-deps` and creates a `.tar.gz` archive plus a SHA-256 checksum.
4. Tests the archive in `ghcr.io/hicknhack-software/ruby-dev:3.4.11` and minimal Debian trixie. Tests check the version and dynamic libraries, start the daemon as an unprivileged user, and verify detection of a newly created file.
5. Creates a release in this repository with the **same tag and title** as upstream, and uploads both files. Publication uses a separate job with write permission and only starts after all builds and tests pass. A new release stays in draft until both uploads succeed.

Enable Actions and put the workflow on this repository's **default branch**. It uses the built-in `GITHUB_TOKEN`; no personal access token or extra secrets are required. Repository or organization policy must allow the publishing job `contents: write`. Start the first build from **Actions → Build upstream Watchman releases → Run workflow**. The local Git tags refer to this packaging repository; the original upstream source commit is recorded inside each archive at `share/doc/watchman/build-info.txt`.

GitHub can disable scheduled workflows in public repositories after 60 days without repository activity; check that the schedule remains enabled. See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Install an archive manually

Run these commands on Debian trixie x86-64. Set `REPOSITORY` to the GitHub repository hosting this project if its name differs.

```sh
REPOSITORY=hicknhack-software/watchman-bin
WATCHMAN_TAG=v2026.10.19.00
ARCHIVE="watchman-${WATCHMAN_TAG}-debian-trixie-amd64.tar.gz"
URL="https://github.com/${REPOSITORY}/releases/download/${WATCHMAN_TAG}"

sudo apt-get update
sudo apt-get install --no-install-recommends -y \
  ca-certificates curl libaio1t64 libssl3t64 libunwind8

mkdir -p /tmp/watchman-install
cd /tmp/watchman-install
curl --fail --show-error --location --remote-name "${URL}/${ARCHIVE}"
curl --fail --show-error --location --remote-name "${URL}/${ARCHIVE}.sha256"
sha256sum -c "${ARCHIVE}.sha256"
sudo tar -xzf "$ARCHIVE" -C /usr/local
sudo ldconfig
sudo mkdir -p /usr/local/var/run/watchman
sudo chmod 2777 /usr/local/var/run/watchman

watchman --version
watchman version
```

Extract the **whole archive**, including `lib/`, into `/usr/local`. The binary references bundled libraries at that prefix; copying only `bin/watchman` or installing at a different prefix will not work. Run Watchman commands as the user who owns the project being watched. The archive includes Watchman's license, third-party license notices, and a build record.

## Use in a Dockerfile

This replaces the expensive `watchman-build` stage. It downloads and verifies the prebuilt archive during the image build; no compiler or Rust toolchain is needed.

```dockerfile
# syntax=docker/dockerfile:1
ARG RUBY_VERSION=3.4.11
FROM ghcr.io/hicknhack-software/ruby-dev:${RUBY_VERSION}

ARG WATCHMAN_REPOSITORY=hicknhack-software/watchman-bin
ARG WATCHMAN_TAG=v2026.10.19.00

RUN <<'INSTALL'
  set -eu
  test "$(dpkg --print-architecture)" = amd64
  apt-get update -qq
  apt-get install --no-install-recommends -y \
    ca-certificates curl libaio1t64 libssl3t64 libunwind8
  rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

  archive="watchman-${WATCHMAN_TAG}-debian-trixie-amd64.tar.gz"
  url="https://github.com/${WATCHMAN_REPOSITORY}/releases/download/${WATCHMAN_TAG}"
  mkdir /tmp/watchman-install
  cd /tmp/watchman-install
  curl --fail --show-error --silent --location "$url/$archive" -o "$archive"
  curl --fail --show-error --silent --location "$url/$archive.sha256" -o "$archive.sha256"
  sha256sum -c "$archive.sha256"
  tar -xzf "$archive" -C /usr/local
  cd /
  rm -rf /tmp/watchman-install

  ldconfig
  mkdir -p /usr/local/var/run/watchman
  chmod 2777 /usr/local/var/run/watchman
  watchman --version
INSTALL

ENV TZ=Europe/Berlin
```

Build for `linux/amd64` if your Docker host uses another architecture. The runtime container's user can start its own Watchman daemon when needed; Watchman does not need to run during `docker build`.

## Build and verify locally

Requirements: Docker running Linux containers, Bash, Git (when providing an existing checkout), sufficient disk space, and network access to Debian, GitHub, and Rust registries. The first build compiles a large dependency graph and can take a long time. Subsequent builds reuse a Docker volume containing the getdeps and Rust files.

```sh
# Build directly from the upstream tag.
BUILD_JOBS=2 bash scripts/build.sh v2026.10.19.00

# Install the result in a fresh Ruby development container and run the smoke test.
bash scripts/smoke-test.sh v2026.10.19.00

# Also check a minimal trixie container.
bash scripts/smoke-test.sh v2026.10.19.00 debian:trixie-slim
```

Artifacts appear in `dist/`:

```text
watchman-v2026.10.19.00-debian-trixie-amd64.tar.gz
watchman-v2026.10.19.00-debian-trixie-amd64.tar.gz.sha256
```

Optionally pass an existing upstream checkout as the second argument to `scripts/build.sh`; it must be at the requested tag. The build copies that checkout into its volume before applying the EdenFS build adjustments. `BUILD_JOBS` defaults to 2 to limit compiler memory use; increase it on larger machines. `WATCHMAN_BUILD_VOLUME` overrides the default volume name, `watchman-trixie-build`. Do not share one build volume between concurrent builds.

The smoke test installs Python only for its test driver; using Watchman's binary does not require Python. It checks the generated archive rather than any files left inside the build container. Upstream's full test suite is not run.

To check release discovery logic without Docker:

```sh
python3 -m unittest discover -s tests -v
```

Build dependency revisions and toolchains follow the upstream release's getdeps manifests and the current Debian/Rust repositories. This project does not promise reproducible byte-for-byte output.
