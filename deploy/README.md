# Test deployment

The server runs everything in Docker, so the archive does too — no system Python
is touched (Ubuntu 22.04 ships 3.10, the project needs 3.12).

```sh
# copy the code
rsync -a --delete --exclude .venv --exclude .git --exclude archive \
  ./ root@HOST:/opt/copart-archive/app/

# build and run
ssh root@HOST 'cd /opt/copart-archive/app && docker build -t copart-archive:0.1 .'
ssh root@HOST '/opt/copart-archive/run.sh photos /input/SalesData.csv --dry-run'

# a long run: detach it, the server drops idle ssh sessions
ssh root@HOST 'DETACH=1 /opt/copart-archive/run.sh photos /input/SalesData.csv --limit 300'
ssh root@HOST 'docker logs -f copart-archive-run'
```

## The bot

```sh
# token from @BotFather and the Telegram IDs allowed in — root-only file
ssh root@HOST 'umask 077; cat > /opt/copart-archive/bot.env' <<'ENV'
BOT_TOKEN=123456:ABC...
BOT_ALLOWED_IDS=111111111 222222222
ENV
ssh root@HOST /opt/copart-archive/bot.sh
ssh root@HOST 'docker logs -f copart-bot'
```

An empty `BOT_ALLOWED_IDS` lets nobody in, and the bot answers everyone with
their ID — that is the way to learn a new ID. The bot restarts on its own
(`--restart unless-stopped`); a download cut by a restart shows as "прервана",
and sending the same file again finishes it.

Клиентский доступ к архиву — [sftp.md](sftp.md).

Keep `ssh -o ServerAliveInterval=15` when watching a run: this host closes
sessions that go quiet for a minute or two.

Layout on the server:

```
/opt/copart-archive/
  app/      the code
  input/    files from the client (mounted read-only)
  archive/  cases/ and photos/ — the archive itself
  run.sh
```

The tests can be run against the deployed copy:

```sh
docker run --rm -v /opt/copart-archive/app:/src:ro python:3.12-slim \
  sh -c 'cp -r /src /app && pip install -q "/app[dev]" && cd /app && python -m pytest -q'
```
