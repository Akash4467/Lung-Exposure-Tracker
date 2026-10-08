#!/usr/bin/env bash
# Runs ON the server (sent by GitHub Actions through SSM Run Command):
#   deploy.sh <release-id> <image-repo>      e.g. deploy.sh 3f2a1c9 ghcr.io/akash
# The release bundle is already unpacked in /opt/lung/releases/<release-id>.
#
# Steps: secrets from SSM -> pull images -> migrate -> start/replace containers and wait
# until healthy -> point "current" at this release -> refresh timers -> tidy up.
# If the new containers don't become healthy, the previous release is started again.
set -euo pipefail

RELEASE="${1:?release id}"
IMAGE_REPO="${2:?image repo, e.g. ghcr.io/owner}"
ROOT=/opt/lung
DIR="$ROOT/releases/$RELEASE"
ENV_FILE="$ROOT/.env"
# shellcheck source=/dev/null
. /etc/lung.env

log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }

compose() {
  docker compose -p lung -f "$1/compose.prod.yml" --env-file "$ENV_FILE" "${@:2}"
}

[ -d "$DIR" ] || { echo "no release at $DIR" >&2; exit 1; }
PREVIOUS="$(readlink "$ROOT/current" 2>/dev/null || true)"

log "rendering configuration from SSM"
bash "$DIR/scripts/render-env.sh" "$ENV_FILE"
set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a

if [ "${TLS_MODE:-caddy}" = "alb" ]; then SITE_ADDRESS=":80"; else SITE_ADDRESS="${DOMAIN:?}"; fi
{
  echo "IMAGE_REPO='$IMAGE_REPO'"
  echo "IMAGE_TAG='$RELEASE'"
  echo "SITE_ADDRESS='$SITE_ADDRESS'"
  echo "DATA_DIR='/data'"
} >> "$ENV_FILE"

if [ -n "${GHCR_TOKEN:-}" ]; then
  log "logging in to ghcr.io"
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "${GHCR_USER:?GHCR_USER}" --password-stdin >/dev/null
fi

log "pulling images for $RELEASE"
compose "$DIR" pull --quiet

log "starting (migrations run first; waiting for health checks)"
if ! compose "$DIR" up -d --remove-orphans --wait --wait-timeout 240; then
  log "NEW RELEASE UNHEALTHY. Recent logs:"
  compose "$DIR" logs --tail 60 migrate api worker || true
  if [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
    OLD_TAG="$(basename "$PREVIOUS")"
    log "rolling back to $OLD_TAG"
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG='$OLD_TAG'/" "$ENV_FILE"
    compose "$PREVIOUS" up -d --remove-orphans --wait --wait-timeout 240 || true
  fi
  exit 1
fi

ln -sfn "$DIR" "$ROOT/current"

log "installing timers (backup, duckdns)"
install -m 644 "$DIR"/systemd/*.service "$DIR"/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now lung-backup.timer lung-duckdns.timer >/dev/null

log "tidying: keep the 5 newest releases, drop unused images"
find "$ROOT/releases" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
  | sort -rn | tail -n +6 | cut -d' ' -f2- | xargs -r rm -rf
docker image prune -af --filter "until=168h" >/dev/null || true

log "done: $RELEASE is live"
compose "$DIR" ps --format 'table {{.Service}}\t{{.Status}}'
