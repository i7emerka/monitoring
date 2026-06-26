from core.metrics import get_navigation_metrics
from core.csv_writer import save_metric

def monitor_page(page, geo, page_name, url):
    print(f"\n========== {page_name} | GEO: {geo} ==========")
    
    try:
        response = page.goto(
            url,
            wait_until="load",
            timeout=60000
        )
        
        if response:
            print(f"Status: {response.status}")
        
        metrics = get_navigation_metrics(page)
        
        print(f"Final URL: {metrics.get('final_url')}")
        print(f"TTFB: {metrics.get('ttfb')} ms")
        print(f"DOM Loaded: {metrics.get('dom_content_loaded')} ms")
        print(f"Full Load: {metrics.get('load')} ms")
        
        save_metric(geo=geo, page=page_name, metrics=metrics)
        
    except Exception as e:
        print(f"❌ Ошибка при мониторинге {page_name}: {e}")
        save_metric(geo=geo, page=page_name, metrics={"error": str(e)})