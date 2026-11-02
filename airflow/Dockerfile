FROM apache/airflow:3.3.2-python3.12

ARG AIRFLOW_VERSION=3.3.2
ARG CONSTRAINTS=https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements.txt -c "${CONSTRAINTS}"

# dbt lives in its own venv: its pinned dependencies conflict with Airflow's constraints.
USER root
RUN python -m venv /opt/dbt-venv \
    && /opt/dbt-venv/bin/pip install --no-cache-dir dbt-clickhouse==1.10.3 \
    && ln -s /opt/dbt-venv/bin/dbt /usr/local/bin/dbt
USER airflow
