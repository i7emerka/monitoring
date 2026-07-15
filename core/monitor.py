import time

from playwright.sync_api import BrowserContext

from core.browser import create_page
from core.metrics import (
    METRICS_INIT_SCRIPT,
    NAVIGATION_TIMEOUT_MS,
    capture_web_vitals,
    count_http_redirects,
    get_navigation_metrics,
    resolve_redirect_count,
    wait_for_page_ready,
)
from config.pages import get_page_urls, should_prefer_mirrors
from core.csv_writer import save_metric
from core.local_browser import is_session_warmed
from core.warmup import is_navigation_error, prime_page

_OBSERVER_CONTEXT_IDS: set[int] = set()


def _ensure_metrics_observer(context: BrowserContext):
    context_id = id(context)
    if context_id in _OBSERVER_CONTEXT_IDS:
        return
    context.add_init_script(METRICS_INIT_SCRIPT)
    _OBSERVER_CONTEXT_IDS.add(context_id)


def _is_fast_fail_error(exc: Exception) -> bool:
    return is_navigation_error(exc)


def _should_prefer_mirrors(geo: str, source: str) -> bool:
    return should_prefer_mirrors(geo) or source in ("dolphin_proxy", "local_proxy")


def _run_measurement(
    context: BrowserContext,
    start_url: str,
    attempt: int,
    max_attempts: int,
    *,
    skip_prime: bool = False,
):
    prime = None
    measure = None
    try:
        if skip_prime:
            print(f"Замер ({attempt + 1}/{max_attempts}), прогрев сессии уже выполнен")
        else:
            print(f"Шаг 1: прогрев страницы ({attempt + 1}/{max_attempts})")
            print(f"  Стартовый URL: {start_url}")
            prime = create_page(context)
            prime_page(prime, start_url, fast=True)
            prime.close()
            prime = None

        print("Шаг 2: замер метрик в новой вкладке")
        measure = create_page(context)
        response = measure.goto(
            start_url,
            wait_until="domcontentloaded",
            timeout=NAVIGATION_TIMEOUT_MS,
        )

        if response:
            print(f"Status: {response.status}")

        print("Ожидание стабилизации страницы...")
        wait_for_page_ready(measure, fast=True)

        print("Ожидание финального LCP (web-vitals)...")
        vitals = capture_web_vitals(measure)
        metrics = get_navigation_metrics(measure, vitals=vitals)

        http_redirects = count_http_redirects(response)
        metrics["redirects"] = resolve_redirect_count(
            start_url, metrics.get("final_url", ""), http_redirects
        )
        if http_redirects != metrics["redirects"]:
            print(f"Редирект: HTTP={http_redirects}, итого={metrics['redirects']} (клиентский)")
        else:
            print(f"Редиректы: {metrics['redirects']}")

        print(f"Final URL: {metrics.get('final_url')}")
        print(
            f"TTFB: {metrics.get('ttfb')} ms | FCP: {metrics.get('fcp')} ms "
            f"| LCP: {metrics.get('lcp')} ms"
        )
        print(f"Load: {metrics.get('load')} ms | CLS: {metrics.get('cls')}")
        return metrics, None
    except Exception as exc:
        return None, exc
    finally:
        for page in (prime, measure):
            if page:
                try:
                    page.close()
                except Exception:
                    pass


def monitor_page(
    context: BrowserContext,
    geo: str,
    page_name: str,
    url: str | None = None,
    source: str = "",
    urls: list[str] | None = None,
):
    source_label = f" | {source}" if source else ""
    print(f"\n========== {page_name} | GEO: {geo}{source_label} ==========")

    _ensure_metrics_observer(context)
    prefer_mirrors = _should_prefer_mirrors(geo, source)
    candidates = urls or (
        [url] if url else get_page_urls(page_name, geo, prefer_mirrors=prefer_mirrors)
    )
    primary_url = get_page_urls(page_name, geo, prefer_mirrors=False)[0]

    if prefer_mirrors and candidates:
        print(f"Сначала зеркало: {candidates[0]}")

    last_error = None

    for start_url in candidates:
        if start_url != candidates[0]:
            print(f"Пробуем следующий URL: {start_url}")

        max_attempts = 1 if _is_fast_fail_error(last_error) else 2
        skip_prime = is_session_warmed(context)
        for attempt in range(max_attempts):
            metrics, error = _run_measurement(
                context,
                start_url,
                attempt,
                max_attempts,
                skip_prime=skip_prime and attempt == 0,
            )
            if metrics is not None:
                if start_url != primary_url:
                    print(f"Загружено через зеркало: {start_url}")
                save_metric(geo=geo, page=page_name, metrics=metrics, source=source)
                return metrics

            last_error = error
            print(f"Попытка {attempt + 1} не удалась: {error}")
            if _is_fast_fail_error(error):
                print("  Быстрый отказ — переходим к следующему URL.")
                break
            if attempt < max_attempts - 1:
                time.sleep(3)

        if start_url != candidates[-1]:
            print(f"  {start_url} не удался, пробуем следующий адрес...")
            continue

    print(f"Не удалось загрузить {page_name}")
    save_metric(
        geo=geo,
        page=page_name,
        metrics={"error": str(last_error)},
        source=source,
    )
    return {"error": str(last_error)}