from urllib.parse import urlparse

from core.web_vitals_bundle import WEB_VITALS_IIFE

WEB_VITALS_COLLECTOR = """
window.__webVitalsStore = { lcp: 0, cls: 0, fcp: 0 };

webVitals.onLCP((metric) => {
  window.__webVitalsStore.lcp = metric.value;
}, { reportAllChanges: true });

webVitals.onCLS((metric) => {
  window.__webVitalsStore.cls = metric.value;
}, { reportAllChanges: true });

webVitals.onFCP((metric) => {
  window.__webVitalsStore.fcp = metric.value;
});
"""

LCP_STABLE_MS = 2000
LCP_MAX_WAIT_MS = 12000
VITALS_EVAL_TIMEOUT_MS = LCP_MAX_WAIT_MS + 5000

NAVIGATION_TIMEOUT_MS = 45000
READY_TIMEOUT_MS = 20000


METRICS_INIT_SCRIPT = WEB_VITALS_IIFE + WEB_VITALS_COLLECTOR


def count_http_redirects(response) -> int:
    if not response:
        return 0

    count = 0
    request = response.request
    while request and request.redirected_from:
        count += 1
        request = request.redirected_from
    return count


def _normalize_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url or "")
    path = parsed.path.rstrip("/") or "/"
    return parsed.netloc.lower(), path


def resolve_redirect_count(start_url: str, final_url: str, http_redirects: int) -> int:
    """HTTP-редиректы + клиентский редирект, если финальный URL отличается."""
    if _normalize_url(start_url) != _normalize_url(final_url):
        return max(http_redirects, 1)
    return http_redirects


def wait_for_url_stable(page, stable_ms: int = 2000, timeout: int = 30000):
    page.wait_for_function(
        f"""
        () => new Promise((resolve) => {{
            let lastUrl = location.href;
            let stableFor = 0;
            const step = 250;
            const needStable = {stable_ms};
            const maxWait = {timeout};
            let waited = 0;

            const timer = setInterval(() => {{
                const current = location.href;
                if (current === lastUrl) {{
                    stableFor += step;
                    if (stableFor >= needStable) {{
                        clearInterval(timer);
                        resolve(true);
                    }}
                }} else {{
                    lastUrl = current;
                    stableFor = 0;
                }}

                waited += step;
                if (waited >= maxWait) {{
                    clearInterval(timer);
                    resolve(true);
                }}
            }}, step);
        }})
        """,
        timeout=timeout + 5000,
    )


def wait_for_page_ready(page, *, fast: bool = False):
    """Ждём готовности страницы. fast=True — без networkidle (SPA не простаивают)."""
    stable_ms = 1000 if fast else 2000
    stable_timeout = 12000 if fast else 20000
    wait_for_url_stable(page, stable_ms=stable_ms, timeout=stable_timeout)

    try:
        page.wait_for_load_state("domcontentloaded", timeout=READY_TIMEOUT_MS)
    except Exception:
        pass

    if not fast:
        try:
            page.wait_for_load_state("load", timeout=10000)
        except Exception:
            pass


def capture_web_vitals(
    page,
    *,
    stable_ms: int = LCP_STABLE_MS,
    max_wait_ms: int = LCP_MAX_WAIT_MS,
) -> dict:
    """Ждёт стабилизации LCP через web-vitals (без DOM-эвристик)."""
    page.set_default_timeout(VITALS_EVAL_TIMEOUT_MS)
    try:
        return page.evaluate(
            f"""
        () => new Promise((resolve) => {{
            const store = window.__webVitalsStore || {{ lcp: 0, cls: 0, fcp: 0 }};
            let lastLcp = store.lcp || 0;
            let stableSince = Date.now();
            const start = Date.now();
            const stableMs = {stable_ms};
            const maxWait = {max_wait_ms};

            const finish = () => resolve({{
                lcp: Math.round(store.lcp || 0),
                cls: parseFloat((store.cls || 0).toFixed(3)),
                fcp: Math.round(store.fcp || 0),
            }});

            const check = () => {{
                const lcp = store.lcp || 0;
                if (lcp !== lastLcp) {{
                    lastLcp = lcp;
                    stableSince = Date.now();
                }}

                const elapsed = Date.now() - start;
                const stableFor = Date.now() - stableSince;
                if (elapsed >= maxWait || (lcp > 0 && stableFor >= stableMs)) {{
                    finish();
                    return;
                }}

                setTimeout(check, 200);
            }};

            setTimeout(check, 200);
        }})
        """
        )
    finally:
        page.set_default_timeout(NAVIGATION_TIMEOUT_MS)


def _safe_ms(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _normalize_timing_metrics(metrics: dict) -> dict:
    """SPA иногда даёт отрицательный DCL/Load — нормализуем."""
    fcp = _safe_ms(metrics.get("fcp"))
    lcp = _safe_ms(metrics.get("lcp"))
    dcl = _safe_ms(metrics.get("dom_content_loaded"))
    load = _safe_ms(metrics.get("load"))

    if dcl == 0:
        dcl = fcp
    if load == 0:
        load = max(dcl, lcp, fcp)

    metrics["fcp"] = fcp
    metrics["lcp"] = lcp or fcp
    metrics["dom_content_loaded"] = dcl
    metrics["load"] = load
    metrics["ttfb"] = _safe_ms(metrics.get("ttfb"))
    return metrics


def get_navigation_metrics(page, vitals: dict | None = None):
    metrics = page.evaluate("""
    () => {
        const nav = performance.getEntriesByType('navigation')[0];
        const paints = performance.getEntriesByType('paint');
        const resources = performance.getEntriesByType('resource');

        return {
            url: location.href,
            final_url: location.href,
            redirects: nav ? nav.redirectCount : 0,

            ttfb: nav ? Math.round(nav.responseStart - nav.fetchStart) : 0,
            fcp: Math.round(paints.find(p => p.name === 'first-contentful-paint')?.startTime || 0),
            load: nav ? Math.round(nav.loadEventEnd - nav.fetchStart) : 0,
            dom_content_loaded: nav ? Math.round(nav.domContentLoadedEventEnd - nav.fetchStart) : 0,

            cls: 0,
            total_requests: resources.length,
            total_transfer_size: Math.round(resources.reduce((sum, r) => sum + (r.transferSize || 0), 0) / 1024),

            fetch_start: nav ? Math.round(nav.fetchStart) : 0,
            dom_interactive: nav ? Math.round(nav.domInteractive - nav.fetchStart) : 0
        };
    }
    """)

    if vitals:
        if vitals.get("fcp", 0) > 0:
            metrics["fcp"] = vitals["fcp"]
        if vitals.get("lcp", 0) > 0:
            metrics["lcp"] = vitals["lcp"]
        metrics["cls"] = vitals.get("cls", 0)

    return _normalize_timing_metrics(metrics)