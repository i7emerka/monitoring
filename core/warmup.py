import time

def warmup(page):
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            print(f"Warmup attempt {attempt+1}/{max_attempts}")
            page.goto(
                "https://fastpari.com", 
                wait_until="domcontentloaded",   # ← изменили с "load"
                timeout=45000
            )
            
            # Добавляем CLS observer
            page.evaluate("""
            () => {
                window.__CLS = 0;
                const observer = new PerformanceObserver((list) => {
                    for (const entry of list.getEntries()) {
                        if (!entry.hadRecentInput) {
                            window.__CLS += entry.value;
                        }
                    }
                });
                observer.observe({ type: 'layout-shift', buffered: true });
            }
            """)
            
            print("WARMUP DONE")
            return
            
        except Exception as e:
            print(f"Warmup failed (attempt {attempt+1}): {e}")
            if attempt < max_attempts - 1:
                time.sleep(3)
            else:
                raise