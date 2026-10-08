#!/bin/sh
# Runs the archive in Docker: ./run.sh photos /input/SalesData.csv --limit 10
# DETACH=1 ./run.sh ... starts it in the background: the server drops idle ssh
# sessions, which kills an attached long run.
set -eu
BASE=${BASE:-/opt/copart-archive}
IMAGE=${IMAGE:-copart-archive:0.1}
NAME=${NAME:-copart-archive-run}
MEMORY=${MEMORY:-1g}

if [ "${DETACH:-0}" = "1" ]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  set -- -d --name "$NAME" "$@"
  echo "запущен в фоне; логи: docker logs -f $NAME"
fi

exec docker run --rm --memory="$MEMORY" \
  -v "$BASE/archive:/archive" \
  -v "$BASE/input:/input:ro" \
  "$@"
