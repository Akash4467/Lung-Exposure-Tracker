#!/usr/bin/env bash
# Writes every parameter under $SSM_PREFIX (config Strings + SecureString secrets, decrypted)
# to a compose-style .env file readable only by root.
#   render-env.sh /opt/lung/.env
set -euo pipefail

OUT="${1:?usage: render-env.sh <output file>}"
# shellcheck source=/dev/null
. /etc/lung.env

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
chmod 600 "$TMP"

aws ssm get-parameters-by-path \
  --region "$AWS_REGION" --path "$SSM_PREFIX/" --recursive --with-decryption \
  --output json \
| python3 -c '
import json, sys
params = []
for page in [json.load(sys.stdin)]:
    params += page.get("Parameters", [])
for p in sorted(params, key=lambda p: p["Name"]):
    key = p["Name"].rsplit("/", 1)[-1]
    value = p["Value"]
    if "\x27" in value or "\n" in value:
        sys.exit(f"{key}: values may not contain single quotes or newlines")
    print(f"{key}=\x27{value}\x27")
' > "$TMP"

COUNT="$(wc -l < "$TMP")"
if [ "$COUNT" -lt 5 ]; then
  echo "only $COUNT parameters under $SSM_PREFIX; run infra apply and put-secrets.sh first" >&2
  exit 1
fi
install -m 600 "$TMP" "$OUT"
echo "rendered $COUNT parameters into $OUT"
