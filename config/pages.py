GEO_MIRROR_FIRST = {"Russia", "Uzbekistan", "Bangladesh"}


def should_prefer_mirrors(geo: str) -> bool:
    """Для этих гео fastpari.com часто недоступен — сначала локальное зеркало."""
    return geo in GEO_MIRROR_FIRST


PAGES = {
    "HOME": {
        "url": "https://fastpari.com",
        "fallbacks": {
            "Russia": [
                "https://fastpari-5041.pro/ru",
                "https://fastpari-5041.pro/en",
            ],
            "Uzbekistan": [
                "https://fastpari-92371.bar/uz",
                "https://fastpari-92371.bar/en",
            ],
            "Bangladesh": [
                "https://fastpari.com/bn",
                "https://fastpari.com/en",
            ],
            "default": [
                "https://fastpari-5041.pro/en",
            ],
        },
    },
}


def get_page_urls(
    page_name: str,
    geo: str = "",
    *,
    prefer_mirrors: bool = False,
) -> list[str]:
    """Основной URL и зеркала. prefer_mirrors=True — локальное зеркало первым (как в Dolphin)."""
    entry = PAGES[page_name]
    if isinstance(entry, str):
        return [entry]

    primary = entry["url"]
    fallbacks = entry.get("fallbacks", {})
    mirrors = list(fallbacks.get(geo) or fallbacks.get("default") or [])

    if prefer_mirrors and mirrors:
        urls = []
        for mirror in mirrors:
            if mirror not in urls:
                urls.append(mirror)
        if primary not in urls:
            urls.append(primary)
        return urls

    urls = [primary]
    for mirror in mirrors:
        if mirror not in urls:
            urls.append(mirror)
    return urls


def iter_pages() -> list[str]:
    return list(PAGES.keys())