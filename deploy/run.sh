#!/bin/sh
# Runs the archive in Docker: ./run.sh photos /input/SalesData.csv --limit 10
# INPUT holds the files from the client, ARCHIVE holds cases/ and photos/.
set -eu
BASE=${BASE:-/opt/copart-archive}
IMAGE=${IMAGE:-copart-archive:0.1}
exec docker run --rm \
  -v "$BASE/archive:/archive" \
  -v "$BASE/input:/input:ro" \
  "$IMAGE" "$@"
