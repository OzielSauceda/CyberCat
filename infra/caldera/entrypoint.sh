#!/usr/bin/env bash
# CyberCat: Caldera 4.2.0 entrypoint.
#
# We run with `--insecure`, which makes Caldera load conf/default.yml
# instead of conf/local.yml. default.yml ships hardcoded keys
# (api_key_red: ADMIN123, api_key_blue: BLUEADMIN123). Phase 21's scorer
# reads CALDERA_API_KEY from infra/compose/.env (auto-provisioned by
# start.sh on first run). To make the two agree without forking
# default.yml, we patch the keys in place at container start using sed,
# then exec the server. If CALDERA_API_KEY is unset (image run outside
# compose, manual debugging), we leave the upstream defaults alone.
set -e

CONF=/usr/src/app/conf/default.yml

if [ -n "${CALDERA_API_KEY}" ] && [ -f "$CONF" ]; then
    sed -i "s|^api_key_red:.*|api_key_red: ${CALDERA_API_KEY}|" "$CONF"
    sed -i "s|^api_key_blue:.*|api_key_blue: ${CALDERA_API_KEY}|" "$CONF"
    echo "entrypoint.sh: injected CALDERA_API_KEY into ${CONF}"
fi

exec python3 server.py --insecure "$@"
