FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8095 \
    DATA_DIR=/app/data

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home app \
    && mkdir -p /app/data \
    && chown app:app /app/data
COPY config.py server.py index.html ./
COPY assets ./assets

USER app
EXPOSE 8095
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8095')+'/healthz',timeout=3)"
CMD ["python", "-u", "server.py"]
