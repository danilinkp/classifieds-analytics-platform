from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import config as cfg

REGION_NAMES = np.array(list(cfg.REGIONS))
REGION_P = np.array(list(cfg.REGIONS.values())) / sum(cfg.REGIONS.values())
PLATFORM_NAMES = np.array(list(cfg.PLATFORMS))
PLATFORM_P = np.array(list(cfg.PLATFORMS.values())) / sum(cfg.PLATFORMS.values())
PLATFORM_CONTACT = np.array([cfg.PLATFORM_CONTACT_FACTOR[p] for p in PLATFORM_NAMES])

CATEGORY_NAMES = np.array([c.name for c in cfg.CATEGORIES])
CATEGORY_SHARE = np.array([c.listing_share for c in cfg.CATEGORIES])
CATEGORY_SHARE = CATEGORY_SHARE / CATEGORY_SHARE.sum()
CATEGORY_VIEW_WEIGHT = np.array([c.view_weight for c in cfg.CATEGORIES])
CATEGORY_CONTACT = np.array([c.contact_rate for c in cfg.CATEGORIES])
CATEGORY_PROMO_PRICE = np.array([c.promo_price_factor for c in cfg.CATEGORIES])

PROMO_NAMES = np.array([s.name for s in cfg.PROMO_SERVICES])
PROMO_PRICE = np.array([s.price for s in cfg.PROMO_SERVICES])
PROMO_BOOST = np.array([s.view_boost for s in cfg.PROMO_SERVICES])
PROMO_P = np.array([s.choice_prob for s in cfg.PROMO_SERVICES])
PROMO_P = PROMO_P / PROMO_P.sum()

HOUR_P = np.array(cfg.HOURLY_PROFILE) / sum(cfg.HOURLY_PROFILE)
MS_PER_DAY = 86_400_000


@dataclass
class State:
    """Everything that exists before the simulated day: the generator is stateless
    between runs and restores this from the warehouse, like a real source would."""

    user_ids: np.ndarray
    user_region: np.ndarray
    user_platform: np.ndarray
    listing_ids: np.ndarray
    listing_seller: np.ndarray
    listing_category: np.ndarray
    listing_region: np.ndarray
    listing_price: np.ndarray
    listing_created: np.ndarray
    promo_listing_ids: np.ndarray
    promo_boost: np.ndarray
    next_user_id: int
    next_listing_id: int
    next_payment_id: int


@dataclass
class DayBatch:
    users: pd.DataFrame
    listings: pd.DataFrame
    listing_closures: pd.DataFrame
    events: pd.DataFrame
    promotions: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        return {
            "users": self.users,
            "listings": self.listings,
            "listing_closures": self.listing_closures,
            "events": self.events,
            "promotions": self.promotions,
        }


def rng_for(day: date) -> np.random.Generator:
    return np.random.default_rng(day.toordinal())


def _day_start_ms(day: date) -> np.datetime64:
    return np.datetime64(day, "ms")


def _random_offsets_ms(n: int, rng: np.random.Generator) -> np.ndarray:
    hours = rng.choice(24, n, p=HOUR_P)
    return hours * 3_600_000 + rng.integers(0, 3_600_000, n)


def _day_factor(day: date, rng: np.random.Generator) -> float:
    days_since_start = (day - cfg.SIMULATION_START).days
    return (
        cfg.WEEKDAY_FACTOR[day.weekday()]
        * (1 + cfg.DAILY_GROWTH * days_since_start)
        * rng.lognormal(0, cfg.DAILY_NOISE_SIGMA)
    )


def _prices(categories: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    medians = np.array([c.price_median for c in cfg.CATEGORIES])[categories]
    sigmas = np.array([c.price_sigma for c in cfg.CATEGORIES])[categories]
    raw = rng.lognormal(np.log(medians), sigmas)
    step = np.where(raw > 100_000, 1_000, np.where(raw > 5_000, 100, 10))
    return np.maximum(np.round(raw / step) * step, 10).astype(np.uint64)


def _to_seconds(ts_ms: np.ndarray) -> np.ndarray:
    return ts_ms.astype("datetime64[s]")


def bootstrap(day: date) -> DayBatch:
    """Marketplace that already existed before the simulation window starts."""
    rng = rng_for(day)
    end_of_day = _day_start_ms(day) + np.timedelta64(MS_PER_DAY - 1, "ms")

    n_users = cfg.INITIAL_USERS
    user_ids = np.arange(1, n_users + 1, dtype=np.uint64)
    user_region = rng.choice(len(REGION_NAMES), n_users, p=REGION_P)
    registered_at = end_of_day - rng.integers(0, 365 * MS_PER_DAY, n_users).astype("timedelta64[ms]")
    users = pd.DataFrame({
        "user_id": user_ids,
        "registered_at": _to_seconds(registered_at),
        "region": REGION_NAMES[user_region],
        "platform": PLATFORM_NAMES[rng.choice(len(PLATFORM_NAMES), n_users, p=PLATFORM_P)],
    })

    n_listings = cfg.INITIAL_LISTINGS
    seller_idx = rng.integers(0, n_users, n_listings)
    categories = rng.choice(len(CATEGORY_NAMES), n_listings, p=CATEGORY_SHARE)
    # Approximates the steady-state age mix: each day a share of listings is closed,
    # so the live stock is skewed towards young listings.
    survival = (1 - cfg.DAILY_REMOVAL_PROB - 0.002) ** np.arange(cfg.LISTING_TTL_DAYS)
    age_days = rng.choice(cfg.LISTING_TTL_DAYS, n_listings, p=survival / survival.sum())
    age_ms = age_days * MS_PER_DAY + rng.integers(0, MS_PER_DAY, n_listings)
    listings = pd.DataFrame({
        "listing_id": np.arange(1, n_listings + 1, dtype=np.uint64),
        "seller_id": user_ids[seller_idx],
        "category": CATEGORY_NAMES[categories],
        "region": REGION_NAMES[user_region[seller_idx]],
        "price": _prices(categories, rng),
        "created_at": _to_seconds(end_of_day - age_ms.astype("timedelta64[ms]")),
    })

    return DayBatch(
        users=users,
        listings=listings,
        listing_closures=_empty_closures(),
        events=_empty_events(),
        promotions=_empty_promotions(),
    )


def generate_day(day: date, state: State) -> DayBatch:
    rng = rng_for(day)
    factor = _day_factor(day, rng)
    day_start = _day_start_ms(day)
    day_end = day_start + np.timedelta64(MS_PER_DAY - 1, "ms")

    n_new_users = rng.poisson(cfg.NEW_USERS_PER_DAY * factor)
    new_user_ids = np.arange(state.next_user_id, state.next_user_id + n_new_users, dtype=np.uint64)
    new_user_region = rng.choice(len(REGION_NAMES), n_new_users, p=REGION_P)
    new_user_platform = rng.choice(len(PLATFORM_NAMES), n_new_users, p=PLATFORM_P)
    users = pd.DataFrame({
        "user_id": new_user_ids,
        "registered_at": _to_seconds(day_start + _random_offsets_ms(n_new_users, rng).astype("timedelta64[ms]")),
        "region": REGION_NAMES[new_user_region],
        "platform": PLATFORM_NAMES[new_user_platform],
    })

    all_user_ids = np.concatenate([state.user_ids, new_user_ids])
    all_user_region = np.concatenate([state.user_region, new_user_region])
    all_user_platform = np.concatenate([state.user_platform, new_user_platform])

    n_new_listings = rng.poisson(cfg.NEW_LISTINGS_PER_DAY * factor)
    seller_idx = rng.integers(0, len(all_user_ids), n_new_listings)
    new_categories = rng.choice(len(CATEGORY_NAMES), n_new_listings, p=CATEGORY_SHARE)
    new_listing_ids = np.arange(state.next_listing_id, state.next_listing_id + n_new_listings, dtype=np.uint64)
    new_listing_region = all_user_region[seller_idx]
    new_listing_price = _prices(new_categories, rng)
    new_listing_created = day_start + _random_offsets_ms(n_new_listings, rng).astype("timedelta64[ms]")
    listings = pd.DataFrame({
        "listing_id": new_listing_ids,
        "seller_id": all_user_ids[seller_idx],
        "category": CATEGORY_NAMES[new_categories],
        "region": REGION_NAMES[new_listing_region],
        "price": new_listing_price,
        "created_at": _to_seconds(new_listing_created),
    })

    pool_ids = np.concatenate([state.listing_ids, new_listing_ids])
    pool_seller = np.concatenate([state.listing_seller, all_user_ids[seller_idx]])
    pool_category = np.concatenate([state.listing_category, new_categories])
    pool_region = np.concatenate([state.listing_region, new_listing_region])
    pool_price = np.concatenate([state.listing_price, new_listing_price])
    pool_created = np.concatenate([state.listing_created, new_listing_created.astype("datetime64[D]")])
    pool_age_days = (np.datetime64(day, "D") - pool_created).astype(np.int64)

    events, contacts_per_listing = _generate_events(
        day=day,
        rng=rng,
        factor=factor,
        day_start=day_start,
        day_end=day_end,
        n_new_users=n_new_users,
        user_ids=all_user_ids,
        user_region=all_user_region,
        user_platform=all_user_platform,
        pool_ids=pool_ids,
        pool_category=pool_category,
        pool_region=pool_region,
        pool_age_days=pool_age_days,
        promo_boost=_promo_boost(pool_ids, state),
    )

    closures, closed_mask = _generate_closures(rng, day_start, pool_ids, pool_age_days, contacts_per_listing)

    promotions = _generate_promotions(
        day=day,
        rng=rng,
        factor=factor,
        day_start=day_start,
        next_payment_id=state.next_payment_id,
        pool_ids=pool_ids[~closed_mask],
        pool_seller=pool_seller[~closed_mask],
        pool_category=pool_category[~closed_mask],
    )

    return DayBatch(
        users=users,
        listings=listings,
        listing_closures=closures,
        events=events,
        promotions=promotions,
    )


def _promo_boost(pool_ids: np.ndarray, state: State) -> np.ndarray:
    boost = np.ones(len(pool_ids))
    if len(state.promo_listing_ids) == 0:
        return boost
    order = np.argsort(state.promo_listing_ids)
    sorted_ids = state.promo_listing_ids[order]
    sorted_boost = state.promo_boost[order]
    pos = np.searchsorted(sorted_ids, pool_ids).clip(0, len(sorted_ids) - 1)
    hit = sorted_ids[pos] == pool_ids
    boost[hit] = sorted_boost[pos[hit]]
    return boost


def _generate_events(
    *,
    day: date,
    rng: np.random.Generator,
    factor: float,
    day_start: np.datetime64,
    day_end: np.datetime64,
    n_new_users: int,
    user_ids: np.ndarray,
    user_region: np.ndarray,
    user_platform: np.ndarray,
    pool_ids: np.ndarray,
    pool_category: np.ndarray,
    pool_region: np.ndarray,
    pool_age_days: np.ndarray,
    promo_boost: np.ndarray,
) -> tuple[pd.DataFrame, np.ndarray]:
    # DAU follows the market trend, not the size of the registered base: most of the
    # base is dormant. Users who registered today are active by definition.
    n_existing = len(user_ids) - n_new_users
    n_returning = min(max(rng.poisson(cfg.BASE_DAU * factor) - n_new_users, 0), n_existing)
    returning_idx = rng.choice(n_existing, n_returning, replace=False)
    active_idx = np.concatenate([returning_idx, np.arange(n_existing, len(user_ids))])
    n_active = len(active_idx)

    dispersion = 1.2
    extra_mean = cfg.MEAN_VIEWS_PER_ACTIVE_USER - 1
    views_per_user = 1 + rng.negative_binomial(dispersion, dispersion / (dispersion + extra_mean), n_active)
    view_user_idx = np.repeat(active_idx, views_per_user)
    n_views = len(view_user_idx)

    # Fresh and promoted listings get more traffic, as on a real feed.
    weights = CATEGORY_VIEW_WEIGHT[pool_category] * promo_boost / (1 + pool_age_days / 14)
    view_region = user_region[view_user_idx]
    same_region = rng.random(n_views) < cfg.SAME_REGION_VIEW_SHARE
    view_listing_idx = np.empty(n_views, dtype=np.int64)
    for region in range(len(REGION_NAMES)):
        mask = same_region & (view_region == region)
        candidates = np.flatnonzero(pool_region == region)
        if mask.sum() == 0 or len(candidates) == 0:
            same_region[mask] = False
            continue
        p = weights[candidates] / weights[candidates].sum()
        view_listing_idx[mask] = candidates[rng.choice(len(candidates), mask.sum(), p=p)]
    other = ~same_region
    view_listing_idx[other] = rng.choice(len(pool_ids), other.sum(), p=weights / weights.sum())

    # A user's views form one session: start time plus small exponential gaps.
    session_start = _random_offsets_ms(n_active, rng)
    gaps = rng.exponential(45_000, n_views).astype(np.int64)
    cumulative = np.cumsum(gaps)
    group_first = np.repeat(np.cumsum(views_per_user) - views_per_user, views_per_user)
    within_session = cumulative - cumulative[group_first] + gaps[group_first]
    view_offset = np.minimum(np.repeat(session_start, views_per_user) + within_session, MS_PER_DAY - 1)
    view_ts = day_start + view_offset.astype("timedelta64[ms]")

    view_platform = user_platform[view_user_idx]
    platform_factor = PLATFORM_CONTACT[view_platform] * np.array(
        [cfg.contact_factor(day, name) for name in PLATFORM_NAMES]
    )[view_platform]
    contact_p = CATEGORY_CONTACT[pool_category[view_listing_idx]] * platform_factor
    is_contact = rng.random(n_views) < contact_p
    is_favorite = rng.random(n_views) < cfg.FAVORITE_RATE

    def follow_up(mask: np.ndarray, mean_delay_ms: float) -> np.ndarray:
        delay = rng.exponential(mean_delay_ms, mask.sum()).astype(np.int64).astype("timedelta64[ms]")
        return np.minimum(view_ts[mask] + delay, day_end)

    parts = [
        ("view", view_ts, np.ones(n_views, dtype=bool)),
        ("contact", follow_up(is_contact, 90_000), is_contact),
        ("favorite", follow_up(is_favorite, 30_000), is_favorite),
    ]
    frames = [
        pd.DataFrame({
            "event_ts": ts,
            "event_type": event_type,
            "user_idx": view_user_idx[mask],
            "listing_idx": view_listing_idx[mask],
        })
        for event_type, ts, mask in parts
    ]
    events = pd.concat(frames, ignore_index=True)

    contacts_per_listing = np.bincount(view_listing_idx[is_contact], minlength=len(pool_ids))

    lost_regions = cfg.lost_event_regions(day)
    if lost_regions:
        lost_codes = [i for i, name in enumerate(REGION_NAMES) if name in lost_regions]
        events = events[~np.isin(user_region[events["user_idx"].to_numpy()], lost_codes)]

    events = events.sort_values("event_ts", kind="stable").reset_index(drop=True)
    events["event_id"] = np.uint64(day.toordinal()) * np.uint64(10_000_000) + np.arange(len(events), dtype=np.uint64)

    duplicates = events.sample(frac=cfg.DUPLICATE_EVENT_RATE, random_state=rng)
    events = pd.concat([events, duplicates], ignore_index=True)

    user_idx = events["user_idx"].to_numpy()
    result = pd.DataFrame({
        "event_id": events["event_id"].to_numpy(),
        "event_ts": events["event_ts"].to_numpy(),
        "event_type": events["event_type"].to_numpy(),
        "user_id": user_ids[user_idx],
        "listing_id": pool_ids[events["listing_idx"].to_numpy()],
        "platform": PLATFORM_NAMES[user_platform[user_idx]],
    })
    return result, contacts_per_listing


def _generate_closures(
    rng: np.random.Generator,
    day_start: np.datetime64,
    pool_ids: np.ndarray,
    pool_age_days: np.ndarray,
    contacts_per_listing: np.ndarray,
) -> tuple[pd.DataFrame, np.ndarray]:
    n = len(pool_ids)
    sold = rng.random(n) < 1 - (1 - cfg.SALE_PROB_PER_CONTACT) ** contacts_per_listing
    expired = pool_age_days >= cfg.LISTING_TTL_DAYS
    removed = rng.random(n) < cfg.DAILY_REMOVAL_PROB

    reason = np.full(n, "", dtype=object)
    reason[removed] = "removed"
    reason[expired] = "expired"
    reason[sold] = "sold"
    closed_mask = reason != ""

    n_closed = int(closed_mask.sum())
    closures = pd.DataFrame({
        "listing_id": pool_ids[closed_mask],
        "closed_at": _to_seconds(day_start + _random_offsets_ms(n_closed, rng).astype("timedelta64[ms]")),
        "reason": reason[closed_mask].astype(str),
    })
    return closures, closed_mask


def _generate_promotions(
    *,
    day: date,
    rng: np.random.Generator,
    factor: float,
    day_start: np.datetime64,
    next_payment_id: int,
    pool_ids: np.ndarray,
    pool_seller: np.ndarray,
    pool_category: np.ndarray,
) -> pd.DataFrame:
    expected = cfg.DAILY_PROMO_SHARE * len(pool_ids) * factor * cfg.promo_volume_factor(day)
    n = min(rng.poisson(expected), len(pool_ids))
    chosen = rng.choice(len(pool_ids), n, replace=False)
    service = rng.choice(len(PROMO_NAMES), n, p=PROMO_P)
    amount = np.round(
        PROMO_PRICE[service] * CATEGORY_PROMO_PRICE[pool_category[chosen]] * cfg.promo_price_factor(day)
    )
    return pd.DataFrame({
        "payment_id": np.arange(next_payment_id, next_payment_id + n, dtype=np.uint64),
        "listing_id": pool_ids[chosen],
        "seller_id": pool_seller[chosen],
        "service": PROMO_NAMES[service],
        "amount": amount,
        "paid_at": _to_seconds(day_start + _random_offsets_ms(n, rng).astype("timedelta64[ms]")),
    })


def _empty_closures() -> pd.DataFrame:
    return pd.DataFrame({"listing_id": [], "closed_at": [], "reason": []})


def _empty_events() -> pd.DataFrame:
    return pd.DataFrame({c: [] for c in ["event_id", "event_ts", "event_type", "user_id", "listing_id", "platform"]})


def _empty_promotions() -> pd.DataFrame:
    return pd.DataFrame({c: [] for c in ["payment_id", "listing_id", "seller_id", "service", "amount", "paid_at"]})


def previous_day(day: date) -> date:
    return day - timedelta(days=1)
