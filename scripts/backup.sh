#!/usr/bin/env sh
# Usage: DATABASE_URL=postgresql://... ./scripts/backup.sh   (or SQLite: ./scripts/backup.sh)
set -e
mkdir -p backups
TS=$(date +%Y%m%d-%H%M%S)
if [ -n "$DATABASE_URL" ] && echo "$DATABASE_URL" | grep -q '^postgres'; then
  pg_dump "$(echo "$DATABASE_URL" | sed 's/+asyncpg//')" | gzip > "backups/rmg-$TS.sql.gz"
else
  sqlite3 data/bot.db ".backup 'backups/rmg-$TS.db'"
fi
ls -1t backups | tail -n +15 | while read f; do rm -f "backups/$f"; done   # keep last 14
echo "Backup written: backups/*-$TS.*"
