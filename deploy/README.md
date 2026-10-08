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
```

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
