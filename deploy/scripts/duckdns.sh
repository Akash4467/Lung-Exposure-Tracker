#!/usr/bin/env bash
# Every 5 minutes (lung-duckdns.timer): keep the DuckDNS name pointing at this server.
# With an Elastic IP the address never changes, so this is insurance (and it sets the
# record the first time). Skipped quietly if no DuckDNS token is configured.
set -euo pipefail
set -a
# shellcheck source=/dev/null
. /opt/lung/.env
set +a

[ -n "${DUCKDNS_TOKEN:-}" ] || exit 0
SUB="${DOMAIN%%.duckdns.org}"
[ "$SUB" != "$DOMAIN" ] || { echo "DOMAIN is not a duckdns.org name; nothing to do"; exit 0; }

# Empty ip= lets DuckDNS use the address the request comes from (the Elastic IP).
RESULT="$(curl -fsS --max-time 20 "https://www.duckdns.org/update?domains=$SUB&token=$DUCKDNS_TOKEN&ip=")"
[ "$RESULT" = "OK" ] || { echo "duckdns update failed: $RESULT" >&2; exit 1; }
