#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
[[ $(dpkg --print-architecture) == amd64 ]]
[[ ${BUILD_JOBS:-2} =~ ^[1-9][0-9]*$ ]]
apt-get update -qq
apt-get install --no-install-recommends -y \
  autoconf automake bison build-essential ca-certificates cmake curl flex git \
  libaio-dev libiberty-dev libssl-dev libtool libunwind-dev ninja-build patchelf pkg-config \
  python3 python3-dev python3-setuptools unzip zip zstd
export CARGO_HOME=/scratch/cargo RUSTUP_HOME=/scratch/rustup
export CARGO_BUILD_JOBS="${BUILD_JOBS:-2}"
export PATH="$CARGO_HOME/bin:$PATH"
if ! command -v rustc >/dev/null; then
  curl --fail --show-error --silent --location https://sh.rustup.rs -o /tmp/rustup.sh
  sh /tmp/rustup.sh -y --profile minimal
fi

src=/scratch/source
rm -rf "$src"
if [[ -d /source ]]; then
  cp -a --no-preserve=ownership /source "$src"
else
  git clone --depth 1 --branch "$WATCHMAN_TAG" https://github.com/facebook/watchman.git "$src"
fi
cd "$src"
[[ $(git describe --tags --exact-match HEAD) == "$WATCHMAN_TAG" ]]
commit=$(git rev-parse HEAD)

# The release archive omits EdenFS headers. Watchman still supports Linux inotify.
cat >> build/fbcode_builder/manifests/watchman <<'CMAKE'

[cmake.defines]
ENABLE_EDEN_SUPPORT=OFF
CMAKE
# Edencommon exports references to these CMake targets even with EdenFS disabled.
cat >> CMakeLists.txt <<'CMAKE'

find_package(fizz CONFIG REQUIRED)
find_package(wangle CONFIG REQUIRED)
find_package(FBThrift CONFIG REQUIRED)
find_package(fb303 CONFIG REQUIRED)
CMAKE
export WATCHMAN_VERSION_OVERRIDE="${WATCHMAN_TAG#v}"
getdeps=(python3 build/fbcode_builder/getdeps.py --allow-system-packages)
args=(--scratch-path=/scratch/getdeps --no-tests --src-dir=. --project-install-prefix=watchman:/usr/local)
"${getdeps[@]}" build "${args[@]}" --num-jobs="${BUILD_JOBS:-2}" --free-up-disk watchman
package=/scratch/package
rm -rf "$package"
"${getdeps[@]}" fixup-dyn-deps "${args[@]}" \
  --final-install-prefix=/usr/local --strip watchman "$package"
mkdir -p "$package/share/doc/watchman"
cp LICENSE "$package/share/doc/watchman/LICENSE"
"${getdeps[@]}" query-paths "${args[@]}" --recursive watchman > /scratch/dependency-paths.txt
python3 /workspace/scripts/collect-licenses.py /scratch/dependency-paths.txt "$package"
cat > "$package/share/doc/watchman/build-info.txt" <<EOF
Upstream: https://github.com/facebook/watchman
Tag: $WATCHMAN_TAG
Commit: $commit
Platform: Debian trixie, linux/amd64
Prefix: /usr/local
EdenFS: disabled
EOF
archive="watchman-${WATCHMAN_TAG}-debian-trixie-amd64.tar.gz"
tar -C "$package" -czf "/output/$archive" .
cd /output
sha256sum "$archive" > "$archive.sha256"
echo "Built /output/$archive"
