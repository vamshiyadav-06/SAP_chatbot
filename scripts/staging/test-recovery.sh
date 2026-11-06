#!/usr/bin/env bash
# Verify a real custom-format dump can be restored into a separate database on the staging server.
# The source database is read-only to this script. The recovery database and dump are retained for
# inspection; this script intentionally has no DROP / rm cleanup path.
set -euo pipefail
cd "$(dirname "$0")/../.."
export COMPOSE_PROJECT_NAME=sap_brim_staging
stamp=$(date -u +%Y%m%d%H%M%S)
recovery_db="sap_brim_recovery_${stamp}"

docker compose -f docker-compose.prod.yml exec -T postgres sh -ec '
  set -eu
  backup="/tmp/sap_brim_recovery_'"$stamp"'.dump"
  recovery_db="'"$recovery_db"'"
  pg_dump -U sap_brim_ai -d sap_brim_ai -Fc -f "$backup"
  test -s "$backup"
  pg_restore --list "$backup" >/dev/null
  createdb -U "$POSTGRES_USER" -O sap_brim_ai "$recovery_db"
  pg_restore -U "$POSTGRES_USER" -d "$recovery_db" --no-owner --role=sap_brim_ai --no-comments --exit-on-error "$backup"
  psql -v ON_ERROR_STOP=1 -At -U sap_brim_ai -d "$recovery_db" -c "SELECT version_num FROM alembic_version" | grep -Eq "^[0-9a-f]+$"
  printf "Recovery verified: database=%s; dump=%s (retained).\n" "$recovery_db" "$backup"
'
