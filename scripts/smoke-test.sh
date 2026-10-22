#!/usr/bin/env bash
set -euo pipefail
tag=${1:?Usage: scripts/smoke-test.sh UPSTREAM_TAG [IMAGE]}
image=${2:-ghcr.io/hicknhack-software/ruby-dev:3.4.11}
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
archive="watchman-${tag}-debian-trixie-amd64.tar.gz"
docker run --rm --platform linux/amd64 --user root \
  --mount "type=bind,src=$root/dist,dst=/artifacts,readonly" \
  --mount "type=bind,src=$root/scripts,dst=/scripts,readonly" \
  --env "ARCHIVE=$archive" --env "EXPECTED_VERSION=${tag#v}" \
  --entrypoint bash "$image" /scripts/smoke-test-container.sh
