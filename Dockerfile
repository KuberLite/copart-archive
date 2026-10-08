FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY config ./config
ENV COPART_ARCHIVE_CONFIG=/app/config/archive.toml \
    COPART_ARCHIVE_ROOT=/archive \
    PYTHONUNBUFFERED=1

# the archive itself lives outside the image
VOLUME ["/archive"]
ENTRYPOINT ["copart-archive"]
CMD ["--help"]
