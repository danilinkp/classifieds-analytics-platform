"""Takes dashboard screenshots for the README and reports charts that failed to render.

Runs inside the Playwright image on the compose network:
    make screenshots
"""

import os
import sys

from playwright.sync_api import sync_playwright

SUPERSET_URL = os.environ.get("SUPERSET_URL", "http://superset:8088")
PASSWORD = os.environ.get("SUPERSET_ADMIN_PASSWORD", "admin")
OUT_DIR = os.environ.get("OUT_DIR", "/docs/screenshots")
DASHBOARDS = ["marketplace-kpi", "listings-liquidity", "metric-monitoring"]


def main() -> int:
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page.goto(f"{SUPERSET_URL}/login/")
        page.fill("input[name=username], #username", "admin")
        page.fill("input[name=password], #password", PASSWORD)
        page.keyboard.press("Enter")
        page.wait_for_url(lambda url: "/login" not in url, timeout=30_000)

        for slug in DASHBOARDS:
            page.goto(f"{SUPERSET_URL}/superset/dashboard/{slug}/?standalone=2")
            page.wait_for_load_state("networkidle", timeout=120_000)
            # Charts render lazily after their queries return.
            page.wait_for_timeout(8_000)
            errors = page.locator(".dashboard-component-chart-holder .alert, .chart-container .ant-alert-error, [role=alert]")
            for i in range(errors.count()):
                failures += 1
                print(f"{slug}: {errors.nth(i).inner_text()[:300]!r}")
            path = os.path.join(OUT_DIR, f"{slug}.png")
            page.screenshot(path=path, full_page=True)
            print(f"saved {path}")
        browser.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
