#!/usr/bin/env bash
# Run on YOUR machine (AWS CLI logged in) to publish a new Android build:
#   deploy/scripts/publish-apk.sh [path/to/app-release.apk] [env]
# Uploads it as lung-score.apk to the public downloads bucket, which https://<domain>/app
# (the QR code) redirects to. Build the APK first (docs/local-development.md, release build).
set -euo pipefail
export MSYS_NO_PATHCONV=1 # Git Bash on Windows

APK="${1:-apps/mobile/android/app/build/outputs/apk/release/app-release.apk}"
ENV_NAME="${2:-demo}"
REGION="${AWS_REGION:-ap-south-1}"

[ -f "$APK" ] || { echo "no APK at $APK" >&2; exit 1; }
URL="$(aws ssm get-parameter --region "$REGION" --name "/lung/$ENV_NAME/APK_URL" \
  --query Parameter.Value --output text)"
# https://<bucket>.s3.<region>.amazonaws.com/lung-score.apk -> <bucket>
BUCKET="${URL#https://}"
BUCKET="${BUCKET%%.s3.*}"

echo "uploading $APK ($(du -h "$APK" | cut -f1)) to s3://$BUCKET/lung-score.apk"
aws s3 cp "$APK" "s3://$BUCKET/lung-score.apk" --region "$REGION" --only-show-errors \
  --content-type application/vnd.android.package-archive \
  --content-disposition 'attachment; filename="lung-score.apk"' \
  --cache-control no-cache
echo "published: $URL"
