def get_navigation_metrics(page):
    return page.evaluate("""
    () => {
        const nav = performance.getEntriesByType('navigation')[0];
        const fetchStart = nav.fetchStart;
        
        return {
            url: location.href,
            final_url: location.href,
            redirects: nav.redirectCount,
            fetch_start: Math.round(fetchStart),
            ttfb: Math.round(nav.responseStart - fetchStart),           // ← правильный TTFB
            dom_interactive: Math.round(nav.domInteractive - fetchStart),
            dom_content_loaded: Math.round(nav.domContentLoadedEventEnd - fetchStart),
            load: Math.round(nav.loadEventEnd - fetchStart),
            total_time: Math.round(nav.loadEventEnd - fetchStart),
            transfer_size: nav.transferSize || 0,
            encoded_body_size: nav.encodedBodySize || 0,
            decoded_body_size: nav.decodedBodySize || 0
        };
    }
    """)