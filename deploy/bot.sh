#!/bin/sh
# (Re)starts the Telegram bot. Token and allowed IDs live in $BASE/bot.env,
# readable by root only:
#   BOT_TOKEN=123456:ABC...
#   BOT_ALLOWED_IDS=111111111 222222222
set -eu
BASE=${BASE:-/opt/copart-archive}
IMAGE=${IMAGE:-copart-archive:0.1}

if [ ! -f "$BASE/bot.env" ]; then
  echo "нет $BASE/bot.env — нужны BOT_TOKEN и BOT_ALLOWED_IDS" >&2
  exit 1
fi
chmod 600 "$BASE/bot.env"

docker rm -f copart-bot >/dev/null 2>&1 || true
docker run -d --name copart-bot \
  --restart unless-stopped \
  --memory=1g \
  --log-opt max-size=10m --log-opt max-file=3 \
  --env-file "$BASE/bot.env" \
  -v "$BASE/archive:/archive" \
  --entrypoint copart-archive-bot \
  "$IMAGE" >/dev/null
echo "бот запущен; логи: docker logs -f copart-bot"
