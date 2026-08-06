#!/usr/bin/env bash

set -euo pipefail

: "${RELEASE_TAG:?RELEASE_TAG is required}"
: "${ARTIFACT_VERSION:?ARTIFACT_VERSION is required}"
: "${ANDROID_DIST:?ANDROID_DIST is required}"
: "${OUTPUT_DIR:?OUTPUT_DIR is required}"

PREVIOUS_TAG="${PREVIOUS_TAG:-v8.1.1_10}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SOURCE_COMMIT="$(git -C "$REPOSITORY_ROOT" rev-parse HEAD)"
WORK_DIR="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ffmpeg-kit-compliance-source"
FORK_DIR="$WORK_DIR/ffmpeg-kit-next-$RELEASE_TAG"
THIRD_PARTY_DIR="$WORK_DIR/third-party-sources-$RELEASE_TAG"
CHECKOUT_DIR="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ffmpeg-kit-dependency-checkouts"

mkdir -p "$FORK_DIR" "$THIRD_PARTY_DIR" "$CHECKOUT_DIR" "$OUTPUT_DIR"

git -C "$REPOSITORY_ROOT" archive HEAD | tar -xf - -C "$FORK_DIR"
git -C "$REPOSITORY_ROOT" diff --binary "$PREVIOUS_TAG"..HEAD \
  > "$FORK_DIR/changes.diff"
git -C "$REPOSITORY_ROOT" log --reverse --format='%H %s' \
  "$PREVIOUS_TAG"..HEAD > "$FORK_DIR/CHANGES-SINCE-$PREVIOUS_TAG.txt"

cp "$REPOSITORY_ROOT/compliance/COMPLIANCE-REBUILD.md" \
  "$FORK_DIR/COMPLIANCE-REBUILD.md"
tar -C "$WORK_DIR" -czf \
  "$OUTPUT_DIR/ffmpeg-kit-next-source-$RELEASE_TAG.tar.gz" \
  "ffmpeg-kit-next-$RELEASE_TAG"

manifest="$THIRD_PARTY_DIR/SOURCES_MANIFEST.txt"
printf '%s\n' \
  "FFmpegKitNext release: $RELEASE_TAG" \
  "Generated from source commit: $SOURCE_COMMIT" \
  "" > "$manifest"

archive_dependency() {
  local name="$1"
  local repository="$2"
  local revision="$3"
  local repository_dir="$CHECKOUT_DIR/$name"
  local destination="$THIRD_PARTY_DIR/$name"

  if [[ ! -d "$repository_dir/.git" ]]; then
    git init -q "$repository_dir"
    git -C "$repository_dir" remote add origin "$repository"
  else
    git -C "$repository_dir" remote set-url origin "$repository"
  fi

  if git -C "$repository_dir" rev-parse --verify HEAD^{commit} >/dev/null 2>&1; then
    git -C "$repository_dir" checkout -q --detach HEAD
  else
    local fetch_succeeded=0
    for attempt in 1 2 3; do
      if git -C "$repository_dir" fetch --depth=1 origin "$revision"; then
        fetch_succeeded=1
        break
      fi
      echo "Source fetch failed for $name (attempt $attempt of 3)." >&2
      sleep $((attempt * 5))
    done
    if [[ $fetch_succeeded -ne 1 ]]; then
      echo "Failed to fetch corresponding source for $name at $revision." >&2
      return 1
    fi
    git -C "$repository_dir" checkout -q --detach FETCH_HEAD
  fi
  local resolved_commit
  resolved_commit="$(git -C "$repository_dir" rev-parse HEAD)"

  mkdir -p "$destination"
  git -C "$repository_dir" archive HEAD | tar -xf - -C "$destination"
  printf '%-14s requested=%-45s commit=%s source=%s\n' \
    "$name" "$revision" "$resolved_commit" "$repository" >> "$manifest"
}

archive_dependency ffmpeg \
  https://github.com/arthenica/FFmpeg n8.1.2
archive_dependency gnu-config \
  https://github.com/arthenica/gnu-config v20210814
archive_dependency lame \
  https://github.com/arthenica/lame RELEASE__3_100
archive_dependency libvpx \
  https://github.com/arthenica/libvpx v1.16.0
archive_dependency libiconv \
  https://github.com/arthenica/libiconv v1.17
archive_dependency cpu_features \
  https://github.com/arthenica/cpu_features v0.11.0
archive_dependency x264 \
  https://github.com/arthenica/x264 b35605ace3ddf7c1a5d67a2eb553f034aef41d55
archive_dependency x265 \
  https://github.com/arthenica/x265 4.2

cp "$REPOSITORY_ROOT/compliance/THIRD_PARTY_NOTICES.md" \
  "$THIRD_PARTY_DIR/THIRD_PARTY_NOTICES.md"
tar -C "$WORK_DIR" -czf \
  "$OUTPUT_DIR/third-party-sources-$RELEASE_TAG.tar.gz" \
  "third-party-sources-$RELEASE_TAG"

cp "$REPOSITORY_ROOT/LICENSE" "$OUTPUT_DIR/COPYING.LGPLv3"
cp "$REPOSITORY_ROOT/compliance/THIRD_PARTY_NOTICES.md" \
  "$OUTPUT_DIR/THIRD_PARTY_NOTICES.md"
cp "$REPOSITORY_ROOT/compliance/SOURCE_OFFER.md" "$OUTPUT_DIR/SOURCE_OFFER.md"

build_info="$OUTPUT_DIR/BUILD_INFO.txt"
cat > "$build_info" <<EOF
FFmpegKitNext Android Build Information
=======================================
Release tag: $RELEASE_TAG
Artifact version: $ARTIFACT_VERSION
Fork source commit: $SOURCE_COMMIT
Previous release comparison base: $PREVIOUS_TAG
Runner OS: ubuntu-24.04
Nix Android package: android-r27d
Android minimum API: 24
Native linkage: shared FFmpeg libraries

LGPLv3 all-ABI build command:
  ./nix-android.sh -p android-r27d --enable-libvpx --enable-lame --enable-android-media-codec

GPLv3 all-ABI build command:
  ./nix-android.sh -p android-r27d --enable-libvpx --enable-lame --enable-android-media-codec --enable-gpl --enable-x264 --enable-x265

Corresponding dependency revisions:
EOF
sed 's/^/  /' "$manifest" >> "$build_info"

for license_family in lgpl3 gpl3; do
  aar="$ANDROID_DIST/ffmpeg-kit-next-$ARTIFACT_VERSION-android-all-$license_family.aar"
  test -f "$aar"
  archive_entries="$(unzip -Z1 "$aar")"
  abi_entry="$(grep -Em1 '^jni/arm64-v8a/libavutil(_neon)?\.so$' <<< "$archive_entries")"
  test -n "$abi_entry"
  binary="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/libavutil-$license_family.so"
  metadata="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/libavutil-$license_family.strings"
  unzip -p "$aar" "$abi_entry" > "$binary"
  "$PYTHON_BIN" - "$binary" > "$metadata" <<'PY'
import re
import sys

with open(sys.argv[1], "rb") as binary_file:
    binary_data = binary_file.read()

for value in re.findall(rb"[\x20-\x7e]{4,}", binary_data):
    print(value.decode("ascii"))
PY
  configure_line="$(grep -Fm1 -- '--enable-shared' "$metadata")"
  license_line="$(grep -Fm1 'libavutil license:' "$metadata")"
  test -n "$configure_line"
  test -n "$license_line"

  cat >> "$build_info" <<EOF

$license_family AAR: $(basename "$aar")
SHA-256: $(sha256sum "$aar" | awk '{print $1}')
$license_line
FFmpeg configuration:
$configure_line
EOF
done
