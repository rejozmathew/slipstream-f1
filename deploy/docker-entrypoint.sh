#!/bin/sh
set -eu

if [ "$(id -u)" = "0" ]; then
    mkdir -p /data
    # Touch only the mount root; never walk the existing replay library.
    chown slipstream:slipstream /data
    chmod u+rwx /data
    exec gosu slipstream "$0" "$@"
fi

if [ "$(id -u)" != "10001" ]; then
    echo "Slipstream must run as its built-in user (UID 10001)." >&2
    exit 1
fi

exec python -m slipstream "$@"
