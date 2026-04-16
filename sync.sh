#!/bin/bash
# sync.sh — Synkroniser kode fra OneDrive til /tmp (UDEN at overskrive databasen)
#
# Brug: bash sync.sh
# Kør dette script hver gang du vil opdatere koden i produktionsmiljøet.
# Databasen overskrives ALDRIG — kun kode-filer synkroniseres.

set -e

SRC="/Users/jesskristensen/Library/CloudStorage/OneDrive-repodio.dk/Systemate/Claude/relations-crm/backend/"
DST="/private/tmp/relations-crm/backend/"

echo "🔄 Synkroniserer kode (ekskluderer database)..."

# Sync kode — ekskluder alle database-filer
rsync -av --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' --exclude='*.db-journal' "$SRC" "$DST"

echo ""
echo "✅ Kode synkroniseret — databasen er urørt."
echo ""

# Verificer at DB stadig er intakt
DB="$DST/relations_crm.db"
if [ -f "$DB" ]; then
    COMPANIES=$(sqlite3 "$DB" "SELECT COUNT(*) FROM companies;" 2>/dev/null || echo "?")
    CONTACTS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM contacts;" 2>/dev/null || echo "?")
    echo "📊 Database status: $COMPANIES virksomheder, $CONTACTS kontakter"
else
    echo "⚠️  Ingen database fundet i $DST — kopier den manuelt:"
    echo "    cp '$SRC/relations_crm.db' '$DST/relations_crm.db'"
fi
