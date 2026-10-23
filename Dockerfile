FROM python:3.12-slim

LABEL org.opencontainers.image.title="EliteLab" \
      org.opencontainers.image.description="Self-hosted live dashboard for Elite Dangerous" \
      org.opencontainers.image.source="https://github.com/ELITELAB_REPO"

WORKDIR /app
COPY elitelab ./elitelab
COPY web ./web

# Journals are mounted read-only at /journals (see docker-compose.yml).
ENV ELITELAB_HOST=0.0.0.0 \
    ELITELAB_PORT=8766 \
    ELITELAB_JOURNAL_DIR=/journals \
    PYTHONUNBUFFERED=1

EXPOSE 8766
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8766/api/health', timeout=4).status==200 else 1)"

USER nobody
CMD ["python", "-m", "elitelab"]
