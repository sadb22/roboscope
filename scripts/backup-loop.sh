#!/bin/sh
set -eu
mkdir -p /backups
umask 077
while true; do
  backup_name="/backups/roboscope-$(date -u +%Y%m%d-%H%M%S).dump"
  if pg_dump --format=custom --file="$backup_name.tmp"; then
    mv "$backup_name.tmp" "$backup_name"
    echo "Backup completed"
  else
    echo "Backup failed" >&2
  fi
  sleep 86400
done
