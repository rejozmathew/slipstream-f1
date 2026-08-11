#!/bin/sh
set -eu

STACK_DIR="${STACK_DIR:-/mnt/user/appdata/slipstream-f1}"
cd "$STACK_DIR"

docker compose pull slipstream
docker compose up -d --remove-orphans --wait
docker compose ps
