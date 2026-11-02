FROM apache/superset:6.0.0

USER root
RUN uv pip install --python /app/.venv/bin/python --no-cache clickhouse-connect psycopg2-binary
COPY superset_config.py /app/pythonpath/superset_config.py
COPY --chmod=755 init-and-run.sh /app/docker/init-and-run.sh
USER superset
