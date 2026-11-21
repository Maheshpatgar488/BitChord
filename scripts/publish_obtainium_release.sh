#!/usr/bin/env bash
# Creates/updates a GitHub release whenever the version code changes.
# Runs inside GitHub Actions after :app:assembleProdRelease.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

read_version() {
  grep -F "extra[\"$1\"]" build.gradle.kts | head -n 1 | sed -E 's/^[^=]*= *"?([^"]*)"?.*$/\1/'
}

VERSION_CODE="$(read_version bitchordVersionCode)"
VERSION_NAME="$(read_version bitchordVersionName)"
if [[ -z "$VERSION_CODE" || -z "$VERSION_NAME" ]]; then
  echo "publish: could not read version; skipping"
  exit 0
fi

# Include versionCode in the tag so a code-only bump also produces a new release.
TAG="v${VERSION_NAME}.${VERSION_CODE}"
APK_DIR="app/build/outputs/apk/prod/release"
mapfile -t APKS < <(find "$APK_DIR" -maxdepth 1 -type f -name '*.apk' | sort)
if [[ ${#APKS[@]} -eq 0 ]]; then
  echo "publish: no phone APKs found; skipping"
  exit 0
fi

# GitHub Actions checkout stores the workflow GITHUB_TOKEN in .git/config.
TOKEN=""
HEADER="$(git config --get http.https://github.com/.extraheader || true)"
if [[ -n "$HEADER" ]]; then
  TOKEN="$(printf '%s' "$HEADER" | sed -n 's/.*AUTHORIZATION: basic //p' | base64 -d | sed -n 's/^x-access-token://p')"
fi
TOKEN="${TOKEN:-${GITHUB_TOKEN:-${GH_TOKEN:-}}}"
if [[ -z "$TOKEN" ]]; then
  echo "publish: no GitHub token available; skipping"
  exit 0
fi

API="https://api.github.com/repos/Maheshpatgar488/BitChord"
AUTH="Authorization: Bearer ${TOKEN}"
TMP_JSON="${TMPDIR:-/data/user/0/ai.antigem/files/usr/tmp}/bitchord-obtainium-release.json"

status="$(curl -s -o "$TMP_JSON" -w '%{http_code}' -H "$AUTH" -H 'Accept: application/vnd.github+json' "$API/releases/tags/$TAG")"
if [[ "$status" == "404" ]]; then
  payload="$(printf '{"tag_name":"%s","name":"BitChord %s (OriginOS)","body":"Automatic phone-only release. Version %s, code %s.","draft":false,"prerelease":false}' \
    "$TAG" "$VERSION_NAME" "$VERSION_NAME" "$VERSION_CODE")"
  status="$(curl -s -o "$TMP_JSON" -w '%{http_code}' -X POST -H "$AUTH" -H 'Accept: application/vnd.github+json' -d "$payload" "$API/releases")"
  if [[ "$status" != "201" ]]; then
    echo "publish: release create failed ($status)"
    cat "$TMP_JSON"
    exit 1
  fi
elif [[ "$status" != "200" ]]; then
  echo "publish: release lookup failed ($status)"
  cat "$TMP_JSON"
  exit 1
fi

UPLOAD_URL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["upload_url"].split("{")[0])' "$TMP_JSON")"
EXISTING="$(python3 -c 'import json,sys; print("\n".join(a["name"] for a in json.load(open(sys.argv[1])).get("assets", [])))' "$TMP_JSON")"

for apk in "${APKS[@]}"; do
  name="$(basename "$apk")"
  if printf '%s\n' "$EXISTING" | grep -Fxq "$name"; then
    echo "publish: $name already uploaded"
    continue
  fi
  echo "publish: uploading $name"
  status="$(curl -s -o "$TMP_JSON" -w '%{http_code}' -X POST -H "$AUTH" -H 'Accept: application/vnd.github+json' \
    -H 'Content-Type: application/vnd.android.package-archive' --data-binary "@$apk" "$UPLOAD_URL?name=$name")"
  if [[ "$status" != "201" ]]; then
    echo "publish: upload failed for $name ($status)"
    cat "$TMP_JSON"
    exit 1
  fi
done

echo "publish: release $TAG is ready for Obtainium"
