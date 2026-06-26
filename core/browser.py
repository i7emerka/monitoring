from playwright.sync_api import sync_playwright, Browser, BrowserContext

def connect_to_browser(ws_url: str):
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(ws_url)
    return pw, browser


def get_or_create_context(browser: Browser) -> BrowserContext:
    if browser.contexts:
        return browser.contexts[0]
    return browser.new_context()


def create_page(context: BrowserContext):
    page = context.new_page()
    page.set_viewport_size({"width": 1920, "height": 1080})
    return page


def close_all_pages(context: BrowserContext):
    """Закрывает все открытые страницы в контексте"""
    for p in context.pages:
        try:
            p.close()
        except:
            pass