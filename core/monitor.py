from core.metrics import get_navigation_metrics
from core.csv_writer import save_metric

import time

def monitor_page(page, geo, page_name, url):
    print(f"\n========== {page_name} | GEO: {geo} ==========")
    
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )
            
            if response:
                print(f"Status: {response.status}")
            
            metrics = get_navigation_metrics(page)
            
            print(f"Final URL: {metrics.get('final_url')}")
            print(f"TTFB: {metrics.get('ttfb')} ms | LCP: {metrics.get('lcp')} ms")
            print(f"Load: {metrics.get('load')} ms | CLS: {metrics.get('cls')}")
            
            save_metric(geo=geo, page=page_name, metrics=metrics)
            return
            
        except Exception as e:
            print(f"Попытка {attempt+1} не удалась: {e}")
            if attempt < max_attempts - 1:
                time.sleep(5)
                page.reload(timeout=30000)
            else:
                print(f"❌ Не удалось загрузить {page_name}")
                save_metric(geo=geo, page=page_name, metrics={"error": str(e)})