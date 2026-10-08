#!/usr/bin/env bash
# Restore a backup into the running Postgres. Destroys the current data.
#   restore.sh latest --yes
#   restore.sh postgres/2026/10/04/lung-20261004T203000Z.dump --yes
# The API and worker are stopped during the restore and started again after.
set -euo pipefail

WHICH="${1:?usage: restore.sh <s3 key | latest> --yes}"
[ "${2:-}" = "--yes" ] || { echo "this replaces the database; re-run with --yes" >&2; exit 1; }

# shellcheck source=/dev/null
. /etc/lung.env
set -a
# shellcheck source=/dev/null
. /opt/lung/.env
set +a

if [ "$WHICH" = "latest" ]; then
  WHICH="$(aws s3api list-objects-v2 --bucket "$BACKUP_BUCKET" --prefix postgres/ \
    --region "$AWS_REGION" --query 'sort_by(Contents, &LastModified)[-1].Key' --output text)"
fi
echo "restoring s3://$BACKUP_BUCKET/$WHICH"

compose() { docker compose -p lung -f /opt/lung/current/compose.prod.yml --env-file /opt/lung/.env "$@"; }
PG="$(docker ps -q -f label=com.docker.compose.project=lung -f label=com.docker.compose.service=postgres)"
[ -n "$PG" ] || { echo "postgres container is not running" >&2; exit 1; }

compose stop api worker
trap 'compose start api worker' EXIT

aws s3 cp "s3://$BACKUP_BUCKET/$WHICH" - --region "$AWS_REGION" \
  | docker exec -i "$PG" pg_restore -U lung -d lung --clean --if-exists --no-owner --single-transaction

echo "restore complete"
