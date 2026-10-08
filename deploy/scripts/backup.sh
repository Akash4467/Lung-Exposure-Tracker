#!/usr/bin/env bash
# Nightly (lung-backup.timer): a compressed pg_dump streamed straight to S3.
# Nothing is written to local disk, so a full disk can't break the backup.
set -euo pipefail
# shellcheck source=/dev/null
. /etc/lung.env
set -a
# shellcheck source=/dev/null
. /opt/lung/.env
set +a

PG="$(docker ps -q -f label=com.docker.compose.project=lung -f label=com.docker.compose.service=postgres)"
[ -n "$PG" ] || { echo "postgres container is not running" >&2; exit 1; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
KEY="postgres/$(date -u +%Y/%m/%d)/lung-$STAMP.dump"

docker exec "$PG" pg_dump -U lung -d lung --format=custom --compress=6 \
  | aws s3 cp - "s3://$BACKUP_BUCKET/$KEY" --region "$AWS_REGION" --sse AES256 --only-show-errors

SIZE="$(aws s3api head-object --bucket "$BACKUP_BUCKET" --key "$KEY" --region "$AWS_REGION" \
  --query ContentLength --output text)"
if [ "$SIZE" -lt 1024 ]; then
  echo "backup $KEY is only $SIZE bytes; something is wrong" >&2
  exit 1
fi
echo "backup ok: s3://$BACKUP_BUCKET/$KEY ($SIZE bytes)"
