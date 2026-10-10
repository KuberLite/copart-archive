#!/bin/sh
# Copies the code to a host, builds the image there and runs the tests in a
# clean container. Fails if the tests fail; restarts the bot if it is running.
#   deploy/push.sh root@HOST
set -eu
HOST=${1:?укажите хост: deploy/push.sh root@HOST}
BASE=${BASE:-/opt/copart-archive}
cd "$(dirname "$0")/.."

# client files live in the repo root (anchored "/" patterns), test fixtures
# under tests/ — those must go, the root ones must not
rsync -a --delete \
  --exclude '/.venv' --exclude '/.git' --exclude '/archive' --exclude '/tmp' \
  --exclude '__pycache__' --exclude '*.egg-info' --exclude '.pytest_cache' \
  --exclude '/*.xlsx' --exclude '/*.csv' \
  ./ "$HOST:$BASE/app/"
scp -q deploy/run.sh deploy/bot.sh "$HOST:$BASE/"

ssh -o ServerAliveInterval=15 "$HOST" BASE="$BASE" sh -s <<'REMOTE'
set -eu
chmod +x "$BASE"/*.sh
cd "$BASE/app"
docker build -q -t copart-archive:0.1 . >/dev/null
echo "образ собран"
docker run --rm -v "$BASE/app:/src:ro" python:3.12-slim sh -c '
  cp -r /src /app && pip install -q "/app[dev,bot]" >/dev/null 2>&1
  cd /app && python -m pytest -q -p no:cacheprovider >/tmp/tests.log 2>&1; rc=$?
  tail -1 /tmp/tests.log; exit $rc'
if docker ps -a --format '{{.Names}}' | grep -qx copart-bot; then
  "$BASE/bot.sh"
fi
REMOTE
