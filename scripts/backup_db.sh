#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
DB_FILE="${APP_DIR}/data/forwarder.db"
BACKUP_DIR="${APP_DIR}/backups"
TIMESTAMP="$(date +'%Y%m%d_%H%M%S')"
BACKUP_TARGET="${BACKUP_DIR}/forwarder_backup_${TIMESTAMP}.db"

mkdir -p "${BACKUP_DIR}"

if [ ! -f "${DB_FILE}" ]; then
    echo "[!] Database file ${DB_FILE} does not exist yet. Skipping backup."
    exit 0
fi

echo "[*] Creating atomic SQLite backup..."
sqlite3 "${DB_FILE}" "VACUUM INTO '${BACKUP_TARGET}';"

gzip -9 "${BACKUP_TARGET}"
echo "[+] Backup successfully created at: ${BACKUP_TARGET}.gz"

find "${BACKUP_DIR}" -type f -name "forwarder_backup_*.db.gz" -mtime +14 -delete
echo "[+] Old backups pruned (retention: 14 days)."
