#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "==> Building charlyn-sandbox Docker image with ani-cli and ffmpeg..."
docker build -t charlyn-sandbox:latest -f Dockerfile.sandbox .
echo "==> Done. Image built: charlyn-sandbox:latest"
