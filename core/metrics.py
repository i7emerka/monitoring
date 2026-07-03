def get_navigation_metrics(page):
    return page.evaluate("""
    () => {
        const nav = performance.getEntriesByType('navigation')[0];
        const paints = performance.getEntriesByType('paint');
        const resources = performance.getEntriesByType('resource');
        
        // LCP
        let lcp = 0;
        try {
            const lcpEntry = performance.getEntriesByType('largest-contentful-paint')[0];
            lcp = lcpEntry ? Math.round(lcpEntry.startTime) : 0;
        } catch(e) {}
        
        // CLS (упрощённо)
        let cls = 0;
        try {
            if (window.__CLS) cls = window.__CLS;
        } catch(e) {}
        
        return {
            url: location.href,
            final_url: location.href,
            redirects: nav.redirectCount,
            
            // Основные
            ttfb: Math.round(nav.responseStart - nav.fetchStart),
            fcp: Math.round(paints.find(p => p.name === 'first-contentful-paint')?.startTime || 0),
            lcp: lcp,
            load: Math.round(nav.loadEventEnd - nav.fetchStart),
            dom_content_loaded: Math.round(nav.domContentLoadedEventEnd - nav.fetchStart),
            
            // Дополнительные
            cls: parseFloat(cls.toFixed(3)),
            total_requests: resources.length,
            total_transfer_size: Math.round(resources.reduce((sum, r) => sum + (r.transferSize || 0), 0) / 1024), // в KB
            
            fetch_start: Math.round(nav.fetchStart),
            dom_interactive: Math.round(nav.domInteractive - nav.fetchStart)
        };
    }
    """)