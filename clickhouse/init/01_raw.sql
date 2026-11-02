CREATE DATABASE IF NOT EXISTS raw;

-- Every raw table is partitioned by load_date so that reloading a day is an atomic
-- DROP PARTITION + INSERT, which makes the daily ETL idempotent.

CREATE TABLE IF NOT EXISTS raw.users
(
    user_id       UInt64,
    registered_at DateTime,
    region        LowCardinality(String),
    platform      LowCardinality(String),
    load_date     Date,
    _loaded_at    DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY load_date
ORDER BY user_id;

CREATE TABLE IF NOT EXISTS raw.listings
(
    listing_id UInt64,
    seller_id  UInt64,
    category   LowCardinality(String),
    region     LowCardinality(String),
    price      UInt64,
    created_at DateTime,
    load_date  Date,
    _loaded_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY load_date
ORDER BY listing_id;

CREATE TABLE IF NOT EXISTS raw.listing_closures
(
    listing_id UInt64,
    closed_at  DateTime,
    reason     LowCardinality(String),
    load_date  Date,
    _loaded_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY load_date
ORDER BY listing_id;

-- Clickstream is delivered at-least-once, so duplicates by event_id are expected here
-- and removed in the staging layer.
CREATE TABLE IF NOT EXISTS raw.events
(
    event_id   UInt64,
    event_ts   DateTime64(3),
    event_type LowCardinality(String),
    user_id    UInt64,
    listing_id UInt64,
    platform   LowCardinality(String),
    load_date  Date,
    _loaded_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY load_date
ORDER BY (event_type, user_id, event_ts);

CREATE TABLE IF NOT EXISTS raw.promotions
(
    payment_id UInt64,
    listing_id UInt64,
    seller_id  UInt64,
    service    LowCardinality(String),
    amount     Decimal(12, 2),
    paid_at    DateTime,
    load_date  Date,
    _loaded_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY load_date
ORDER BY payment_id;

CREATE TABLE IF NOT EXISTS raw.load_log
(
    load_date   Date,
    table_name  LowCardinality(String),
    rows        UInt64,
    duration_ms UInt32,
    loaded_at   DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (load_date, table_name);
