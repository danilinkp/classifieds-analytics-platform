"""Dashboards as code: (re)creates the ClickHouse connection, datasets with a semantic
layer of metrics, charts and dashboards through the Superset REST API."""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from charts import (  # noqa: E402
    Chart,
    Layout,
    Markdown,
    SelectFilter,
    big_number,
    category_bar,
    donut,
    heatmap,
    raw_table,
    select_filter,
    sql_filter,
    sql_metric,
    time_filter,
    timeseries,
)
from client import Superset  # noqa: E402

log = logging.getLogger("bootstrap")

COLUMN_TITLES = {
    "date": "Дата",
    "platform": "Платформа",
    "category": "Категория",
    "user_region": "Регион пользователя",
    "region": "Регион",
    "service": "Услуга",
    "severity": "Важность",
    "alert_kind": "Тип",
    "message": "Описание",
    "metric_title": "Метрика",
    "slice_type": "Разрез",
    "slice_value": "Сегмент",
    "deviation_pct": "Отклонение",
    "impact_share": "Доля вклада",
    "created_date": "Дата публикации",
    "status": "Статус",
    "paid_date": "Дата оплаты",
}

DATASETS = {
    "kpi": {
        "schema": "marts",
        "table_name": "agg_daily_kpi",
        "temporal": ["date"],
        "description": "Ключевые метрики маркетплейса по дням",
        "metrics": {
            "dau": ("avg(dau)", "DAU", ",d"),
            "views": ("sum(views)", "Просмотры", ",d"),
            "contacts": ("sum(contacts)", "Контакты", ",d"),
            "cr": ("sum(contacts) / sum(views)", "Конверсия просмотр → контакт", ".2%"),
            "promo_revenue": ("sum(promo_revenue)", "Выручка продвижения, ₽", ",.0f"),
            "arppu": ("sum(promo_revenue) / sum(paying_sellers)", "ARPPU, ₽", ",.0f"),
            # Stock metric: the value at the end of the period, not a sum over days.
            "active_listings": ("argMax(active_listings, date)", "Активные объявления", ",d"),
            "new_listings": ("sum(new_listings)", "Новые объявления", ",d"),
            "closed_listings": ("sum(closed_listings)", "Снятые объявления", ",d"),
            "sold_listings": ("sum(sold_listings)", "Проданные объявления", ",d"),
            "new_users": ("sum(new_users)", "Новые пользователи", ",d"),
        },
    },
    "slice": {
        "schema": "marts",
        "table_name": "agg_daily_slice",
        "temporal": ["date"],
        "description": "Аддитивные метрики в разрезе платформы, категории и региона",
        "metrics": {
            "views": ("sum(views)", "Просмотры", ",d"),
            "contacts": ("sum(contacts)", "Контакты", ",d"),
            "favorites": ("sum(favorites)", "Добавления в избранное", ",d"),
            "cr": ("sum(contacts) / sum(views)", "Конверсия просмотр → контакт", ".2%"),
        },
    },
    "liquidity": {
        "schema": "marts",
        "table_name": "listing_liquidity",
        "temporal": ["created_date"],
        "description": "Ликвидность объявлений по когортам публикации",
        "metrics": {
            "liquidity_7d": (
                "sumIf(contacted_7d, is_complete) / sumIf(listings, is_complete)",
                "Ликвидность 7 дней",
                ".1%",
            ),
            "listings": ("sum(listings)", "Объявления", ",d"),
            "hours_to_contact": (
                "sumIf(median_hours_to_first_contact * listings, is_complete and not isNaN(median_hours_to_first_contact))"
                " / sumIf(listings, is_complete and not isNaN(median_hours_to_first_contact))",
                "Время до первого контакта, ч",
                ",.1f",
            ),
        },
    },
    "listings": {
        "schema": "marts",
        "table_name": "dim_listings",
        "temporal": ["created_date"],
        "description": "Объявления с текущим статусом",
        "metrics": {
            "listings": ("count()", "Объявления", ",d"),
            "sold_share": ("countIf(status = 'sold') / count()", "Доля проданных", ".1%"),
            "avg_lifetime": ("avg(lifetime_days)", "Средний срок жизни, дней", ",.1f"),
        },
    },
    "promotions": {
        "schema": "marts",
        "table_name": "fct_promotions",
        "temporal": ["paid_date"],
        "description": "Оплаты платного продвижения",
        "metrics": {
            "revenue": ("sum(amount)", "Выручка, ₽", ",.0f"),
            "purchases": ("count()", "Покупки", ",d"),
            "avg_check": ("avg(amount)", "Средний чек, ₽", ",.0f"),
        },
    },
    "corridor": {
        "schema": "monitoring",
        "table_name": "metric_corridor",
        "temporal": ["date"],
        "description": "Факт метрики и коридор ожидаемых значений. Доли переведены в проценты.",
        "sql": """
            select
                date,
                metric,
                metric_title,
                slice_type,
                slice_value,
                status,
                value * if(is_ratio, 100, 1) as value,
                expected * if(is_ratio, 100, 1) as expected,
                lower_bound * if(is_ratio, 100, 1) as lower_bound,
                upper_bound * if(is_ratio, 100, 1) as upper_bound
            from monitoring.metric_monitoring
        """,
        "metrics": {
            "fact": ("max(value)", "Факт", ",.2~f"),
            "expected": ("max(expected)", "Ожидание", ",.2~f"),
            "lower": ("max(lower_bound)", "Нижняя граница", ",.2~f"),
            "upper": ("max(upper_bound)", "Верхняя граница", ",.2~f"),
        },
    },
    "alerts": {
        "schema": "monitoring",
        "table_name": "metric_alerts",
        "temporal": ["date"],
        "description": "Отклонения метрик за пределы коридора",
        "metrics": {"alerts": ("count()", "Алерты", ",d")},
    },
    "drivers": {
        "schema": "monitoring",
        "table_name": "alert_drivers",
        "temporal": ["date"],
        "description": "Вклад сегментов в отклонение общей метрики",
        "metrics": {"segments": ("count()", "Сегменты", ",d")},
    },
}

KPI = Layout(
    title="Маркетплейс: ключевые метрики",
    rows=[
        [Markdown(
            "### Ключевые метрики маркетплейса объявлений\n"
            "Большие числа показывают значение за последний день и изменение к тому же дню неделей ранее. "
            "Фильтры платформы, категории и региона применяются к графикам по клик-стриму.",
            height=12,
        )],
        [
            Chart("kpi_dau", "DAU", "kpi", big_number("dau", "date", ",d"), 2, 40),
            Chart("kpi_views", "Просмотры за день", "kpi", big_number("views", "date", "SMART_NUMBER"), 2, 40),
            Chart("kpi_contacts", "Контакты за день", "kpi", big_number("contacts", "date", "SMART_NUMBER"), 2, 40),
            Chart("kpi_cr", "Конверсия в контакт", "kpi", big_number("cr", "date", ".2%"), 2, 40),
            Chart("kpi_revenue", "Выручка продвижения", "kpi", big_number("promo_revenue", "date", "SMART_NUMBER"), 2, 40),
            Chart("kpi_active", "Активные объявления", "kpi", big_number("active_listings", "date", "SMART_NUMBER"), 2, 40),
        ],
        [
            Chart("kpi_activity", "Активность пользователей", "kpi", timeseries(["dau", "new_users"], "date", number_format=",d"), 6),
            Chart("kpi_cr_platform", "Конверсия в контакт по платформам", "slice",
                  timeseries(["cr"], "date", groupby=["platform"], number_format=".2%"), 6),
        ],
        [
            Chart("kpi_contacts_category", "Контакты по категориям", "slice",
                  category_bar("contacts", "category", "SMART_NUMBER"), 6, 60),
            Chart("kpi_cr_heatmap", "Конверсия: категория × платформа", "slice", heatmap("cr", "platform", "category", ".1%"), 6, 60),
        ],
        [
            Chart("kpi_revenue_service", "Выручка продвижения по услугам, по неделям", "promotions",
                  timeseries(["revenue"], "paid_date", groupby=["service"], kind="bar", stacked=True,
                             time_grain="P1W"), 8),
            Chart("kpi_revenue_category", "Структура выручки по категориям", "promotions", donut("revenue", "category"), 4),
        ],
    ],
)

LISTINGS = Layout(
    title="Объявления и ликвидность",
    rows=[
        [Markdown(
            "### Предложение и ликвидность\n"
            "**Ликвидность 7 дней** — доля объявлений, получивших хотя бы один контакт в течение 7 дней после публикации. "
            "Учитываются только завершённые когорты (объявления старше 7 дней).",
            height=12,
        )],
        [
            Chart("lst_liquidity", "Ликвидность 7 дней", "liquidity", big_number("liquidity_7d", "created_date", ".1%"), 3, 40),
            Chart("lst_hours", "Время до первого контакта, ч", "liquidity",
                  big_number("hours_to_contact", "created_date", ",.1f"), 3, 40),
            Chart("lst_new", "Новые объявления за день", "kpi", big_number("new_listings", "date", ",d"), 3, 40),
            Chart("lst_sold", "Продано за день", "kpi", big_number("sold_listings", "date", ",d"), 3, 40),
        ],
        [
            Chart("lst_stock", "Сток активных объявлений", "kpi", timeseries(["active_listings"], "date", number_format=",d"), 6),
            Chart("lst_flow", "Публикации и снятия объявлений", "kpi",
                  timeseries(["new_listings", "closed_listings", "sold_listings"], "date", number_format=",d"), 6),
        ],
        [
            Chart("lst_liquidity_category", "Ликвидность по категориям", "liquidity",
                  category_bar("liquidity_7d", "category", ".1%"), 6, 55),
            Chart("lst_liquidity_cohort", "Ликвидность по когортам публикации", "liquidity",
                  timeseries(["liquidity_7d"], "created_date", number_format=".1%",
                             filters=[sql_filter("is_complete")]), 6, 55),
        ],
        [
            Chart("lst_hours_category", "Время до первого контакта по категориям, ч", "liquidity",
                  category_bar("hours_to_contact", "category", ",.1f"), 6, 55),
            Chart("lst_outcomes", "Исходы объявлений по категориям", "listings",
                  category_bar("listings", "category", ".0%", stack_by="status"), 6, 55),
        ],
    ],
)

CORRIDOR_METRICS = ["fact", "expected", "lower", "upper"]

MONITORING = Layout(
    title="Мониторинг метрик",
    rows=[
        [Markdown(
            "### Мониторинг отклонений метрик\n"
            "**Ожидание** — медиана того же дня недели за 6 предыдущих недель (убирает недельную сезонность). "
            "**Коридор** — ±3 робастных σ относительных остатков за 8 недель. "
            "**critical**: |z| ≥ 5 и отклонение ≥ 15%, **warning**: |z| ≥ 3.5 и отклонение ≥ 5%. "
            "Падение метрики сегмента до нуля помечается как проблема с данными. "
            "Выберите метрику и сегмент в фильтрах слева; доли (конверсия) показаны в процентах.",
            height=16,
        )],
        [Chart("mon_corridor", "Метрика и коридор ожидаемых значений", "corridor",
               timeseries(CORRIDOR_METRICS, "date", number_format=",.2~f"), 12, 65)],
        [Chart("mon_timeline", "Алерты по дням", "alerts",
               timeseries(["alerts"], "date", groupby=["severity"], kind="bar", stacked=True, number_format=",d"), 12, 40)],
        [
            Chart("mon_log", "Журнал алертов", "alerts",
                  raw_table(["date", "severity", "alert_kind", "message"], "date", page_length=20), 7, 80),
            Chart("mon_drivers", "Вклад сегментов в отклонение (топ-3 в каждом разрезе)", "drivers",
                  raw_table(["date", "slice_type", "slice_value", "deviation_pct", "impact_share"], "date",
                            filters=[sql_filter("impact_rank <= 3")],
                            formats={"deviation_pct": ".1%", "impact_share": ".0%"}, page_length=20), 5, 80),
        ],
    ],
)

DASHBOARDS = {
    "marketplace-kpi": (KPI, [
        SelectFilter("platform", "Платформа", "slice", "platform"),
        SelectFilter("category", "Категория", "slice", "category"),
        SelectFilter("region", "Регион пользователя", "slice", "user_region"),
    ]),
    "listings-liquidity": (LISTINGS, [
        SelectFilter("category", "Категория", "liquidity", "category"),
        SelectFilter("region", "Регион", "liquidity", "region"),
    ]),
    "metric-monitoring": (MONITORING, [
        SelectFilter("metric", "Метрика", "corridor", "metric_title", default="Конверсия просмотр → контакт",
                     multi=False, required=True, only_charts=["mon_corridor", "mon_drivers"]),
        SelectFilter("segment", "Сегмент", "corridor", "slice_value", default="Все",
                     multi=False, required=True, only_charts=["mon_corridor"]),
    ]),
}

LABEL_COLORS = {"critical": "#E04355", "warning": "#FCC700", "Факт": "#1F77B4", "Ожидание": "#7F7F7F",
                "Нижняя граница": "#BDBDBD", "Верхняя граница": "#BDBDBD"}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    superset = Superset(os.environ["SUPERSET_URL"], "admin", os.environ["SUPERSET_ADMIN_PASSWORD"])

    uri = (
        f"clickhousedb://{os.environ['CLICKHOUSE_USER']}:{os.environ['CLICKHOUSE_PASSWORD']}"
        f"@{os.environ['CLICKHOUSE_HOST']}:{os.environ['CLICKHOUSE_PORT']}/marts"
    )
    database_id = superset.upsert_database("ClickHouse", uri)
    log.info("database id=%s", database_id)

    datasets = {}
    for key, spec in DATASETS.items():
        spec = {**spec, "columns": COLUMN_TITLES}
        datasets[key] = superset.upsert_dataset(database_id, spec)
        log.info("dataset %s id=%s", key, datasets[key]["id"])

    for slug, (layout, filters) in DASHBOARDS.items():
        dashboard_id = superset.upsert_dashboard(slug, layout.title)
        chart_ids, chart_datasets = {}, {}
        for chart in layout.charts():
            viz_type, params = chart.viz
            chart_ids[chart.key] = superset.upsert_chart(
                chart.title, viz_type, datasets[chart.dataset]["id"], params, dashboard_id
            )
            chart_datasets[chart.key] = chart.dataset

        superset.prune_charts(dashboard_id, set(chart_ids.values()))

        native_filters = [time_filter()]
        for spec in filters:
            # A filter only makes sense for charts whose dataset has the filtered column.
            excluded = [
                chart_ids[key]
                for key, dataset in chart_datasets.items()
                if spec.column not in datasets[dataset]["columns"]
                or (spec.only_charts is not None and key not in spec.only_charts)
            ]
            native_filters.append(select_filter(spec, datasets[spec.dataset]["id"], excluded))

        superset.update_dashboard(dashboard_id, layout.title, layout.position(chart_ids), {
            "native_filter_configuration": native_filters,
            "color_scheme": "supersetColors",
            "label_colors": LABEL_COLORS,
            "cross_filters_enabled": True,
            "refresh_frequency": 0,
            "timed_refresh_immune_slices": [],
            "expanded_slices": {},
        })
        log.info("dashboard %s id=%s with %s charts", slug, dashboard_id, len(chart_ids))


if __name__ == "__main__":
    main()
