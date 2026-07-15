from core.metrics import NAVIGATION_TIMEOUT_MS, wait_for_page_ready


def is_navigation_error(exc: Exception) -> bool:
    """Сетевые/навигационные ошибки (не баги в коде)."""
    err = str(exc).lower()
    if any(
        marker in err
        for marker in (
            "unexpected keyword argument",
            "syntaxerror",
            "typeerror",
            "referenceerror",
        )
    ):
        return False
    return any(
        marker in err
        for marker in (
            "err_connection_closed",
            "err_connection_reset",
            "err_name_not_resolved",
            "err_tunnel_connection_failed",
            "err_proxy_connection_failed",
            "err_timed_out",
            "timed out",
            "ms exceeded",
            "net::err_",
        )
    )


def _is_fast_fail_error(exc: Exception) -> bool:
    return is_navigation_error(exc)


def prime_first_available(page, urls: list[str], *, fast: bool = True) -> str:
    """Пробует URL по очереди, возвращает успешный."""
    last_error = None
    for index, url in enumerate(urls):
        if index > 0:
            print(f"  Пробуем следующий URL для прогрева: {url}")
        try:
            prime_page(page, url, fast=fast)
            return url
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("Список URL для прогрева пуст")


def prime_page(page, url: str, *, fast: bool = True):
    """Прогрев страницы. fast=True — domcontentloaded, без долгого ожидания load."""
    max_attempts = 2 if fast else 3
    for attempt in range(max_attempts):
        try:
            print(f"  Prime attempt {attempt + 1}/{max_attempts}: {url}")
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT_MS,
            )
            wait_for_page_ready(page, fast=fast)
            print(f"  Prime DONE: {page.url}")
            return
        except Exception as e:
            print(f"  Prime failed (attempt {attempt + 1}): {e}")
            if _is_fast_fail_error(e):
                raise
            if attempt < max_attempts - 1:
                page.wait_for_timeout(2000)
            else:
                raise