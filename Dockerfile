FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_DB=/data/app.db PORT=3000
WORKDIR /app
RUN groupadd --gid 10001 roomly && useradd --uid 10001 --gid roomly --no-create-home roomly && mkdir /data && chown roomly:roomly /data
COPY --chown=roomly:roomly server.py ./
COPY --chown=roomly:roomly public ./public
COPY --chown=roomly:roomly deploy/backup_worker.py ./deploy/backup_worker.py
USER roomly
VOLUME /data
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/healthz',timeout=3)"
CMD ["python", "server.py"]
