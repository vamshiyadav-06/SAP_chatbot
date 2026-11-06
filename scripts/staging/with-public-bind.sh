#!/usr/bin/env bash
# Optional exposure after an owner review. Staging basic auth remains enabled; only this script binds
# ports publicly. Use deploy.sh for all builds and keep registration disabled.
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 - <<'PY'
from pathlib import Path
import re
v = dict(re.match(r'^([^#=]+)=(.*)$', line).groups() for line in Path('.env').read_text().splitlines()
         if re.match(r'^([^#=]+)=(.*)$', line))
if (v.get('ACCESS_MODE') != 'basic_auth' or v.get('REGISTRATION_ENABLED', '').lower() != 'false'
        or not v.get('STAGING_BASIC_AUTH_USER') or not v.get('STAGING_BASIC_AUTH_HASH')
        or 'change-me' in v.get('STAGING_BASIC_AUTH_HASH', '').lower()):
    raise SystemExit('Refusing public bind unless staging Basic auth has a user/hash and registration is closed.')
PY
export COMPOSE_PROJECT_NAME=sap_brim_staging
export WEB_BIND=0.0.0.0
[[ -f .deploy/staging-image-tag ]] || { echo "Run deploy.sh successfully first." >&2; exit 1; }
export IMAGE_TAG="$(cat .deploy/staging-image-tag)"
docker compose -f docker-compose.prod.yml up -d
echo "Staging gate remains enabled. Restrict 80/443 at the Ubuntu firewall to approved tester IPs."
