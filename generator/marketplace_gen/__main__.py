import argparse
import logging
import time
from datetime import date, timedelta

from . import config as cfg
from .simulation import bootstrap, generate_day
from .storage import connect, last_loaded_date, load_state, require_previous_day_loaded, write_batch

log = logging.getLogger("marketplace_gen")


def run_day(day: date) -> dict[str, int]:
    client = connect()
    require_previous_day_loaded(client, day)
    started = time.monotonic()
    state = load_state(client, day)
    batch = generate_day(day, state)
    loaded = write_batch(client, day, batch)
    log.info("%s loaded in %.1fs: %s", day, time.monotonic() - started, loaded)
    return loaded


def run_bootstrap() -> None:
    client = connect()
    day = cfg.SIMULATION_START - timedelta(days=1)
    if last_loaded_date(client) is not None:
        log.info("raw layer already initialised, skipping bootstrap")
        return
    loaded = write_batch(client, day, bootstrap(day))
    log.info("bootstrap %s: %s", day, loaded)


def run_backfill(start: date, end: date) -> None:
    run_bootstrap()
    day = start
    while day <= end:
        run_day(day)
        day += timedelta(days=1)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="marketplace_gen", description="Synthetic classifieds marketplace source")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap", help="create the initial user and listing base")

    day_cmd = sub.add_parser("day", help="generate and load a single day")
    day_cmd.add_argument("date", type=date.fromisoformat)

    backfill_cmd = sub.add_parser("backfill", help="generate a range of days")
    backfill_cmd.add_argument("--start", type=date.fromisoformat, default=cfg.SIMULATION_START)
    backfill_cmd.add_argument("--end", type=date.fromisoformat, default=date.today() - timedelta(days=1))

    args = parser.parse_args()
    if args.command == "bootstrap":
        run_bootstrap()
    elif args.command == "day":
        run_day(args.date)
    else:
        run_backfill(args.start, args.end)


if __name__ == "__main__":
    main()
