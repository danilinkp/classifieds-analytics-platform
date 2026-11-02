"""Builders of Superset chart form data and dashboard layout."""

from dataclasses import dataclass, field

ALL_TIME = "No filter"
DATE_FORMAT = "%d.%m.%Y"


def sql_metric(expression: str, label: str) -> dict:
    return {"expressionType": "SQL", "sqlExpression": expression, "label": label}


def sql_filter(expression: str) -> dict:
    return {"expressionType": "SQL", "sqlExpression": expression, "clause": "WHERE"}


def big_number(metric: str, x_axis: str, number_format: str, filters: list | None = None) -> tuple[str, dict]:
    return "big_number", {
        "x_axis": x_axis,
        "time_grain_sqla": "P1D",
        "metric": metric,
        "adhoc_filters": filters or [],
        "time_range": ALL_TIME,
        "show_trend_line": True,
        "start_y_axis_at_zero": False,
        "compare_lag": "7",
        "compare_suffix": "к неделе назад",
        "y_axis_format": number_format,
        "time_format": DATE_FORMAT,
        "header_font_size": 0.3,
        "subheader_font_size": 0.125,
    }


def timeseries(
    metrics: list,
    x_axis: str,
    *,
    groupby: list | None = None,
    number_format: str = "SMART_NUMBER",
    kind: str = "line",
    stacked: bool = False,
    filters: list | None = None,
    time_grain: str = "P1D",
) -> tuple[str, dict]:
    viz = {"line": "echarts_timeseries_line", "bar": "echarts_timeseries_bar", "area": "echarts_area"}[kind]
    return viz, {
        "x_axis": x_axis,
        "time_grain_sqla": time_grain,
        "metrics": metrics,
        "groupby": groupby or [],
        "adhoc_filters": filters or [],
        "time_range": ALL_TIME,
        "row_limit": 10000,
        "y_axis_format": number_format,
        "x_axis_time_format": "%d.%m",
        "tooltipTimeFormat": DATE_FORMAT,
        "rich_tooltip": True,
        "show_legend": True,
        "legendType": "scroll",
        "legendOrientation": "top",
        "markerEnabled": False,
        "zoomable": True,
        # Truncating the axis to the data minimum would cut off the lower series of a stack.
        "truncateYAxis": not stacked,
        "y_axis_bounds": [None, None],
        "stack": "Stack" if stacked else None,
        "opacity": 0.6,
    }


def category_bar(
    metric: str,
    dimension: str,
    number_format: str,
    *,
    filters: list | None = None,
    horizontal: bool = True,
    stack_by: str | None = None,
) -> tuple[str, dict]:
    stacked = stack_by is not None
    return "echarts_timeseries_bar", {
        "x_axis": dimension,
        "metrics": [metric],
        "groupby": [stack_by] if stacked else [],
        "stack": "Stack" if stacked else None,
        # Shares within each bar: the mix matters here, not the absolute volume.
        "contributionMode": "row" if stacked else None,
        "adhoc_filters": filters or [],
        "time_range": ALL_TIME,
        "row_limit": 100,
        "orientation": "horizontal" if horizontal else "vertical",
        "x_axis_sort": metric,
        "x_axis_sort_asc": horizontal,
        "y_axis_format": number_format,
        "show_value": not stacked,
        "show_legend": stacked,
        "legendOrientation": "top",
        "rich_tooltip": True,
        "truncateYAxis": False,
    }


def heatmap(metric: str, x: str, y: str, number_format: str) -> tuple[str, dict]:
    return "heatmap_v2", {
        "x_axis": x,
        "groupby": y,
        "metric": metric,
        "adhoc_filters": [],
        "time_range": ALL_TIME,
        "row_limit": 10000,
        "linear_color_scheme": "superset_seq_1",
        "normalize_across": "heatmap",
        "show_values": True,
        "show_legend": True,
        "show_percentage": False,
        "y_axis_format": number_format,
        "sort_x_axis": "alpha_asc",
        "sort_y_axis": "alpha_asc",
        "xscale_interval": 1,
        "yscale_interval": 1,
        "left_margin": "auto",
        "bottom_margin": "auto",
    }


def donut(metric: str, dimension: str) -> tuple[str, dict]:
    return "pie", {
        "groupby": [dimension],
        "metric": metric,
        "adhoc_filters": [],
        "time_range": ALL_TIME,
        "row_limit": 100,
        "sort_by_metric": True,
        "donut": True,
        "innerRadius": 40,
        "outerRadius": 75,
        "show_labels": True,
        "labels_outside": False,
        "label_type": "percent",
        "number_format": "SMART_NUMBER",
        "show_legend": True,
        "legendType": "scroll",
        "legendOrientation": "right",
    }


def raw_table(
    columns: list[str],
    order_by: str,
    *,
    filters: list | None = None,
    formats: dict[str, str] | None = None,
    page_length: int = 15,
) -> tuple[str, dict]:
    return "table", {
        "query_mode": "raw",
        "all_columns": columns,
        "order_by_cols": [f'["{order_by}", false]'],
        "adhoc_filters": filters or [],
        "time_range": ALL_TIME,
        "row_limit": 5000,
        "server_page_length": page_length,
        "page_length": page_length,
        "include_search": True,
        "table_timestamp_format": DATE_FORMAT,
        "column_config": {name: {"d3NumberFormat": fmt} for name, fmt in (formats or {}).items()},
        "conditional_formatting": [],
    }


@dataclass
class Chart:
    key: str
    title: str
    dataset: str
    viz: tuple[str, dict]
    width: int
    height: int = 50


@dataclass
class Markdown:
    text: str
    width: int = 12
    height: int = 14


@dataclass
class Layout:
    """Builds Superset's position_json from rows of charts and markdown blocks."""

    title: str
    rows: list[list[Chart | Markdown]] = field(default_factory=list)

    def position(self, chart_ids: dict[str, int]) -> dict:
        position = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
            "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
            "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": self.title}},
        }
        for row_index, row in enumerate(self.rows):
            row_id = f"ROW-{row_index}"
            position["GRID_ID"]["children"].append(row_id)
            position[row_id] = {
                "type": "ROW",
                "id": row_id,
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID"],
                "meta": {"background": "BACKGROUND_TRANSPARENT"},
            }
            for item_index, item in enumerate(row):
                parents = ["ROOT_ID", "GRID_ID", row_id]
                if isinstance(item, Markdown):
                    item_id = f"MARKDOWN-{row_index}-{item_index}"
                    position[item_id] = {
                        "type": "MARKDOWN",
                        "id": item_id,
                        "children": [],
                        "parents": parents,
                        "meta": {"code": item.text, "width": item.width, "height": item.height},
                    }
                else:
                    item_id = f"CHART-{item.key}"
                    position[item_id] = {
                        "type": "CHART",
                        "id": item_id,
                        "children": [],
                        "parents": parents,
                        "meta": {
                            "chartId": chart_ids[item.key],
                            "width": item.width,
                            "height": item.height,
                            "sliceName": item.title,
                        },
                    }
                position[row_id]["children"].append(item_id)
        return position

    def charts(self) -> list[Chart]:
        return [item for row in self.rows for item in row if isinstance(item, Chart)]


@dataclass
class SelectFilter:
    key: str
    name: str
    dataset: str
    column: str
    default: str | None = None
    multi: bool = True
    required: bool = False
    only_charts: list[str] | None = None


def time_filter() -> dict:
    return {
        "id": "NATIVE_FILTER-period",
        "name": "Период",
        "filterType": "filter_time",
        "type": "NATIVE_FILTER",
        "targets": [{}],
        "controlValues": {},
        "defaultDataMask": {"extraFormData": {}, "filterState": {}},
        "cascadeParentIds": [],
        "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
        "description": "",
    }


def select_filter(spec: SelectFilter, dataset_id: int, excluded_chart_ids: list[int]) -> dict:
    default_mask = {"extraFormData": {}, "filterState": {}}
    if spec.default is not None:
        default_mask = {
            "extraFormData": {"filters": [{"col": spec.column, "op": "IN", "val": [spec.default]}]},
            "filterState": {"value": [spec.default]},
        }
    return {
        "id": f"NATIVE_FILTER-{spec.key}",
        "name": spec.name,
        "filterType": "filter_select",
        "type": "NATIVE_FILTER",
        "targets": [{"datasetId": dataset_id, "column": {"name": spec.column}}],
        "controlValues": {
            "multiSelect": spec.multi,
            "enableEmptyFilter": spec.required,
            "defaultToFirstItem": False,
            "inverseSelection": False,
            "searchAllOptions": False,
        },
        "defaultDataMask": default_mask,
        "cascadeParentIds": [],
        "scope": {"rootPath": ["ROOT_ID"], "excluded": excluded_chart_ids},
        "description": "",
    }
