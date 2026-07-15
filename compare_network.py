import argparse
import sys

from config.pages import PAGES, iter_pages
from config.profiles import PROFILES
from core.compare_runner import (
    print_comparison,
    run_dolphin_test,
    run_full_compare,
    run_local_proxy_test,
    run_local_test,
)


def _select_pages(page_filter: str | None) -> list[str]:
    if not page_filter:
        return iter_pages()
    names = [name.strip().upper() for name in page_filter.split(",") if name.strip()]
    unknown = [name for name in names if name not in PAGES]
    if unknown:
        raise ValueError(f"Неизвестные страницы: {', '.join(unknown)}")
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Сравнение: локальный IP / локальный+прокси / Dolphin"
    )
    parser.add_argument("--profile", default="RU", help="Профиль (по умолчанию RU)")
    parser.add_argument("--pages", help="Страницы через запятую (HOME)")
    parser.add_argument("--full", action="store_true", help="Все 3 источника (по умолчанию для RU)")
    parser.add_argument("--local-only", action="store_true", help="Только локальный IP")
    parser.add_argument("--local-proxy-only", action="store_true", help="Только локальный + прокси")
    parser.add_argument("--dolphin-only", action="store_true", help="Только Dolphin")
    parser.add_argument("--headed", action="store_true", help="Показать окно локального браузера")
    args = parser.parse_args(argv)

    modes = sum([
        args.local_only,
        args.local_proxy_only,
        args.dolphin_only,
        args.full,
    ])
    if modes > 1:
        print("Выберите только один режим")
        return 1

    pages = _select_pages(args.pages)
    profile = args.profile.upper()

    if args.full or (not args.local_only and not args.local_proxy_only and not args.dolphin_only):
        run_full_compare(
            profile,
            pages,
            headless=not args.headed,
            include_local_ip=(profile == "RU"),
        )
    else:
        results = {}
        if args.local_only:
            results["local_ip"] = run_local_test(
                PROFILES[profile]["geo"], pages, headless=not args.headed
            )
        if args.local_proxy_only:
            results["local_proxy"] = run_local_proxy_test(
                profile, pages, headless=not args.headed
            )
        if args.dolphin_only:
            results["dolphin_proxy"] = run_dolphin_test(profile, pages)
        print_comparison(results)

    print("\nРезультаты в reports/metrics.csv (колонка source).")
    return 0


if __name__ == "__main__":
    sys.exit(main())