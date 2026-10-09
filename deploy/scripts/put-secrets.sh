#!/usr/bin/env bash
# Run on YOUR machine (AWS CLI logged in) once before the first deploy, and again to change
# a value. Stores secrets as SSM SecureStrings under /lung/<env>/; nothing is written to disk
# and nothing goes into OpenTofu state.
#   deploy/scripts/put-secrets.sh demo
# Press Enter to keep an existing value (or to auto-generate where offered).
set -euo pipefail
# Git Bash on Windows would rewrite "/lung/demo/..." into a Windows path
export MSYS_NO_PATHCONV=1

ENV_NAME="${1:-demo}"
REGION="${AWS_REGION:-ap-south-1}"
PREFIX="/lung/$ENV_NAME"

# python3, or uv's Python where there is no python3 (Git Bash on Windows)
py() {
  if command -v python3 >/dev/null 2>&1; then python3 "$@"; else uv run --no-project python "$@"; fi
}

exists() {
  aws ssm get-parameter --region "$REGION" --name "$PREFIX/$1" >/dev/null 2>&1
}

put() { # name type value
  aws ssm put-parameter \
    --region "$REGION" \
    --cli-input-json "$(python3 -c 'import json,sys; print(json.dumps({"Name":sys.argv[1],"Type":sys.argv[2],"Value":sys.argv[3],"Overwrite":True}))' "$PREFIX/$1" "$2" "$3")" \
    >/dev/null
  echo "  saved $PREFIX/$1 ($2)"
}

ask() { # name type prompt [generate]
  local name="$1" type="$2" prompt="$3" gen="${4:-}" value=""
  local state="not set"
  if exists "$name"; then state="set"; fi
  if [ "$type" = "SecureString" ]; then
    read -r -s -p "$prompt [$state${gen:+, Enter = generate}]: " value; echo
  else
    read -r -p "$prompt [$state]: " value
  fi
  if [ -z "$value" ] && [ -n "$gen" ] && [ "$state" = "not set" ]; then
    value="$(py -c 'import secrets; print(secrets.token_urlsafe(48))')"
    echo "  generated a random value"
  fi
  if [ -n "$value" ]; then put "$name" "$type" "$value"; fi
}

echo "Secrets for $PREFIX in $REGION"
ask POSTGRES_PASSWORD SecureString "Postgres password" generate
ask JWT_SECRET        SecureString "JWT signing secret (32+ chars)" generate
ask BREVO_API_KEY     SecureString "Brevo API key"
ask MAIL_FROM         String       "Sender email (verified in Brevo)"
ask ORS_API_KEY       SecureString "OpenRouteService API key (optional)"
ask GOOGLE_CLIENT_IDS String       "Google OAuth client IDs, comma-separated (optional for now)"
ask FCM_PROJECT_ID    String       "Firebase project ID (optional for now)"
read -r -p "Path to Firebase service-account JSON (optional, Enter to skip): " SA
if [ -n "$SA" ]; then
  put FCM_SERVICE_ACCOUNT_JSON SecureString "$(py -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))))' "$SA")"
fi
ask ACME_EMAIL        String       "Email for Let's Encrypt expiry notices"
ask DUCKDNS_TOKEN     SecureString "DuckDNS token"
ask GHCR_USER         String       "GitHub user for pulling private images (optional)"
ask GHCR_TOKEN        SecureString "GitHub token with read:packages (optional; skip if images are public)"
echo "Done. Values take effect on the next deploy."
