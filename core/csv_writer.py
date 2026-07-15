import csv
import os
from datetime import datetime

from core.metrics_store import CSV_COLUMNS, CSV_FILE, repair_csv


def _sanitize_error(value) -> str:
    return str(value or "").replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()


def save_metric(geo: str, page: str, metrics: dict, source: str = ""):
    """Сохраняет метрики в CSV"""
    if os.path.exists(CSV_FILE):
        repair_csv()

    file_exists = os.path.exists(CSV_FILE)

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, quoting=csv.QUOTE_MINIMAL)

        if not file_exists:
            writer.writerow(CSV_COLUMNS)

        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            geo,
            page,
            source,
            metrics.get("final_url", ""),
            int(metrics.get("ttfb", 0)),
            int(metrics.get("fcp", 0)),
            int(metrics.get("lcp", 0)),
            int(metrics.get("dom_content_loaded", 0)),
            int(metrics.get("load", 0)),
            float(metrics.get("cls", 0)),
            int(metrics.get("total_requests", 0)),
            int(metrics.get("total_transfer_size", 0)),
            int(metrics.get("redirects", 0)),
            _sanitize_error(metrics.get("error", "")),
        ]
        writer.writerow(row)