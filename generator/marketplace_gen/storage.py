import os
import time
from datetime import date, timedelta

import clickhouse_connect
import numpy as np
import pandas as pd
from clickhouse_connect.driver.client import Client

from . import config as cfg
from .simulation import (
    CATEGORY_NAMES,
    PLATFORM_NAMES,
    PROMO_BOOST,
    PROMO_NAMES,
    REGION_NAMES,
    DayBatch,
    State,
)

RAW_TABLES = ["users", "listings", "listing_closures", "events", "promotions"]


def connect() -> Client:
    return clickhouse_connect.get_client(
        host=os.environ.get("CLICKHOUSE_HOST", "localhost"),
        port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
        username=os.environ.get("CLICKHOUSE_USER", "default"),
        password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
        database="raw",
    )


def last_loaded_date(client: Client) -> date | None:
    value = client.command("SELECT max(load_date) FROM raw.users")
    if not value or str(value) == "1970-01-01":
        return None
    return date.fromisoformat(str(value))


def _codes(values: pd.Series, names: np.ndarray) -> np.ndarray:
    lookup = {name: i for i, name in enumerate(names)}
    return values.map(lookup).to_numpy(dtype=np.int64)


def _active_promo_boosts(promos: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    if promos.empty:
        return np.array([], dtype=np.uint64), np.array([])
    boost = pd.Series(PROMO_BOOST[_codes(promos["service"], PROMO_NAMES)])
    # A listing can have several overlapping promotions; the strongest one wins.
    strongest = boost.groupby(promos["listing_id"].to_numpy()).max()
    return strongest.index.to_numpy(dtype=np.uint64), strongest.to_numpy()


def load_state(client: Client, day: date) -> State:
    params = {"day": day}

    users = client.query_df(
        "SELECT user_id, region, platform FROM raw.users WHERE load_date < {day:Date} ORDER BY user_id",
        parameters=params,
    )
    listings = client.query_df(
        """
        SELECT listing_id, seller_id, category, region, price, toDate(created_at) AS created_date
        FROM raw.listings
        WHERE load_date < {day:Date}
          AND listing_id NOT IN (SELECT listing_id FROM raw.listing_closures WHERE load_date < {day:Date})
        ORDER BY listing_id
        """,
        parameters=params,
    )
    promos = client.query_df(
        """
        SELECT listing_id, service
        FROM raw.promotions
        WHERE load_date >= {day:Date} - {duration:UInt16} AND load_date < {day:Date}
        """,
        parameters={**params, "duration": cfg.PROMO_DURATION_DAYS},
    )
    promo_ids, promo_boost = _active_promo_boosts(promos)

    max_ids = client.query_df(
        """
        SELECT
            (SELECT max(user_id) FROM raw.users WHERE load_date < {day:Date}) AS max_user,
            (SELECT max(listing_id) FROM raw.listings WHERE load_date < {day:Date}) AS max_listing,
            (SELECT max(payment_id) FROM raw.promotions WHERE load_date < {day:Date}) AS max_payment
        """,
        parameters=params,
    ).iloc[0]

    return State(
        user_ids=users["user_id"].to_numpy(dtype=np.uint64),
        user_region=_codes(users["region"], REGION_NAMES),
        user_platform=_codes(users["platform"], PLATFORM_NAMES),
        listing_ids=listings["listing_id"].to_numpy(dtype=np.uint64),
        listing_seller=listings["seller_id"].to_numpy(dtype=np.uint64),
        listing_category=_codes(listings["category"], CATEGORY_NAMES),
        listing_region=_codes(listings["region"], REGION_NAMES),
        listing_price=listings["price"].to_numpy(dtype=np.uint64),
        listing_created=pd.to_datetime(listings["created_date"]).to_numpy().astype("datetime64[D]"),
        promo_listing_ids=promo_ids,
        promo_boost=promo_boost,
        next_user_id=int(max_ids["max_user"]) + 1,
        next_listing_id=int(max_ids["max_listing"]) + 1,
        next_payment_id=int(max_ids["max_payment"]) + 1,
    )


def write_batch(client: Client, day: date, batch: DayBatch) -> dict[str, int]:
    partition_id = day.strftime("%Y%m%d")
    loaded: dict[str, int] = {}
    for table, frame in batch.tables().items():
        started = time.monotonic()
        client.command(f"ALTER TABLE raw.{table} DROP PARTITION ID '{partition_id}'")
        if len(frame):
            client.insert_df(f"raw.{table}", frame.assign(load_date=day))
        duration_ms = int((time.monotonic() - started) * 1000)
        loaded[table] = len(frame)
        client.insert(
            "raw.load_log",
            [[day, table, len(frame), duration_ms]],
            column_names=["load_date", "table_name", "rows", "duration_ms"],
        )
    return loaded


def require_previous_day_loaded(client: Client, day: date) -> None:
    last = last_loaded_date(client)
    previous = day - timedelta(days=1)
    if last is None:
        raise RuntimeError("raw layer is empty: run bootstrap first")
    if last < previous:
        raise RuntimeError(f"gap in raw data: last loaded day is {last}, cannot generate {day}")
