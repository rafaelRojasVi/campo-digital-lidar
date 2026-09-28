#!/bin/sh
# Container entrypoint for the Campo Digital API image.
#
# The image runs as the non-root `campo` user by default, and then this
# script only execs the command. Hosts that mount a persistent volume
# root-owned (Railway does, and documents RAILWAY_RUN_UID=0 as the remedy)
# start the container as root instead: in that case, and only then, make
# the configured object-store root writable by `campo` and drop privileges
# before the application starts. The API process never runs as root.
set -eu

if [ "$(id -u)" = "0" ]; then
    if [ -n "${CAMPO_OBJECT_STORE_ROOT:-}" ]; then
        # This mkdir succeeds with or without a volume attached; it proves
        # nothing about persistence. app.object_store.require_persistent_mount
        # makes production readiness fail when no volume is mounted there.
        mkdir -p "$CAMPO_OBJECT_STORE_ROOT"
        chown campo:campo "$CAMPO_OBJECT_STORE_ROOT"
    fi
    # One line in the host's deploy log proves this entrypoint ran at all
    # (a host-level start command or builder override would bypass it).
    echo "campo-entrypoint: started as root; object store ${CAMPO_OBJECT_STORE_ROOT:-<unset>}; dropping to campo" >&2
    # setpriv changes identity, not environment: without this HOME stays
    # /root, which `campo` cannot write (uv's cache lives under it).
    HOME="$(getent passwd campo | cut -d: -f6)"
    export HOME
    exec setpriv --reuid=campo --regid=campo --init-groups -- "$@"
fi

echo "campo-entrypoint: started as uid $(id -u); no privilege change" >&2
exec "$@"
