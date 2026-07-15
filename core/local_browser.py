from pathlib import Path

from playwright.sync_api import BrowserContext, Playwright, sync_playwright

from config.pages import get_page_urls, should_prefer_mirrors
from core.browser import create_page
from core.warmup import prime_first_available

PROFILE_DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "playwright_profiles"
_WARMED_CONTEXT_IDS: set[int] = set()


def mark_session_warmed(context: BrowserContext) -> None:
    _WARMED_CONTEXT_IDS.add(id(context))


def is_session_warmed(context: BrowserContext) -> bool:
    return id(context) in _WARMED_CONTEXT_IDS


def clear_session_warmed(context: BrowserContext) -> None:
    _WARMED_CONTEXT_IDS.discard(id(context))


def _profile_data_dir(profile_key: str) -> Path:
    path = PROFILE_DATA_ROOT / profile_key
    path.mkdir(parents=True, exist_ok=True)
    return path


def launch_local_browser(
    headless: bool = True,
    proxy: dict | None = None,
    *,
    profile_key: str = "default",
    persistent: bool = True,
) -> tuple[Playwright, BrowserContext]:
    """Chromium на вашем ПК. persistent=True — кэш и cookies между запусками."""
    pw = sync_playwright().start()

    if persistent:
        launch_kwargs: dict = {
            "headless": headless,
            "viewport": {"width": 1920, "height": 1080},
        }
        if proxy:
            launch_kwargs["proxy"] = proxy
        context = pw.chromium.launch_persistent_context(
            str(_profile_data_dir(profile_key)),
            **launch_kwargs,
        )
        return pw, context

    browser = pw.chromium.launch(headless=headless)
    context = browser.new_context(
        proxy=proxy,
        viewport={"width": 1920, "height": 1080},
    )
    return pw, context


def warmup_browser_session(
    context: BrowserContext,
    geo: str,
    *,
    source: str = "",
) -> None:
    """Один визит на сайт до замеров — DNS, TLS, cookies, кэш (как прогретый Dolphin)."""
    prefer_mirrors = should_prefer_mirrors(geo) or source in (
        "local_proxy",
        "dolphin_proxy",
    )
    candidates = get_page_urls("HOME", geo, prefer_mirrors=prefer_mirrors)
    print(f"\nПрогрев сессии браузера (кандидаты: {len(candidates)})")
    page = create_page(context)
    try:
        warmup_url = prime_first_available(page, candidates, fast=True)
        print(f"  Прогрев OK: {warmup_url}")
        mark_session_warmed(context)
    except Exception as exc:
        print(f"  Прогрев пропущен: {exc}")
    finally:
        page.close()


def close_local_browser(pw: Playwright | None, context: BrowserContext | None) -> None:
    try:
        if context:
            clear_session_warmed(context)
            context.close()
        if pw:
            pw.stop()
    except Exception:
        pass