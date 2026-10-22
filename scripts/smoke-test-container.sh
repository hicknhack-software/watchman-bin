#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install --no-install-recommends -y libaio1t64 libssl3t64 libunwind8
cd /artifacts
sha256sum -c "$ARCHIVE.sha256"
tar -xzf "$ARCHIVE" -C /usr/local
ldconfig
mkdir -p /usr/local/var/run/watchman
chmod 2777 /usr/local/var/run/watchman
watchman --version | tee /tmp/watchman-version
grep -Fx "$EXPECTED_VERSION" /tmp/watchman-version
ldd /usr/local/bin/watchman | tee /tmp/watchman-ldd
if grep -q 'not found' /tmp/watchman-ldd; then
  echo 'Missing runtime libraries' >&2
  exit 1
fi
# Install the test driver only after checking the actual runtime dependencies.
apt-get install --no-install-recommends -y python3
rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*
# Exercise the daemon and inotify as an ordinary user, on the container filesystem.
su -s /bin/sh nobody -c 'python3 /scripts/smoke-test-user.py'
