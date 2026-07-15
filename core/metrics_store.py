import csv
import os
from datetime import datetime

import pandas as pd

CSV_FILE = "reports/metrics.csv"

CSV_COLUMNS = [
    "datetime", "geo", "page", "source", "final_url",
    "ttfb", "fcp", "lcp", "dom_content_loaded", "load",
    "cls", "total_requests", "total_transfer_size_kb",
    "redirects", "error",
]


def parse_datetime_series(series: pd.Series) -> pd.Series:
    """Парсит смешанные форматы дат из CSV (ISO и '%Y-%m-%d %H:%M:%S')."""
    parsed = pd.to_datetime(series, format="mixed", utc=True, errors="coerce")
    missing = parsed.isna()
    if missing.any():
        normalized = (
            series[missing]
            .astype(str)
            .str.replace("T", " ", regex=False)
            .str.split(".", n=1)
            .str[0]
        )
        parsed.loc[missing] = pd.to_datetime(normalized, utc=True, errors="coerce")
    return parsed


OLD_CSV_COLUMNS = [col for col in CSV_COLUMNS if col != "source"]


def _looks_like_url(value: str) -> bool:
    text = (value or "").strip().lower()
    return text.startswith("http://") or text.startswith("https://")


def _normalize_data_row(row: list[str]) -> list[str]:
    if len(row) == len(CSV_COLUMNS):
        return row

    if len(row) == len(OLD_CSV_COLUMNS):
        return row[:3] + [""] + row[3:]

    if len(row) > len(CSV_COLUMNS):
        fixed = row[: len(CSV_COLUMNS) - 1]
        fixed.append(" | ".join(row[len(CSV_COLUMNS) - 1 :]))
        return fixed

    padded = row + [""] * (len(CSV_COLUMNS) - len(row))
    return padded[: len(CSV_COLUMNS)]


def repair_csv() -> bool:
    """Приводит CSV к единому формату с колонкой source."""
    if not os.path.exists(CSV_FILE):
        return False

    with open(CSV_FILE, newline="", encoding="utf-8") as file:
        rows = list(csv.reader(file))

    if not rows:
        return False

    header = rows[0]
    if header == CSV_COLUMNS:
        return False

    normalized_rows = [CSV_COLUMNS]
    for row in rows[1:]:
        if not row:
            continue

        if len(row) == len(OLD_CSV_COLUMNS) and _looks_like_url(row[3]):
            normalized_rows.append(row[:3] + [""] + row[3:])
            continue

        if len(row) == len(CSV_COLUMNS):
            normalized_rows.append(row)
            continue

        normalized_rows.append(_normalize_data_row(row))

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerows(normalized_rows)

    return True


def _read_raw() -> pd.DataFrame:
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame(columns=CSV_COLUMNS)

    repair_csv()
    df = pd.read_csv(CSV_FILE)
    for col in CSV_COLUMNS:
        if col not in df.columns:
            df[col] = "" if col in ("final_url", "error", "source") else 0
    df = df[CSV_COLUMNS]
    df["_row_id"] = range(len(df))
    return df


def _write_raw(df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
    out = df.drop(columns=["_row_id", "row_id"], errors="ignore")
    out = out[CSV_COLUMNS]
    out.to_csv(CSV_FILE, index=False, encoding="utf-8")


def load_metrics() -> pd.DataFrame:
    """Загружает метрики: новые сверху, с колонкой row_id для удаления."""
    df = _read_raw()
    if df.empty:
        return df

    df["datetime"] = parse_datetime_series(df["datetime"])
    df = df.sort_values(by="datetime", ascending=False, na_position="last")
    df["row_id"] = range(1, len(df) + 1)
    return df


def format_metric_row(row: pd.Series) -> str:
    dt = row["datetime"]
    if hasattr(dt, "strftime"):
        dt_text = dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        dt_text = str(row.get("datetime", "—"))

    error = str(row.get("error", "") or "").strip()
    error_mark = " [ОШИБКА]" if error and error.lower() != "nan" else ""
    return (
        f"#{int(row['row_id'])} | {dt_text} | {row['geo']} | {row['page']}"
        f" | TTFB={row.get('ttfb', '—')} | LCP={row.get('lcp', '—')}{error_mark}"
    )


def list_metrics() -> pd.DataFrame:
    return load_metrics()


def filter_metrics(
    df: pd.DataFrame,
    *,
    geo: str | None = None,
    page: str | None = None,
    before: str | None = None,
    after: str | None = None,
    errors_only: bool = False,
) -> pd.DataFrame:
    filtered = df.copy()

    if geo:
        filtered = filtered[filtered["geo"].astype(str).str.lower() == geo.lower()]

    if page:
        filtered = filtered[filtered["page"].astype(str).str.upper() == page.upper()]

    if before:
        cutoff = pd.to_datetime(before, utc=True, errors="coerce")
        if pd.isna(cutoff):
            raise ValueError(f"Некорректная дата --before: {before}")
        filtered = filtered[filtered["datetime"] < cutoff]

    if after:
        cutoff = pd.to_datetime(after, utc=True, errors="coerce")
        if pd.isna(cutoff):
            raise ValueError(f"Некорректная дата --after: {after}")
        filtered = filtered[filtered["datetime"] > cutoff]

    if errors_only:
        errors = filtered["error"].fillna("").astype(str).str.strip()
        filtered = filtered[(errors != "") & (errors.str.lower() != "nan")]

    return filtered


def delete_metrics(
    *,
    display_ids: list[int] | None = None,
    geo: str | None = None,
    page: str | None = None,
    before: str | None = None,
    after: str | None = None,
    errors_only: bool = False,
) -> list[pd.Series]:
    if not os.path.exists(CSV_FILE):
        raise FileNotFoundError("CSV файл не найден")

    display_df = load_metrics()
    if display_df.empty:
        return []

    if display_ids:
        available = set(display_df["row_id"].astype(int))
        missing = sorted(set(display_ids) - available)
        if missing:
            raise ValueError(
                f"Неизвестные номера записей: {', '.join(map(str, missing))}"
            )
        targets = display_df[display_df["row_id"].isin(display_ids)]
    else:
        if not any([geo, page, before, after, errors_only]):
            raise ValueError("Укажите номера записей или фильтры для удаления")
        targets = filter_metrics(
            display_df,
            geo=geo,
            page=page,
            before=before,
            after=after,
            errors_only=errors_only,
        )

    if targets.empty:
        return []

    row_ids = targets["_row_id"].tolist()
    raw = _read_raw()
    raw = raw[~raw["_row_id"].isin(row_ids)]
    _write_raw(raw)
    return [row for _, row in targets.iterrows()]