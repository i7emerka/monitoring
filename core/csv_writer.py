import csv
import os
from datetime import datetime

CSV_FILE = "reports/metrics.csv"


def save_metric(geo: str, page: str, metrics: dict):
    """Сохраняет метрики в CSV"""
    file_exists = os.path.exists(CSV_FILE)

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "datetime", "geo", "page", "final_url",
                "ttfb", "fcp", "lcp", "dom_content_loaded", "load",
                "cls", "total_requests", "total_transfer_size_kb",
                "redirects", "error"
            ])

        row = [
            datetime.now().isoformat(),
            geo,
            page,
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
            str(metrics.get("error", ""))
        ]
        writer.writerow(row)