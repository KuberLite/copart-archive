#!/bin/sh
# Runs the archive in Docker: ./run.sh photos /input/SalesData.csv --limit 10
# DETACH=1 ./run.sh ... starts it in the background: this server drops idle ssh
# sessions, which kills an attached long run. Logs stay until the next run.
set -eu
BASE=${BASE:-/opt/copart-archive}
# per-host settings, e.g. MEMORY=700m on a small machine
[ -f "$BASE/host.conf" ] && . "$BASE/host.conf"
IMAGE=${IMAGE:-copart-archive:0.1}
NAME=${NAME:-copart-archive-run}
MEMORY=${MEMORY:-1g}

set -- "$IMAGE" "$@"
if [ "${DETACH:-0}" = "1" ]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  set -- -d --name "$NAME" "$@"  # no --rm, so the log survives the run
  echo "запущен в фоне; логи: docker logs -f $NAME"
else
  set -- --rm "$@"
fi

exec docker run --memory="$MEMORY" \
  -v "$BASE/archive:/archive" \
  -v "$BASE/input:/input:ro" \
  "$@"
