#!/usr/bin/env bash
# Copy the production database to this machine with pg_dump.
#
# The Railway Hobby plan has no scheduled backups, so this is the manual
# substitute. See products/transelect/docs/deployment.md "Manual database
# backup" for the full procedure (open the TCP proxy, run, close it again).
#
# Usage:
#   DATABASE_PUBLIC_URL='postgresql://…' scripts/backup_prod_db.sh
#
# The URL is read from the environment only: never pass it as an argument
# (shell history) and never write it to a file in the repository.
# Backups go to $CAMPO_BACKUP_DIR (default ~/campo-digital-backups), outside
# the repository, because they contain client data.

set -euo pipefail

if [[ -z "${DATABASE_PUBLIC_URL:-}" ]]; then
  echo "DATABASE_PUBLIC_URL is not set (copy it from Railway: PostGIS → Variables)." >&2
  exit 2
fi

backup_dir="${CAMPO_BACKUP_DIR:-$HOME/campo-digital-backups}"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$backup_dir/campo-digital-prod-$stamp.dump"

# The Railway TCP proxy crosses the public internet: refuse to send client
# data unencrypted.
export PGSSLMODE="${PGSSLMODE:-require}"

umask 077
pg_dump --format=custom --no-owner --no-privileges \
  --dbname="$DATABASE_PUBLIC_URL" --file="$target.partial"

# A dump pg_restore can list is complete and readable.
pg_restore --list "$target.partial" > /dev/null
mv "$target.partial" "$target"

echo "Backup written: $target ($(du -h "$target" | cut -f1))"
