#!/usr/bin/env bash

set -euo pipefail

PIP_AUDIT_VERSION="2.10.1"

repo_root="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cd "$repo_root"

echo "=== Python runtime + API + Transelec dependencies ==="

uv export \
  --quiet \
  --frozen \
  --no-dev \
  --no-emit-project \
  --no-header \
  --no-annotate \
  --extra api \
  --extra transelec \
  --no-hashes \
  --format requirements-txt \
  -o "$tmp_dir/runtime-api.txt"

uvx "pip-audit==${PIP_AUDIT_VERSION}" \
  --no-deps \
  -r "$tmp_dir/runtime-api.txt"

echo
echo "=== Python optional geometry dependencies ==="

uv export \
  --quiet \
  --frozen \
  --no-dev \
  --no-emit-project \
  --no-header \
  --no-annotate \
  --extra geometry-extra \
  --no-hashes \
  --format requirements-txt \
  -o "$tmp_dir/geometry.txt"

uvx "pip-audit==${PIP_AUDIT_VERSION}" \
  --no-deps \
  -r "$tmp_dir/geometry.txt"

echo
echo "=== LiDAR dashboard production dependencies ==="

npm \
  --prefix products/lidar/dashboard \
  audit \
  --omit=dev \
  --audit-level=high

echo
echo "=== Transelec dashboard production dependencies ==="

npm \
  --prefix products/transelect/dashboard \
  audit \
  --omit=dev \
  --audit-level=high
