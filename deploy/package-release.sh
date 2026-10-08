#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
release_dir="${1:-dist/btc-signal-release}"
mkdir -p "$release_dir/wheelhouse" "$release_dir/deploy"
"${BTC_BUILD_PYTHON:-python3}" -m pip wheel --no-cache-dir --constraint deploy/constraints.txt --wheel-dir "$release_dir/wheelhouse" .
(cd "$release_dir/wheelhouse" && sha256sum ./*.whl > SHA256SUMS)
cp deploy/Dockerfile.release "$release_dir/Dockerfile"
cp -a alembic "$release_dir/"
cp alembic.ini "$release_dir/"
cp deploy/compose.yml deploy/env.example deploy/README.md "$release_dir/deploy/"
