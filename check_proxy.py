"""Быстрая проверка: прокси профиля Dolphin работает и открывает fastpari."""
import argparse
import sys
import time

from config.pages import get_page_urls
from config.profiles import PROFILES
from core.browser import connect_to_browser, get_or_create_context
from core.dolphin import start_profile, stop_profile


def check_profile(profile_key: str) -> int:
    if profile_key not in PROFILES:
        print(f"Профиль {profile_key} не найден")
        return 1

    profile = PROFILES[profile_key]
    profile_id = profile["profile_id"]
    print(f"Проверка {profile_key} ({profile['geo']}), id={profile_id}")

    pw = None
    browser = None
    try:
        automation = start_profile(profile_id)
        pw, browser = connect_to_browser(f"http://127.0.0.1:{automation['port']}")
        page = get_or_create_context(browser).new_page()

        page.goto("https://api.ipify.org?format=json", wait_until="domcontentloaded", timeout=30000)
        print("IP прокси:", page.inner_text("body"))

        urls = get_page_urls("HOME", profile["geo"])
        for index, check_url in enumerate(urls):
            label = "fastpari.com" if index == 0 else f"зеркало #{index}"
            test_page = get_or_create_context(browser).new_page()
            try:
                resp = test_page.goto(check_url, wait_until="load", timeout=60000)
                print(f"{label}: OK, status={resp.status if resp else '?'}, url={test_page.url}")
                return 0
            except Exception as exc:
                print(f"{label} ({check_url}): ОШИБКА — {exc}")
            finally:
                test_page.close()

        print(
            "Прокси живой, но fastpari.com и зеркала недоступны. "
            "Проверьте прокси в Dolphin или добавьте зеркало в config/pages.py"
        )
        return 2
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()
        stop_profile(profile_id)
        time.sleep(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка прокси профиля Dolphin")
    parser.add_argument("--profile", default="RU", help="Ключ профиля (RU, UZ, BD)")
    args = parser.parse_args()
    return check_profile(args.profile.upper())


if __name__ == "__main__":
    sys.exit(main())