import html as html_lib
import json
import os
import re
from datetime import datetime

import pandas as pd

from core.metrics_store import load_metrics

ROWS_PER_PAGE = 20

CHART_METRICS = (
    ("lcp", "LCP"),
    ("ttfb", "TTFB"),
    ("fcp", "FCP"),
    ("load", "Load"),
    ("cls", "CLS"),
)

GEO_CHART_ORDER = ("Russia", "Uzbekistan", "Bangladesh")

CHART_SOURCE_STYLES = {
    "local_ip": {"label": "Локальный IP", "color": "#94a3b8"},
    "local_proxy": {"label": "Локальный + прокси", "color": "#2563eb"},
    "dolphin_proxy": {"label": "Dolphin + прокси", "color": "#16a34a"},
}

CHART_SOURCE_ORDER = ("local_ip", "local_proxy", "dolphin_proxy")

COMPARE_SOURCES = ("local_proxy", "dolphin_proxy")
COMPARE_PERIOD_MS = 7 * 24 * 60 * 60 * 1000
DELTA_PAIR_MAX_GAP_MS = 30 * 60 * 1000


COLUMN_META = {
    "row_id": {
        "label": "#",
        "tooltip": "Номер записи. Для удаления: python delete_metrics.py --ids N",
    },
    "datetime": {
        "label": "Дата и время",
        "tooltip": "Момент, когда метрики были записаны в CSV.",
    },
    "geo": {
        "label": "Гео",
        "tooltip": "География профиля браузера (страна прокси / Dolphin Anty).",
    },
    "page": {
        "label": "Страница",
        "tooltip": "Тестируемая страница: HOME — главная.",
    },
    "source": {
        "label": "Источник",
        "tooltip": "local_ip — ваш IP; local_proxy — Playwright на ПК через прокси; dolphin_proxy — Dolphin Anty.",
    },
    "final_url": {
        "label": "Финальный URL",
        "tooltip": "Адрес страницы после всех редиректов.",
    },
    "ttfb": {
        "label": "TTFB",
        "tooltip": "Time To First Byte — время до первого байта ответа сервера (мс). Показывает скорость реакции бэкенда и сети.",
        "unit": "мс",
        "thresholds": [(800, "good"), (1800, "warn")],
        "lower_is_better": True,
    },
    "fcp": {
        "label": "FCP",
        "tooltip": "First Contentful Paint — когда пользователь впервые видит контент: текст, изображение или canvas (мс).",
        "unit": "мс",
        "thresholds": [(1800, "good"), (3000, "warn")],
        "lower_is_better": True,
    },
    "lcp": {
        "label": "LCP",
        "tooltip": "Largest Contentful Paint — когда отрисовывается самый крупный видимый элемент страницы (мс). Ключевая метрика воспринимаемой скорости.",
        "unit": "мс",
        "thresholds": [(2500, "good"), (4000, "warn")],
        "lower_is_better": True,
    },
    "dom_content_loaded": {
        "label": "DCL",
        "tooltip": "DOM Content Loaded — HTML полностью разобран, DOM готов. Скрипты могут ещё догружаться (мс).",
        "unit": "мс",
        "thresholds": [(2000, "good"), (4000, "warn")],
        "lower_is_better": True,
    },
    "load": {
        "label": "Load",
        "tooltip": "Полная загрузка страницы — событие load, когда загружены все ресурсы на странице (мс).",
        "unit": "мс",
        "thresholds": [(3000, "good"), (5000, "warn")],
        "lower_is_better": True,
    },
    "cls": {
        "label": "CLS",
        "tooltip": "Cumulative Layout Shift — насколько сильно «прыгает» вёрстка при загрузке. 0 — идеально, чем меньше — тем лучше.",
        "unit": "",
        "thresholds": [(0.1, "good"), (0.25, "warn")],
        "lower_is_better": True,
    },
    "total_requests": {
        "label": "Запросы",
        "tooltip": "Общее количество сетевых запросов при загрузке страницы. Меньше — обычно лучше.",
        "unit": "",
        "thresholds": [(50, "good"), (100, "warn")],
        "lower_is_better": True,
    },
    "total_transfer_size_kb": {
        "label": "Трафик",
        "tooltip": "Суммарный объём переданных данных по всем запросам (КБ). Влияет на скорость на медленных сетях.",
        "unit": "КБ",
        "thresholds": [(1000, "good"), (3000, "warn")],
        "lower_is_better": True,
    },
    "redirects": {
        "label": "Редиректы",
        "tooltip": "Число переадресаций до финального URL: HTTP-редиректы + клиентские (JS), если итоговый адрес отличается от стартового.",
        "unit": "",
        "thresholds": [(0, "good"), (2, "warn")],
        "lower_is_better": True,
    },
    "error": {
        "label": "Ошибка",
        "tooltip": "Текст ошибки, если страница не загрузилась. Пустое значение — успех.",
    },
}

SUMMARY_COLUMNS = [
    col for col, meta in COLUMN_META.items() if meta.get("thresholds")
]


def _to_number(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_status(column: str, value) -> str:
    meta = COLUMN_META.get(column, {})
    thresholds = meta.get("thresholds")
    if not thresholds:
        if column == "error":
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return "neutral"
            text = str(value).strip()
            if text and text.lower() != "nan":
                return "bad"
        return "neutral"

    num = _to_number(value)
    if num is None:
        return "neutral"

    if column in ("fcp", "lcp", "load", "dom_content_loaded") and num <= 0:
        return "bad"

    for limit, status in thresholds:
        if num <= limit:
            return status
    return "bad"


SOURCE_LABELS = {
    "local_ip": "Локальный IP",
    "local_proxy": "Локальный + прокси",
    "dolphin_proxy": "Dolphin + прокси",
    "__all__": "Все источники",
}

SOURCE_ORDER = ("local_ip", "local_proxy", "dolphin_proxy")


def _format_cell(column: str, value) -> str:
    if column == "source":
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return "—"
        return SOURCE_LABELS.get(text, text)

    if column == "row_id":
        num = _to_number(value)
        return "—" if num is None else str(int(num))

    if column == "datetime":
        if pd.isna(value):
            return "—"
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return "—"
        if "." in text:
            text = text.split(".", 1)[0].replace("T", " ")
        return text

    if column == "error":
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        text = str(value).strip()
        return text if text and text.lower() != "nan" else "—"

    if column == "cls":
        num = _to_number(value)
        return "—" if num is None else f"{num:.3f}"

    if column in COLUMN_META and COLUMN_META[column].get("unit") == "мс":
        num = _to_number(value)
        return "—" if num is None else str(int(num))

    if column == "total_transfer_size_kb":
        num = _to_number(value)
        unit = COLUMN_META[column]["unit"]
        return "—" if num is None else f"{int(num)} {unit}"

    if pd.isna(value):
        return "—"
    return str(value)


def _successful_rows(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["error"].fillna("").astype(str).str.strip() == ""]


def _valid_metric_series(series: pd.Series, column: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if column in ("fcp", "lcp", "load", "dom_content_loaded"):
        values = values[values > 0]
    return values.dropna()


def _round_summary_value(column: str, value: float):
    if column == "cls":
        return round(value, 3)
    return int(round(value))


def _aggregate_metric(series: pd.Series, column: str, method: str):
    values = _valid_metric_series(series, column)
    if values.empty:
        return None
    raw = float(values.mean() if method == "mean" else values.median())
    return _round_summary_value(column, raw)


def _normalize_source(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _source_sort_key(source: str) -> tuple[int, str]:
    source = _normalize_source(source)
    if source in SOURCE_ORDER:
        return (SOURCE_ORDER.index(source), source)
    return (len(SOURCE_ORDER), source)


def _make_summary_rows(
    group: pd.DataFrame,
    *,
    geo: str,
    page: str,
    source: str,
) -> list[dict]:
    rows = []
    for label, method in (("Среднее", "mean"), ("Медиана", "median")):
        row = {
            "datetime": label,
            "geo": geo,
            "page": page,
            "source": source,
            "final_url": "—",
            "error": "",
        }
        for col in SUMMARY_COLUMNS:
            row[col] = _aggregate_metric(group[col], col, method)
        rows.append(row)
    return rows


def _build_summary_sections(df: pd.DataFrame) -> list[tuple[str, list[dict]]]:
    ok = _successful_rows(df)
    if ok.empty:
        return []

    if "source" not in ok.columns:
        ok = ok.copy()
        ok["source"] = ""

    ok = ok.copy()
    ok["_source_key"] = ok["source"].map(_normalize_source)

    sections: list[tuple[str, list[dict]]] = []

    by_geo_source: list[dict] = []
    for (geo, page, source), group in sorted(
        ok.groupby(["geo", "page", "_source_key"], sort=False),
        key=lambda item: (item[0][0], item[0][1], _source_sort_key(item[0][2])),
    ):
        if not source:
            continue
        by_geo_source.extend(
            _make_summary_rows(group, geo=geo, page=page, source=source)
        )
    if by_geo_source:
        sections.append(("По гео и источнику", by_geo_source))

    by_geo_all_sources: list[dict] = []
    for (geo, page), group in sorted(ok.groupby(["geo", "page"], sort=False)):
        by_geo_all_sources.extend(
            _make_summary_rows(group, geo=geo, page=page, source="__all__")
        )
    if by_geo_all_sources:
        sections.append(("По гео (все источники)", by_geo_all_sources))

    by_source_all_geo: list[dict] = []
    for source, group in sorted(
        ok.groupby("_source_key", sort=False),
        key=lambda item: _source_sort_key(item[0]),
    ):
        if not source:
            continue
        by_source_all_geo.extend(
            _make_summary_rows(
                group,
                geo="Все гео",
                page="Все страницы",
                source=source,
            )
        )
    if by_source_all_geo:
        sections.append(("По источнику (все гео)", by_source_all_geo))

    total_rows = _make_summary_rows(
        ok,
        geo="Все гео",
        page="Все страницы",
        source="__all__",
    )
    sections.append(("Итого", total_rows))

    return sections


def _render_summary_divider(columns: list[str], title: str) -> str:
    return (
        f'<tr class="summary-divider"><td colspan="{len(columns)}">'
        f"{html_lib.escape(title)}</td></tr>"
    )


def _render_row(columns: list[str], row, row_class: str = "") -> str:
    cells = []
    for col in columns:
        raw = row[col] if col in row else None
        status = _metric_status(col, raw)
        display = _format_cell(col, raw)
        cells.append(f'<td class="metric {status}">{display}</td>')
    class_attr = f' class="{row_class}"' if row_class else ""
    return f"<tr{class_attr}>{''.join(cells)}</tr>"


def _geo_chart_id(geo: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", geo.lower()).strip("-")
    return slug or "geo"


def _chart_geos(df: pd.DataFrame) -> list[str]:
    present = set(df["geo"].dropna().astype(str))
    ordered = [geo for geo in GEO_CHART_ORDER if geo in present]
    extras = sorted(present - set(ordered))
    return ordered + extras


def _prepare_chart_points(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []

    chart_df = df[df["page"].fillna("").astype(str).str.upper() == "HOME"]
    points: list[dict] = []

    for _, row in chart_df.iterrows():
        dt = row.get("datetime")
        if dt is None or pd.isna(dt):
            continue

        source = _normalize_source(row.get("source"))
        if not source:
            continue

        error = str(row.get("error", "") or "").strip()
        ok = not error or error.lower() == "nan"
        point: dict = {
            "ts": int(pd.Timestamp(dt).timestamp() * 1000),
            "geo": str(row.get("geo", "")),
            "source": source,
            "ok": ok,
        }

        for metric, _ in CHART_METRICS:
            value = _to_number(row.get(metric))
            if not ok or value is None:
                point[metric] = None
            elif metric == "cls":
                point[metric] = round(value, 3)
            elif metric in ("fcp", "lcp", "load", "dom_content_loaded") and value <= 0:
                point[metric] = None
            else:
                point[metric] = int(round(value)) if metric != "cls" else value

        points.append(point)

    points.sort(key=lambda item: item["ts"])
    return points


def _build_charts_section(geos: list[str]) -> str:
    if not geos:
        return ""

    metric_options = "".join(
        f'<option value="{key}">{label}</option>' for key, label in CHART_METRICS
    )

    cards = []
    for geo in geos:
        geo_id = _geo_chart_id(geo)
        cards.append(
            f"""
        <article class="chart-card" data-geo="{html_lib.escape(geo, quote=True)}">
            <div class="chart-header">
                <h3 class="chart-title">{html_lib.escape(geo)}</h3>
                <div class="chart-controls">
                    <div class="period-btns" role="group" aria-label="Период">
                        <button type="button" class="period-btn active" data-period="24h">24 ч</button>
                        <button type="button" class="period-btn" data-period="7d">7 дн</button>
                        <button type="button" class="period-btn" data-period="30d">30 дн</button>
                    </div>
                    <label class="metric-picker">
                        <span>Метрика</span>
                        <select class="metric-select">{metric_options}</select>
                    </label>
                </div>
            </div>
            <div class="chart-canvas-wrap">
                <canvas id="chart-{geo_id}" class="chart-timeline" aria-label="Динамика {html_lib.escape(geo)}"></canvas>
                <p class="chart-empty chart-empty-timeline hidden">Нет данных за выбранный период</p>
            </div>
            <p class="chart-meta"></p>
            <div class="chart-subsection">
                <h4 class="chart-subtitle">Сравнение local vs Dolphin · медиана и Δ за 7 дней</h4>
                <div class="chart-duo">
                    <div class="chart-duo-item">
                        <p class="chart-duo-label">Медиана (7 дн)</p>
                        <div class="chart-canvas-wrap chart-canvas-wrap--short">
                            <canvas id="chart-bar-{geo_id}" class="chart-bar" aria-label="Медиана {html_lib.escape(geo)}"></canvas>
                            <p class="chart-empty chart-empty-bar hidden">Нет данных</p>
                        </div>
                    </div>
                    <div class="chart-duo-item">
                        <p class="chart-duo-label">Δ local − Dolphin (7 дн)</p>
                        <div class="chart-canvas-wrap chart-canvas-wrap--short">
                            <canvas id="chart-delta-{geo_id}" class="chart-delta" aria-label="Delta {html_lib.escape(geo)}"></canvas>
                            <p class="chart-empty chart-empty-delta hidden">Нет пар замеров</p>
                        </div>
                    </div>
                </div>
                <p class="chart-compare-meta"></p>
            </div>
        </article>
        """
        )

    return f"""
    <section class="charts-section">
        <h2 class="section-title">Динамика по гео</h2>
        <p class="subtitle charts-intro">
            Линии — тренд по времени. Ниже — медиана local+прокси vs Dolphin за 7 дней и разница (Δ) по парам
            прогонов. Положительная Δ — local медленнее. Метрика по умолчанию: LCP (мс).
        </p>
        <div class="charts-grid">{''.join(cards)}</div>
    </section>
    """


def _build_table(df: pd.DataFrame) -> str:
    columns = ["row_id"] + [
        col for col in df.columns if col in COLUMN_META and col != "row_id"
    ]

    header_cells = []
    for col in columns:
        meta = COLUMN_META[col]
        tooltip = html_lib.escape(meta["tooltip"], quote=True)
        header_cells.append(
            f'<th><span class="th-label" data-tooltip="{tooltip}">{meta["label"]}</span></th>'
        )

    body_rows = [
        _render_row(columns, row, "data-row") for _, row in df.iterrows()
    ]
    footer_parts = []
    for title, section_rows in _build_summary_sections(df):
        footer_parts.append(_render_summary_divider(columns, title))
        footer_parts.extend(
            _render_row(columns, row, "summary-row") for row in section_rows
        )
    footer_html = "".join(footer_parts)
    total_rows = len(body_rows)

    return f"""
    <div class="table-wrap">
        <table class="metrics-table">
            <thead><tr>{''.join(header_cells)}</tr></thead>
            <tbody id="metrics-body">{''.join(body_rows)}</tbody>
            <tfoot>{footer_html}</tfoot>
        </table>
    </div>
    <div class="pagination" id="table-pagination" data-rows-per-page="{ROWS_PER_PAGE}" data-total-rows="{total_rows}">
        <button type="button" class="page-btn" id="page-prev" disabled>← Назад</button>
        <span class="page-info" id="page-info"></span>
        <button type="button" class="page-btn" id="page-next">Вперёд →</button>
    </div>
    """


def generate_html_report():
    if not os.path.exists("reports/metrics.csv"):
        print("CSV файл не найден")
        return

    df = load_metrics()
    if df.empty:
        print("CSV пуст — отчёт не создан")
        return

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    table_html = _build_table(df)
    chart_points = _prepare_chart_points(df)
    chart_geos = _chart_geos(df) if chart_points else []
    charts_html = _build_charts_section(chart_geos)
    chart_points_json = json.dumps(chart_points, ensure_ascii=False)
    chart_styles_json = json.dumps(CHART_SOURCE_STYLES, ensure_ascii=False)
    chart_source_order_json = json.dumps(CHART_SOURCE_ORDER)
    compare_sources_json = json.dumps(COMPARE_SOURCES)
    compare_period_ms = COMPARE_PERIOD_MS
    delta_pair_gap_ms = DELTA_PAIR_MAX_GAP_MS

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Fastpari Monitoring — {generated_at}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        :root {{
            --bg: #f4f6fb;
            --card: #ffffff;
            --text: #1f2937;
            --muted: #6b7280;
            --border: #e5e7eb;
            --accent: #2563eb;
            --good-bg: #dcfce7;
            --good-text: #166534;
            --warn-bg: #fef9c3;
            --warn-text: #854d0e;
            --bad-bg: #fee2e2;
            --bad-text: #991b1b;
            --neutral-bg: #f9fafb;
        }}

        * {{ box-sizing: border-box; }}

        body {{
            margin: 0;
            font-family: "Segoe UI", Tahoma, sans-serif;
            background: linear-gradient(180deg, #eef2ff 0%, var(--bg) 220px);
            color: var(--text);
            line-height: 1.5;
        }}

        .container {{
            max-width: 1520px;
            margin: 0 auto;
            padding: 28px 24px 40px;
        }}

        .hero {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px 28px;
            box-shadow: 0 10px 30px rgba(37, 99, 235, 0.08);
            margin-bottom: 24px;
        }}

        h1 {{
            margin: 0 0 8px;
            font-size: 28px;
        }}

        .subtitle {{
            color: var(--muted);
            margin: 0;
        }}

        .legend, .glossary {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 18px 22px;
            margin-bottom: 20px;
        }}

        .legend h2, .glossary h2, .section-title {{
            margin: 0 0 12px;
            font-size: 18px;
        }}

        .legend-items {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}

        .legend-item {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            border-radius: 999px;
            font-size: 13px;
            border: 1px solid var(--border);
            background: #fff;
        }}

        .swatch {{
            width: 14px;
            height: 14px;
            border-radius: 4px;
            display: inline-block;
        }}

        .swatch.good {{ background: var(--good-bg); border: 1px solid #86efac; }}
        .swatch.warn {{ background: var(--warn-bg); border: 1px solid #fde047; }}
        .swatch.bad {{ background: var(--bad-bg); border: 1px solid #fca5a5; }}
        .swatch.neutral {{ background: var(--neutral-bg); border: 1px solid var(--border); }}

        .glossary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 12px;
        }}

        .glossary-item {{
            background: #f8fafc;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px 14px;
        }}

        .glossary-item strong {{
            display: block;
            margin-bottom: 4px;
            color: var(--accent);
        }}

        .glossary-item span {{
            color: var(--muted);
            font-size: 14px;
        }}

        .table-wrap {{
            overflow-x: auto;
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 14px;
            box-shadow: 0 4px 18px rgba(15, 23, 42, 0.05);
        }}

        .metrics-table {{
            width: 100%;
            border-collapse: collapse;
            min-width: 1220px;
            font-size: 14px;
        }}

        .metrics-table thead th {{
            position: sticky;
            top: 0;
            background: #1e293b;
            color: #f8fafc;
            text-align: left;
            padding: 12px 14px;
            white-space: nowrap;
            overflow: visible;
            z-index: 2;
        }}

        .metrics-table tbody td {{
            padding: 11px 14px;
            border-top: 1px solid var(--border);
            vertical-align: top;
        }}

        .metrics-table tbody tr:hover {{
            background: #f8fafc;
        }}

        .metrics-table tfoot td {{
            padding: 11px 14px;
            border-top: 1px solid var(--border);
            vertical-align: top;
            background: #f8fafc;
        }}

        .metrics-table tfoot tr:first-child td {{
            border-top: 3px solid #1e293b;
        }}

        .metrics-table tfoot tr.summary-row td:first-child {{
            color: var(--accent);
            font-weight: 700;
            white-space: nowrap;
        }}

        .metrics-table tfoot tr.summary-row:hover {{
            background: #eef2ff;
        }}

        .metrics-table tfoot tr.summary-divider td {{
            background: #1e293b;
            color: #f8fafc;
            font-weight: 600;
            font-size: 13px;
            text-align: left;
            padding: 10px 14px;
            border-top: 3px solid #1e293b;
        }}

        .th-label {{
            display: inline-block;
            cursor: help;
            border-bottom: 1px dashed rgba(255, 255, 255, 0.45);
        }}

        .global-tooltip {{
            position: fixed;
            display: none;
            max-width: 340px;
            min-width: 240px;
            padding: 12px 14px;
            background: #111827;
            color: #f9fafb;
            border-radius: 10px;
            font-size: 12px;
            font-weight: 400;
            line-height: 1.5;
            white-space: normal;
            word-wrap: break-word;
            text-align: left;
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.35);
            z-index: 99999;
            pointer-events: none;
        }}

        .global-tooltip.visible {{
            display: block;
        }}

        td.metric.good {{
            background: var(--good-bg);
            color: var(--good-text);
            font-weight: 600;
        }}

        td.metric.warn {{
            background: var(--warn-bg);
            color: var(--warn-text);
            font-weight: 600;
        }}

        td.metric.bad {{
            background: var(--bad-bg);
            color: var(--bad-text);
            font-weight: 600;
        }}

        td.metric.neutral {{
            background: var(--neutral-bg);
        }}

        .pagination {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 16px;
            margin-top: 16px;
            padding: 14px 18px;
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 14px;
        }}

        .page-btn {{
            border: 1px solid var(--border);
            background: #fff;
            color: var(--text);
            border-radius: 8px;
            padding: 8px 14px;
            font-size: 14px;
            cursor: pointer;
        }}

        .page-btn:hover:not(:disabled) {{
            border-color: var(--accent);
            color: var(--accent);
        }}

        .page-btn:disabled {{
            opacity: 0.45;
            cursor: not-allowed;
        }}

        .page-info {{
            color: var(--muted);
            font-size: 14px;
            min-width: 180px;
            text-align: center;
        }}

        tr.data-row.hidden-row {{
            display: none;
        }}

        .charts-section {{
            margin-top: 32px;
        }}

        .charts-intro {{
            margin: 0 0 18px;
        }}

        .charts-grid {{
            display: grid;
            gap: 20px;
        }}

        .chart-card {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 18px 20px 16px;
            box-shadow: 0 4px 18px rgba(15, 23, 42, 0.05);
        }}

        .chart-header {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 14px;
        }}

        .chart-title {{
            margin: 0;
            font-size: 18px;
        }}

        .chart-controls {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 12px;
        }}

        .period-btns {{
            display: inline-flex;
            border: 1px solid var(--border);
            border-radius: 10px;
            overflow: hidden;
            background: #fff;
        }}

        .period-btn {{
            border: 0;
            background: transparent;
            color: var(--muted);
            padding: 8px 14px;
            font-size: 13px;
            cursor: pointer;
        }}

        .period-btn.active {{
            background: var(--accent);
            color: #fff;
            font-weight: 600;
        }}

        .metric-picker {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            color: var(--muted);
        }}

        .metric-select {{
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 7px 10px;
            font-size: 13px;
            background: #fff;
            color: var(--text);
        }}

        .chart-canvas-wrap {{
            position: relative;
            height: 320px;
        }}

        .chart-canvas-wrap canvas {{
            width: 100% !important;
            height: 100% !important;
        }}

        .chart-empty {{
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
            color: var(--muted);
            background: #f8fafc;
            border: 1px dashed var(--border);
            border-radius: 10px;
        }}

        .chart-empty.hidden {{
            display: none;
        }}

        .chart-meta {{
            margin: 10px 0 0;
            font-size: 13px;
            color: var(--muted);
        }}

        .chart-subsection {{
            margin-top: 20px;
            padding-top: 18px;
            border-top: 1px solid var(--border);
        }}

        .chart-subtitle {{
            margin: 0 0 12px;
            font-size: 15px;
            color: var(--text);
        }}

        .chart-duo {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
        }}

        .chart-duo-label {{
            margin: 0 0 8px;
            font-size: 13px;
            color: var(--muted);
            font-weight: 600;
        }}

        .chart-canvas-wrap--short {{
            height: 260px;
        }}

        .chart-compare-meta {{
            margin: 12px 0 0;
            font-size: 13px;
            color: var(--muted);
        }}
    </style>
</head>
<body>
    <div class="container">
        <section class="hero">
            <h1>Fastpari Performance Report</h1>
            <p class="subtitle">Сгенерировано: {generated_at}</p>
        </section>

        <section class="legend">
            <h2>Цветовая индикация</h2>
            <div class="legend-items">
                <span class="legend-item"><span class="swatch good"></span> Хорошо</span>
                <span class="legend-item"><span class="swatch warn"></span> Средне</span>
                <span class="legend-item"><span class="swatch bad"></span> Плохо</span>
                <span class="legend-item"><span class="swatch neutral"></span> Нет оценки / текст</span>
            </div>
        </section>

        <section class="glossary">
            <h2>Что означают метрики</h2>
            <div class="glossary-grid">
                <div class="glossary-item"><strong>TTFB</strong><span>Время до первого байта ответа сервера. &lt; 800 мс — хорошо.</span></div>
                <div class="glossary-item"><strong>FCP</strong><span>Первый видимый контент на экране. &lt; 1.8 с — хорошо.</span></div>
                <div class="glossary-item"><strong>LCP</strong><span>Отрисовка крупнейшего элемента. &lt; 2.5 с — хорошо.</span></div>
                <div class="glossary-item"><strong>DCL</strong><span>DOM готов, HTML разобран. &lt; 2 с — хорошо.</span></div>
                <div class="glossary-item"><strong>Load</strong><span>Полная загрузка всех ресурсов. &lt; 3 с — хорошо.</span></div>
                <div class="glossary-item"><strong>CLS</strong><span>Стабильность вёрстки. &lt; 0.1 — хорошо, 0 — идеально.</span></div>
                <div class="glossary-item"><strong>Запросы</strong><span>Число сетевых запросов при загрузке. Меньше — лучше.</span></div>
                <div class="glossary-item"><strong>Трафик</strong><span>Объём скачанных данных в КБ. Меньше — лучше.</span></div>
                <div class="glossary-item"><strong>Редиректы</strong><span>HTTP + JS-редиректы. Если fastpari.com → другой домен, считается минимум 1.</span></div>
            </div>
        </section>

        <h2 class="section-title">Результаты измерений</h2>
        <p class="subtitle" style="margin: 0 0 14px;">Наведите на заголовок столбца, чтобы увидеть подробное описание. Внизу таблицы — среднее и медиана по гео, источнику (local+прокси / Dolphin) и итогом. Удалить запись: <code>python delete_metrics.py --ids N</code> (номер в колонке #).</p>
        {table_html}
        {charts_html}
    </div>
    <div id="global-tooltip" class="global-tooltip"></div>
    <script>
        const CHART_POINTS = {chart_points_json};
        const CHART_SOURCE_STYLES = {chart_styles_json};
        const CHART_SOURCE_ORDER = {chart_source_order_json};
        const COMPARE_SOURCES = {compare_sources_json};
        const COMPARE_PERIOD_MS = {compare_period_ms};
        const DELTA_PAIR_MAX_GAP_MS = {delta_pair_gap_ms};

        const tooltip = document.getElementById('global-tooltip');

        function positionTooltip(target) {{
            const rect = target.getBoundingClientRect();
            tooltip.style.visibility = 'hidden';
            tooltip.classList.add('visible');

            const tipRect = tooltip.getBoundingClientRect();
            let left = rect.left + rect.width / 2 - tipRect.width / 2;
            let top = rect.bottom + 10;

            if (top + tipRect.height > window.innerHeight - 8) {{
                top = rect.top - tipRect.height - 10;
            }}

            left = Math.max(8, Math.min(left, window.innerWidth - tipRect.width - 8));
            top = Math.max(8, Math.min(top, window.innerHeight - tipRect.height - 8));

            tooltip.style.left = left + 'px';
            tooltip.style.top = top + 'px';
            tooltip.style.visibility = 'visible';
        }}

        document.querySelectorAll('.th-label[data-tooltip]').forEach((label) => {{
            label.addEventListener('mouseenter', () => {{
                tooltip.textContent = label.dataset.tooltip || '';
                positionTooltip(label);
            }});

            label.addEventListener('mousemove', () => positionTooltip(label));

            label.addEventListener('mouseleave', () => {{
                tooltip.classList.remove('visible');
                tooltip.textContent = '';
            }});
        }});

        (function initTablePagination() {{
            const pagination = document.getElementById('table-pagination');
            const prevBtn = document.getElementById('page-prev');
            const nextBtn = document.getElementById('page-next');
            const pageInfo = document.getElementById('page-info');
            const rows = Array.from(document.querySelectorAll('#metrics-body tr.data-row'));

            if (!pagination || rows.length === 0) {{
                if (pagination) pagination.style.display = 'none';
                return;
            }}

            const rowsPerPage = Number(pagination.dataset.rowsPerPage || 20);
            const totalPages = Math.max(1, Math.ceil(rows.length / rowsPerPage));
            let currentPage = 1;

            function renderPage() {{
                rows.forEach((row, index) => {{
                    const page = Math.floor(index / rowsPerPage) + 1;
                    row.classList.toggle('hidden-row', page !== currentPage);
                }});

                pageInfo.textContent = `Страница ${{currentPage}} из ${{totalPages}} · записей: ${{rows.length}}`;
                prevBtn.disabled = currentPage <= 1;
                nextBtn.disabled = currentPage >= totalPages;
            }}

            prevBtn.addEventListener('click', () => {{
                if (currentPage > 1) {{
                    currentPage -= 1;
                    renderPage();
                }}
            }});

            nextBtn.addEventListener('click', () => {{
                if (currentPage < totalPages) {{
                    currentPage += 1;
                    renderPage();
                }}
            }});

            if (totalPages <= 1) {{
                pagination.style.display = 'none';
            }}

            renderPage();
        }})();

        (function initGeoCharts() {{
            if (!window.Chart || !Array.isArray(CHART_POINTS) || CHART_POINTS.length === 0) {{
                return;
            }}

            const PERIOD_MS = {{
                "24h": 24 * 60 * 60 * 1000,
                "7d": 7 * 24 * 60 * 60 * 1000,
                "30d": 30 * 24 * 60 * 60 * 1000,
            }};

            const METRIC_UNITS = {{
                lcp: "мс",
                ttfb: "мс",
                fcp: "мс",
                load: "мс",
                cls: "",
            }};

            const charts = new Map();

            function median(values) {{
                if (!values.length) return null;
                const sorted = values.slice().sort((a, b) => a - b);
                const mid = Math.floor(sorted.length / 2);
                if (sorted.length % 2) return sorted[mid];
                return (sorted[mid - 1] + sorted[mid]) / 2;
            }}

            function formatMetricValue(metric, value) {{
                if (value === null || value === undefined || Number.isNaN(value)) {{
                    return "нет данных";
                }}
                if (metric === "cls") {{
                    return value.toFixed(3);
                }}
                const unit = METRIC_UNITS[metric] || "";
                return String(Math.round(value)) + (unit ? " " + unit : "");
            }}

            function formatTs(ts) {{
                return new Date(ts).toLocaleString("ru-RU", {{
                    month: "short",
                    day: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                }});
            }}

            function filterPoints(geo, periodMs, metric) {{
                const cutoff = Date.now() - periodMs;
                return CHART_POINTS.filter(
                    (point) => point.geo === geo && point.ts >= cutoff
                ).map((point) => ({{
                    ts: point.ts,
                    source: point.source,
                    value: point[metric],
                    ok: point.ok,
                }}));
            }}

            function buildDatasets(points, metric) {{
                const grouped = new Map();
                points.forEach((point) => {{
                    if (!grouped.has(point.source)) {{
                        grouped.set(point.source, []);
                    }}
                    grouped.get(point.source).push(point);
                }});

                return CHART_SOURCE_ORDER
                    .filter((source) => grouped.has(source))
                    .map((source) => {{
                        const style = CHART_SOURCE_STYLES[source] || {{
                            label: source,
                            color: "#64748b",
                        }};
                        const rows = grouped.get(source).sort((a, b) => a.ts - b.ts);
                        return {{
                            label: style.label,
                            data: rows.map((row) => ({{
                                x: row.ts,
                                y: row.value,
                            }})),
                            borderColor: style.color,
                            backgroundColor: style.color,
                            pointRadius: 4,
                            pointHoverRadius: 6,
                            borderWidth: 2,
                            tension: 0.2,
                            spanGaps: false,
                        }};
                    }});
            }}

            function destroyChart(canvas) {{
                if (canvas && charts.has(canvas)) {{
                    charts.get(canvas).destroy();
                    charts.delete(canvas);
                }}
            }}

            function upsertChart(canvas, config) {{
                if (charts.has(canvas)) {{
                    const chart = charts.get(canvas);
                    chart.config.type = config.type;
                    chart.data = config.data;
                    chart.options = config.options;
                    chart.update();
                    return chart;
                }}
                const chart = new Chart(canvas, config);
                charts.set(canvas, chart);
                return chart;
            }}

            function filterGeoPoints(geo, periodMs) {{
                const cutoff = Date.now() - periodMs;
                return CHART_POINTS.filter(
                    (point) => point.geo === geo && point.ts >= cutoff
                );
            }}

            function collectMetricValues(points, source, metric) {{
                return points
                    .filter(
                        (point) =>
                            point.source === source &&
                            point.ok &&
                            point[metric] !== null &&
                            point[metric] !== undefined
                    )
                    .map((point) => point[metric]);
            }}

            function buildDeltaPoints(geo, periodMs, metric) {{
                const points = filterGeoPoints(geo, periodMs);
                const localRows = points.filter(
                    (point) =>
                        point.source === "local_proxy" &&
                        point.ok &&
                        point[metric] !== null &&
                        point[metric] !== undefined
                );
                const dolphinRows = points.filter(
                    (point) =>
                        point.source === "dolphin_proxy" &&
                        point.ok &&
                        point[metric] !== null &&
                        point[metric] !== undefined
                );

                const deltas = [];
                dolphinRows.forEach((dolphin) => {{
                    let best = null;
                    let bestGap = Infinity;
                    localRows.forEach((local) => {{
                        const gap = Math.abs(local.ts - dolphin.ts);
                        if (gap < bestGap && gap <= DELTA_PAIR_MAX_GAP_MS) {{
                            bestGap = gap;
                            best = local;
                        }}
                    }});
                    if (best) {{
                        deltas.push({{
                            ts: dolphin.ts,
                            delta: best[metric] - dolphin[metric],
                        }});
                    }}
                }});
                return deltas.sort((a, b) => a.ts - b.ts);
            }}

            function renderTimelineChart(card) {{
                const geo = card.dataset.geo;
                const period = card.querySelector(".period-btn.active")?.dataset.period || "24h";
                const metric = card.querySelector(".metric-select")?.value || "lcp";
                const canvas = card.querySelector("canvas.chart-timeline");
                const emptyEl = card.querySelector(".chart-empty-timeline");
                const metaEl = card.querySelector(".chart-meta");
                if (!canvas || !geo) return;

                const periodMs = PERIOD_MS[period] || PERIOD_MS["24h"];
                const points = filterPoints(geo, periodMs, metric);
                const datasets = buildDatasets(points, metric);
                const visibleCount = datasets.reduce((sum, ds) => sum + ds.data.length, 0);

                if (visibleCount === 0) {{
                    emptyEl?.classList.remove("hidden");
                    canvas.style.display = "none";
                    if (metaEl) metaEl.textContent = "Нет замеров HOME за выбранный период.";
                    destroyChart(canvas);
                    return;
                }}

                emptyEl?.classList.add("hidden");
                canvas.style.display = "block";

                const unit = METRIC_UNITS[metric] || "";
                const yTitle = unit
                    ? metric.toUpperCase() + " (" + unit + ")"
                    : metric.toUpperCase();
                const successCount = points.filter(
                    (point) => point.ok && point.value !== null && point.value !== undefined
                ).length;

                if (metaEl) {{
                    metaEl.textContent =
                        "Точек: " + points.length + " · с метрикой: " + successCount + " · период: " + period;
                }}

                upsertChart(canvas, {{
                    type: "line",
                    data: {{ datasets }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {{ mode: "nearest", intersect: false }},
                        plugins: {{
                            legend: {{
                                position: "bottom",
                                labels: {{ boxWidth: 12, boxHeight: 12 }},
                            }},
                            tooltip: {{
                                callbacks: {{
                                    title: (items) => {{
                                        const ts = items[0]?.parsed?.x;
                                        return ts ? formatTs(ts) : "";
                                    }},
                                    label: (item) => {{
                                        const value = item.parsed.y;
                                        return item.dataset.label + ": " + formatMetricValue(metric, value);
                                    }},
                                }},
                            }},
                        }},
                        scales: {{
                            x: {{
                                type: "linear",
                                ticks: {{
                                    maxRotation: 0,
                                    autoSkip: true,
                                    maxTicksLimit: 8,
                                    callback: (value) => formatTs(value),
                                }},
                                title: {{ display: true, text: "Время" }},
                            }},
                            y: {{
                                beginAtZero: metric === "cls",
                                title: {{ display: true, text: yTitle }},
                            }},
                        }},
                    }},
                }});
            }}

            function renderMedianBarChart(card) {{
                const geo = card.dataset.geo;
                const metric = card.querySelector(".metric-select")?.value || "lcp";
                const canvas = card.querySelector("canvas.chart-bar");
                const emptyEl = card.querySelector(".chart-empty-bar");
                if (!canvas || !geo) return;

                const points = filterGeoPoints(geo, COMPARE_PERIOD_MS);
                const labels = [];
                const values = [];
                const colors = [];

                COMPARE_SOURCES.forEach((source) => {{
                    const style = CHART_SOURCE_STYLES[source] || {{
                        label: source,
                        color: "#64748b",
                    }};
                    const med = median(collectMetricValues(points, source, metric));
                    if (med !== null) {{
                        labels.push(style.label);
                        values.push(med);
                        colors.push(style.color);
                    }}
                }});

                if (!values.length) {{
                    emptyEl?.classList.remove("hidden");
                    canvas.style.display = "none";
                    destroyChart(canvas);
                    return;
                }}

                emptyEl?.classList.add("hidden");
                canvas.style.display = "block";

                const unit = METRIC_UNITS[metric] || "";
                const yTitle = unit
                    ? "Медиана " + metric.toUpperCase() + " (" + unit + ")"
                    : "Медиана " + metric.toUpperCase();

                upsertChart(canvas, {{
                    type: "bar",
                    data: {{
                        labels,
                        datasets: [{{
                            label: "Медиана (7 дн)",
                            data: values,
                            backgroundColor: colors,
                            borderColor: colors,
                            borderWidth: 1,
                            borderRadius: 6,
                        }}],
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ display: false }},
                            tooltip: {{
                                callbacks: {{
                                    label: (item) => "Медиана: " + formatMetricValue(metric, item.parsed.y),
                                }},
                            }},
                        }},
                        scales: {{
                            y: {{
                                beginAtZero: metric === "cls",
                                title: {{ display: true, text: yTitle }},
                            }},
                        }},
                    }},
                }});
            }}

            function renderDeltaChart(card) {{
                const geo = card.dataset.geo;
                const metric = card.querySelector(".metric-select")?.value || "lcp";
                const canvas = card.querySelector("canvas.chart-delta");
                const emptyEl = card.querySelector(".chart-empty-delta");
                const compareMeta = card.querySelector(".chart-compare-meta");
                if (!canvas || !geo) return;

                const deltas = buildDeltaPoints(geo, COMPARE_PERIOD_MS, metric);

                if (!deltas.length) {{
                    emptyEl?.classList.remove("hidden");
                    canvas.style.display = "none";
                    if (compareMeta) {{
                        compareMeta.textContent =
                            "Δ: нет пар local+Dolphin в пределах 30 мин за 7 дней.";
                    }}
                    destroyChart(canvas);
                    return;
                }}

                emptyEl?.classList.add("hidden");
                canvas.style.display = "block";

                const unit = METRIC_UNITS[metric] || "";
                const yTitle = unit
                    ? "Δ " + metric.toUpperCase() + " (" + unit + ")"
                    : "Δ " + metric.toUpperCase();
                const avgDelta = deltas.reduce((sum, row) => sum + row.delta, 0) / deltas.length;

                if (compareMeta) {{
                    compareMeta.textContent =
                        "Пар замеров: " + deltas.length +
                        " · средняя Δ: " + formatMetricValue(metric, avgDelta) +
                        " (положительная — local медленнее)";
                }}

                upsertChart(canvas, {{
                    type: "line",
                    data: {{
                        datasets: [{{
                            label: "Δ local − Dolphin",
                            data: deltas.map((row) => ({{ x: row.ts, y: row.delta }})),
                            borderColor: "#ea580c",
                            backgroundColor: "#ea580c",
                            pointRadius: 4,
                            pointHoverRadius: 6,
                            borderWidth: 2,
                            tension: 0.2,
                        }}],
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ position: "bottom" }},
                            tooltip: {{
                                callbacks: {{
                                    title: (items) => {{
                                        const ts = items[0]?.parsed?.x;
                                        return ts ? formatTs(ts) : "";
                                    }},
                                    label: (item) => "Δ: " + formatMetricValue(metric, item.parsed.y),
                                }},
                            }},
                        }},
                        scales: {{
                            x: {{
                                type: "linear",
                                ticks: {{
                                    maxRotation: 0,
                                    autoSkip: true,
                                    maxTicksLimit: 6,
                                    callback: (value) => formatTs(value),
                                }},
                                title: {{ display: true, text: "Время (Dolphin)" }},
                            }},
                            y: {{
                                title: {{ display: true, text: yTitle }},
                            }},
                        }},
                    }},
                }});
            }}

            function renderCardCharts(card) {{
                renderTimelineChart(card);
                renderMedianBarChart(card);
                renderDeltaChart(card);
            }}

            document.querySelectorAll(".chart-card").forEach((card) => {{
                renderCardCharts(card);

                card.querySelectorAll(".period-btn").forEach((btn) => {{
                    btn.addEventListener("click", () => {{
                        card.querySelectorAll(".period-btn").forEach((item) => {{
                            item.classList.toggle("active", item === btn);
                        }});
                        renderTimelineChart(card);
                    }});
                }});

                card.querySelector(".metric-select")?.addEventListener("change", () => {{
                    renderCardCharts(card);
                }});
            }});
        }})();
    </script>
</body>
</html>"""

    with open("reports/report.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("Отчёт создан: reports/report.html")