from dataclasses import dataclass
from datetime import date

SIMULATION_START = date(2026, 7, 1)

REGIONS: dict[str, float] = {
    "Москва": 0.24,
    "Санкт-Петербург": 0.13,
    "Краснодар": 0.07,
    "Екатеринбург": 0.07,
    "Новосибирск": 0.06,
    "Казань": 0.06,
    "Нижний Новгород": 0.05,
    "Другие регионы": 0.32,
}

PLATFORMS: dict[str, float] = {"android": 0.47, "ios": 0.31, "web": 0.22}

# Relative propensity to contact a seller after viewing a listing.
PLATFORM_CONTACT_FACTOR: dict[str, float] = {"android": 1.0, "ios": 1.08, "web": 0.85}


@dataclass(frozen=True)
class Category:
    name: str
    listing_share: float
    view_weight: float
    contact_rate: float
    price_median: int
    price_sigma: float
    promo_price_factor: float


CATEGORIES: list[Category] = [
    Category("Транспорт", 0.08, 1.6, 0.035, 650_000, 0.8, 2.5),
    Category("Недвижимость", 0.07, 1.8, 0.030, 5_500_000, 0.7, 3.0),
    Category("Электроника", 0.16, 1.2, 0.055, 15_000, 1.0, 1.0),
    Category("Одежда и обувь", 0.17, 0.7, 0.045, 2_000, 0.8, 0.6),
    Category("Дом и сад", 0.13, 0.8, 0.050, 4_500, 1.0, 0.8),
    Category("Работа", 0.05, 1.3, 0.070, 60_000, 0.4, 1.5),
    Category("Услуги", 0.08, 0.9, 0.060, 3_000, 0.9, 1.2),
    Category("Хобби и отдых", 0.10, 0.8, 0.040, 5_000, 1.1, 0.7),
    Category("Животные", 0.05, 1.0, 0.065, 8_000, 1.2, 0.6),
    Category("Детские товары", 0.11, 0.8, 0.050, 2_500, 0.9, 0.6),
]


@dataclass(frozen=True)
class PromoService:
    name: str
    price: int
    view_boost: float
    choice_prob: float


PROMO_SERVICES: list[PromoService] = [
    PromoService("highlight", 99, 1.5, 0.45),
    PromoService("x2_views", 199, 2.0, 0.30),
    PromoService("x5_views", 449, 5.0, 0.18),
    PromoService("vip", 1290, 8.0, 0.07),
]
PROMO_DURATION_DAYS = 7

INITIAL_USERS = 120_000
INITIAL_LISTINGS = 240_000

NEW_USERS_PER_DAY = 1_800
NEW_LISTINGS_PER_DAY = 5_600
BASE_DAU = 17_000
MEAN_VIEWS_PER_ACTIVE_USER = 9.0
SAME_REGION_VIEW_SHARE = 0.75
FAVORITE_RATE = 0.035
DUPLICATE_EVENT_RATE = 0.003

LISTING_TTL_DAYS = 60
DAILY_REMOVAL_PROB = 0.008
SALE_PROB_PER_CONTACT = 0.15
DAILY_PROMO_SHARE = 0.011

# Monday..Sunday: people browse classifieds more on weekends.
WEEKDAY_FACTOR = [0.97, 0.95, 0.95, 0.97, 1.00, 1.10, 1.12]
DAILY_GROWTH = 0.0015
DAILY_NOISE_SIGMA = 0.03

# Share of the day's events falling into each hour (evening peak).
HOURLY_PROFILE = [
    0.012, 0.007, 0.005, 0.004, 0.004, 0.006, 0.014, 0.027,
    0.040, 0.050, 0.055, 0.057, 0.058, 0.057, 0.055, 0.054,
    0.055, 0.058, 0.064, 0.072, 0.078, 0.074, 0.058, 0.031,
]


@dataclass(frozen=True)
class Anomaly:
    name: str
    start: date
    end: date
    description: str

    def active(self, day: date) -> bool:
        return self.start <= day <= self.end


ANDROID_RELEASE_BUG = Anomaly(
    "android_release_bug",
    date(2026, 10, 14),
    date(2026, 10, 18),
    "Релиз Android-приложения сломал кнопку «Написать продавцу»: конверсия в контакт на Android падает на 45%",
)
PROMO_SALE = Anomaly(
    "promo_sale",
    date(2026, 9, 18),
    date(2026, 9, 20),
    "Акция «-50% на продвижение»: число покупок x3, средний чек x0.5",
)
KAZAN_TRACKING_OUTAGE = Anomaly(
    "kazan_tracking_outage",
    date(2026, 10, 27),
    date(2026, 10, 27),
    "Сбой доставки клик-стрима: потеряны все события пользователей из Казани",
)
ANOMALIES = [ANDROID_RELEASE_BUG, PROMO_SALE, KAZAN_TRACKING_OUTAGE]


def contact_factor(day: date, platform: str) -> float:
    if platform == "android" and ANDROID_RELEASE_BUG.active(day):
        return 0.55
    return 1.0


def promo_volume_factor(day: date) -> float:
    return 3.0 if PROMO_SALE.active(day) else 1.0


def promo_price_factor(day: date) -> float:
    return 0.5 if PROMO_SALE.active(day) else 1.0


def lost_event_regions(day: date) -> set[str]:
    return {"Казань"} if KAZAN_TRACKING_OUTAGE.active(day) else set()
