import json
import logging
import time

import requests

log = logging.getLogger("bootstrap")

# Fields of a dataset column that the PUT endpoint accepts back.
COLUMN_FIELDS = {
    "id", "column_name", "type", "verbose_name", "description", "expression",
    "filterable", "groupby", "is_active", "is_dttm", "python_date_format", "extra",
}


class Superset:
    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self._wait_until_healthy()
        token = self._request("POST", "/api/v1/security/login", json={
            "username": username, "password": password, "provider": "db", "refresh": True,
        })["access_token"]
        self.session.headers["Authorization"] = f"Bearer {token}"
        csrf = self._request("GET", "/api/v1/security/csrf_token/")["result"]
        self.session.headers.update({"X-CSRFToken": csrf, "Referer": self.url})

    def _wait_until_healthy(self, attempts: int = 60) -> None:
        for _ in range(attempts):
            try:
                if self.session.get(f"{self.url}/health", timeout=5).ok:
                    return
            except requests.ConnectionError:
                pass
            time.sleep(5)
        raise RuntimeError(f"Superset at {self.url} is not healthy")

    def _request(self, method: str, path: str, **kwargs) -> dict:
        response = self.session.request(method, f"{self.url}{path}", timeout=60, **kwargs)
        if not response.ok:
            raise RuntimeError(f"{method} {path} -> {response.status_code}: {response.text[:1000]}")
        return response.json() if response.content else {}

    def _list(self, resource: str) -> list[dict]:
        items, page = [], 0
        while True:
            chunk = self._request("GET", f"/api/v1/{resource}/?q=(page:{page},page_size:100)")["result"]
            items.extend(chunk)
            if len(chunk) < 100:
                return items
            page += 1

    def _find(self, resource: str, field: str, value: str) -> int | None:
        for item in self._list(resource):
            if item.get(field) == value:
                return item["id"]
        return None

    def upsert_database(self, name: str, uri: str) -> int:
        payload = {
            "database_name": name,
            "sqlalchemy_uri": uri,
            "expose_in_sqllab": True,
            "allow_ctas": False,
            "allow_dml": False,
        }
        existing = self._find("database", "database_name", name)
        if existing:
            self._request("PUT", f"/api/v1/database/{existing}", json=payload)
            return existing
        return self._request("POST", "/api/v1/database/", json=payload)["id"]

    def upsert_dataset(self, database_id: int, spec: dict) -> dict:
        existing = None
        for item in self._list("dataset"):
            if item["table_name"] == spec["table_name"] and item.get("schema") == spec["schema"]:
                existing = item["id"]
        if existing is None:
            create = {"database": database_id, "schema": spec["schema"], "table_name": spec["table_name"]}
            if spec.get("sql"):
                create["sql"] = spec["sql"]
            existing = self._request("POST", "/api/v1/dataset/", json=create)["id"]
        elif spec.get("sql"):
            self._request("PUT", f"/api/v1/dataset/{existing}", json={"sql": spec["sql"]})

        # Picks up columns added to the underlying table since the dataset was created.
        self._request("PUT", f"/api/v1/dataset/{existing}/refresh")
        current = self._request("GET", f"/api/v1/dataset/{existing}")["result"]

        verbose = spec.get("columns", {})
        temporal = set(spec.get("temporal", []))
        columns = []
        for column in current["columns"]:
            item = {k: v for k, v in column.items() if k in COLUMN_FIELDS and v is not None}
            name = column["column_name"]
            if name in verbose:
                item["verbose_name"] = verbose[name]
            if name in temporal:
                item["is_dttm"] = True
            columns.append(item)

        existing_metrics = {m["metric_name"]: m["id"] for m in current["metrics"]}
        metrics = []
        for name, (expression, title, d3format) in spec["metrics"].items():
            metric = {"metric_name": name, "expression": expression, "verbose_name": title, "d3format": d3format}
            if name in existing_metrics:
                metric["id"] = existing_metrics[name]
            metrics.append(metric)

        self._request("PUT", f"/api/v1/dataset/{existing}", json={
            "columns": columns,
            "metrics": metrics,
            "main_dttm_col": spec["temporal"][0] if spec.get("temporal") else None,
            "description": spec.get("description", ""),
        })
        return {"id": existing, "columns": {c["column_name"] for c in current["columns"]}}

    def upsert_dashboard(self, slug: str, title: str) -> int:
        existing = self._find("dashboard", "slug", slug)
        if existing:
            return existing
        return self._request("POST", "/api/v1/dashboard/", json={
            "dashboard_title": title, "slug": slug, "published": True,
        })["id"]

    def upsert_chart(self, name: str, viz_type: str, dataset_id: int, params: dict, dashboard_id: int) -> int:
        params = {**params, "viz_type": viz_type, "datasource": f"{dataset_id}__table"}
        payload = {
            "slice_name": name,
            "viz_type": viz_type,
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "params": json.dumps(params, ensure_ascii=False),
            "dashboards": [dashboard_id],
        }
        existing = self._find("chart", "slice_name", name)
        if existing:
            self._request("PUT", f"/api/v1/chart/{existing}", json=payload)
            return existing
        return self._request("POST", "/api/v1/chart/", json=payload)["id"]

    def prune_charts(self, dashboard_id: int, keep: set[int]) -> None:
        """Deletes charts of the dashboard that are no longer defined in code."""
        for chart in self._request("GET", f"/api/v1/dashboard/{dashboard_id}/charts")["result"]:
            if chart["id"] not in keep:
                log.info("deleting stale chart %s %r", chart["id"], chart["slice_name"])
                self._request("DELETE", f"/api/v1/chart/{chart['id']}")

    def update_dashboard(self, dashboard_id: int, title: str, position: dict, metadata: dict) -> None:
        self._request("PUT", f"/api/v1/dashboard/{dashboard_id}", json={
            "dashboard_title": title,
            "published": True,
            "position_json": json.dumps(position, ensure_ascii=False),
            "json_metadata": json.dumps(metadata, ensure_ascii=False),
        })
