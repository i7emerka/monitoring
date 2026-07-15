from config.pages import iter_pages
from config.profiles import PROFILES, get_profile_proxy
from core.browser import close_all_pages, connect_to_browser, get_or_create_context
from core.dolphin import start_profile, stop_profile
from core.local_browser import (
    close_local_browser,
    launch_local_browser,
    warmup_browser_session,
)
from core.monitor import monitor_page

COMPARE_METRICS = ("ttfb", "fcp", "lcp", "dom_content_loaded", "load", "cls")

SOURCE_TITLES = {
    "local_ip": "Локальный IP",
    "local_proxy": "Локальный + прокси",
    "dolphin_proxy": "Dolphin + прокси",
}


def run_local_test(
    geo: str,
    pages: list[str] | None = None,
    *,
    headless: bool = True,
) -> dict[str, dict]:
    pages = pages or iter_pages()
    print(f"\n=== Локальный браузер: ваш ПК, ваш IP ({geo}) ===")

    pw = None
    context = None
    results: dict[str, dict] = {}

    try:
        pw, context = launch_local_browser(headless=headless, profile_key="local_ip")
        warmup_browser_session(context, geo, source="local_ip")
        for page_name in pages:
            metrics = monitor_page(
                context,
                geo=geo,
                page_name=page_name,
                source="local_ip",
            )
            results[page_name] = metrics or {}
        return results
    finally:
        close_local_browser(pw, context)


def run_local_proxy_test(
    profile_key: str,
    pages: list[str] | None = None,
    *,
    headless: bool = True,
) -> dict[str, dict]:
    profile = PROFILES[profile_key]
    proxy = get_profile_proxy(profile_key)
    if not proxy:
        raise ValueError(
            f"Прокси для {profile_key} не задан. "
            f"Добавьте {profile_key.upper()}_PROXY_SERVER в .env"
        )

    pages = pages or iter_pages()
    print(f"\n=== Локальный браузер + прокси ({profile['geo']}) ===")
    print(f"  Прокси: {proxy['server']}")
    if proxy.get("username"):
        print(f"  Логин: {proxy['username'][:20]}...")

    pw = None
    context = None
    results: dict[str, dict] = {}

    try:
        pw, context = launch_local_browser(
            headless=headless,
            proxy=proxy,
            profile_key=profile_key,
        )
        warmup_browser_session(context, profile["geo"], source="local_proxy")
        for page_name in pages:
            metrics = monitor_page(
                context,
                geo=profile["geo"],
                page_name=page_name,
                source="local_proxy",
            )
            results[page_name] = metrics or {}
        return results
    finally:
        close_local_browser(pw, context)


def run_dolphin_profile(profile_key: str, pages: list[str] | None = None) -> None:
    """Запуск Dolphin для профиля (без возврата результатов в dict)."""
    run_dolphin_test(profile_key, pages)


def run_dolphin_test(
    profile_key: str,
    pages: list[str] | None = None,
) -> dict[str, dict]:
    profile = PROFILES[profile_key]
    profile_id = profile["profile_id"]
    if not profile_id:
        raise ValueError(f"Для профиля {profile_key} не задан profile_id")

    pages = pages or iter_pages()
    print(f"\n=== Dolphin Anty: прокси {profile['geo']} ===")

    pw = None
    browser = None
    context = None
    results: dict[str, dict] = {}

    try:
        automation = start_profile(profile_id)
        cdp_url = f"http://127.0.0.1:{automation['port']}"
        pw, browser = connect_to_browser(cdp_url)
        context = get_or_create_context(browser)

        for page_name in pages:
            metrics = monitor_page(
                context,
                geo=profile["geo"],
                page_name=page_name,
                source="dolphin_proxy",
            )
            results[page_name] = metrics or {}
        return results
    finally:
        try:
            if context:
                close_all_pages(context)
            if browser:
                browser.close()
            if pw:
                pw.stop()
        except Exception:
            pass
        stop_profile(profile_id)


def _metric_value(metrics: dict, key: str):
    if not metrics or metrics.get("error"):
        return None
    value = metrics.get(key)
    if value is None:
        return None
    return float(value)


def print_comparison(
    results_by_source: dict[str, dict[str, dict]],
    *,
    baseline_source: str = "local_ip",
) -> None:
    active_sources = [key for key, data in results_by_source.items() if data]
    if not active_sources:
        return

    print("\n" + "=" * 72)
    print("СРАВНЕНИЕ ИСТОЧНИКОВ ЗАМЕРА")
    print("=" * 72)

    pages = sorted(
        {page for source in active_sources for page in results_by_source[source]}
    )

    for page_name in pages:
        print(f"\n--- {page_name} ---")
        header = f"  {'Метрика':<8}"
        for source in active_sources:
            header += f" {SOURCE_TITLES.get(source, source):>18}"
        if baseline_source in active_sources:
            delta_label = (
                "Δ vs IP" if baseline_source == "local_ip" else "Δ vs proxy"
            )
            header += f" {delta_label:>10}"
        print(header)
        print(f"  {'-'*8}" + f" {'-'*18}" * len(active_sources) + (
            f" {'-'*10}" if baseline_source in active_sources else ""
        ))

        for metric in COMPARE_METRICS:
            row = f"  {metric.upper():<8}"
            values = {}
            for source in active_sources:
                values[source] = _metric_value(
                    results_by_source[source].get(page_name, {}),
                    metric,
                )
                val = values[source]
                text = "—" if val is None else (
                    f"{val:.3f}" if metric == "cls" else str(int(val))
                )
                row += f" {text:>18}"

            if baseline_source in active_sources:
                base = values.get(baseline_source)
                compare_source = active_sources[-1]
                other = values.get(compare_source)
                if base is not None and other is not None and compare_source != baseline_source:
                    delta = other - base
                    delta_text = (
                        f"{delta:+.3f}" if metric == "cls" else f"{int(round(delta)):+.0f}"
                    )
                else:
                    delta_text = "—"
                row += f" {delta_text:>10}"

            print(row)

        for source in active_sources:
            final_url = results_by_source[source].get(page_name, {}).get("final_url", "—")
            print(f"  URL {SOURCE_TITLES.get(source, source)}: {final_url}")


def run_full_compare(
    profile_key: str,
    pages: list[str] | None = None,
    *,
    include_local_ip: bool = True,
    include_dolphin: bool = True,
    headless: bool = True,
) -> dict[str, dict[str, dict]]:
    geo = PROFILES[profile_key]["geo"]
    results: dict[str, dict[str, dict]] = {}

    if include_local_ip:
        results["local_ip"] = run_local_test(geo, pages, headless=headless)

    try:
        results["local_proxy"] = run_local_proxy_test(
            profile_key, pages, headless=headless
        )
    except ValueError as exc:
        print(f"\nЛокальный прокси пропущен: {exc}")

    if include_dolphin:
        try:
            results["dolphin_proxy"] = run_dolphin_test(profile_key, pages)
        except Exception as exc:
            print(f"\nDolphin пропущен: {exc}")

    baseline = (
        "local_ip"
        if include_local_ip and results.get("local_ip")
        else "local_proxy"
    )
    print_comparison(results, baseline_source=baseline)
    return results