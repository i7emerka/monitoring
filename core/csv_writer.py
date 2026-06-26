import csv
import os
from datetime import datetime

CSV_FILE = "reports/metrics.csv"

def save_metric(geo: str, page: str, metrics: dict):
    file_exists = os.path.exists(CSV_FILE)

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "datetime", "geo", "page", "url", "final_url",
                "redirects", "ttfb", "dom_content_loaded", "load", "error"
            ])

        row = [
            datetime.now().isoformat(),           # ISO формат — надёжный
            geo,
            page,
            metrics.get("url", metrics.get("final_url", "")),
            metrics.get("final_url", ""),
            int(metrics.get("redirects", 0)),
            int(metrics.get("ttfb", 0)),
            int(metrics.get("dom_content_loaded", 0)),
            int(metrics.get("load", 0)),
            str(metrics.get("error", ""))
        ]
        writer.writerow(row)