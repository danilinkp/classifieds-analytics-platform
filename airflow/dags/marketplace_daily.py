"""Daily ETL of the classifieds marketplace.

extract_load -> dbt staging -> dbt marts -> dbt monitoring -> report_alerts

A run scheduled at midnight processes the day that has just ended. Every step is
idempotent (raw partitions are replaced, dbt incrementals overwrite partitions), so
any run can be cleared and re-run safely.
"""

import logging
import os
from datetime import date, datetime, timedelta

import requests
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

log = logging.getLogger(__name__)

DBT = "dbt {command} --project-dir $DBT_PROJECT_DIR --profiles-dir $DBT_PROFILES_DIR --select {select}"
TARGET_DAY = "{{ macros.ds_add(ds, -1) }}"


def _send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.info("Telegram is not configured, alert summary is only logged")
        return
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )
    response.raise_for_status()


def _main_drivers(client, target_day: str) -> list[str]:
    """For every alert on a total metric, name the segment that explains most of it."""
    rows = client.query(
        """
        SELECT metric_title, slice_type, slice_value, impact_share
        FROM monitoring.alert_drivers
        WHERE date = {day:Date} AND impact_rank = 1 AND impact_share >= 0.5
        ORDER BY metric_title, impact_share DESC
        LIMIT 1 BY metric_title
        """,
        parameters={"day": target_day},
    ).result_rows
    return [
        f"Главный вклад в «{title}»: {slice_type} = {value} ({share:.0%} отклонения)"
        for title, slice_type, value, share in rows
    ]


@dag(
    dag_id="marketplace_daily",
    schedule="@daily",
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["marketplace", "etl", "dbt"],
    doc_md=__doc__,
)
def marketplace_daily():
    @task
    def extract_load(target_day: str) -> dict[str, int]:
        from marketplace_gen.__main__ import run_day

        return run_day(date.fromisoformat(target_day))

    dbt_staging = BashOperator(
        task_id="dbt_staging",
        bash_command=DBT.format(command="build", select="staging"),
    )
    dbt_marts = BashOperator(
        task_id="dbt_marts",
        bash_command=DBT.format(command="build", select="marts"),
    )
    dbt_monitoring = BashOperator(
        task_id="dbt_monitoring",
        bash_command=DBT.format(command="build", select="monitoring metric_catalog"),
    )

    @task
    def report_alerts(target_day: str) -> int:
        from marketplace_gen.storage import connect

        client = connect()
        rows = client.query(
            """
            SELECT severity, alert_kind, message
            FROM monitoring.metric_alerts
            WHERE date = {day:Date}
            ORDER BY severity = 'critical' DESC, slice_type = 'total' DESC, abs(z_score) DESC
            """,
            parameters={"day": target_day},
        ).result_rows

        if not rows:
            log.info("%s: all metrics are within the expected corridor", target_day)
            return 0

        lines = [f"[{severity}{', данные' if kind == 'data_quality' else ''}] {message}" for severity, kind, message in rows]
        lines = _main_drivers(client, target_day) + lines
        for line in lines:
            log.warning(line)
        _send_telegram(f"Отклонения метрик за {target_day}: {len(rows)}\n" + "\n".join(lines[:15]))
        return len(rows)

    loaded = extract_load(TARGET_DAY)
    loaded >> dbt_staging >> dbt_marts >> dbt_monitoring >> report_alerts(TARGET_DAY)


marketplace_daily()
