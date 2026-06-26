from playwright.sync_api import sync_playwright

WS_URL = "ws://127.0.0.1:58741/devtools/browser/3fd23ebc-eb79-42bd-88c4-304a4a5f4737"

with sync_playwright() as p:

    browser = p.chromium.connect_over_cdp(
        WS_URL
    )

    context = browser.contexts[0]

    page = context.new_page()

    requests_count = {"value": 0}

    def count_requests(request):
        requests_count["value"] += 1

    page.on("request", count_requests)

    page.goto(
        "about:blank"
    )

    page.goto(
        "https://fastpari.com/ru",
        wait_until="load",
        timeout=60000
    )

    metrics = page.evaluate("""
    () => {
        const nav = performance.getEntriesByType('navigation')[0];

        return {
            url: location.href,
            ttfb: Math.round(nav.responseStart),
            dom_content_loaded:
                Math.round(nav.domContentLoadedEventEnd),
            load:
                Math.round(nav.loadEventEnd),
            transfer_size:
                nav.transferSize,
            encoded_body_size:
                nav.encodedBodySize,
            decoded_body_size:
                nav.decodedBodySize,
            redirects:
                nav.redirectCount
        };
    }
    """)

    print("\n=== RESULT ===")
    print("Requests:", requests_count["value"])
    print("Title:", page.title())
    print("URL:", page.url)
    print("Metrics:")
    print(metrics)

    input("\nPress Enter...")