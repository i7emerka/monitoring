import argparse
import sys

from config.profiles import PROFILES, get_profile_proxy

from core.compare_runner import run_dolphin_profile, run_full_compare, run_local_proxy_test
from core.html_report import generate_html_report
from core.publish_report import publish_report

COMPARE_PROFILES = {"UZ", "BD", "RU"}


def run_for_profile(profile_key: str, *, use_dolphin: bool = False):
    profile = PROFILES[profile_key]
    print(f"\nЗапуск профиля {profile_key} ({profile['geo']})")

    if profile_key in COMPARE_PROFILES:
        run_full_compare(
            profile_key,
            include_dolphin=not use_dolphin,
            include_local_ip=(profile_key == "RU"),
        )
        return

    proxy = get_profile_proxy(profile_key)

    if use_dolphin:
        print("Режим: Dolphin Anty")
        run_dolphin_profile(profile_key)
        return

    if proxy:
        print("Режим: локальный браузер + прокси")
        run_local_proxy_test(profile_key)
        return

    print(
        f"Прокси для {profile_key} не задан ({profile_key}_PROXY_SERVER в .env), "
        "используем Dolphin"
    )
    run_dolphin_profile(profile_key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сбор метрик Fastpari")
    parser.add_argument(
        "--profiles",
        help="Профили через запятую (UZ,BD,RU). По умолчанию — все",
    )
    parser.add_argument(
        "--dolphin",
        action="store_true",
        help="Принудительно через Dolphin Anty вместо локального прокси",
    )
    args = parser.parse_args(argv)

    if args.profiles:
        keys = [key.strip().upper() for key in args.profiles.split(",") if key.strip()]
        unknown = [key for key in keys if key not in PROFILES]
        if unknown:
            print(f"Неизвестные профили: {', '.join(unknown)}")
            return 1
    else:
        keys = list(PROFILES.keys())

    for profile_key in keys:
        run_for_profile(profile_key, use_dolphin=args.dolphin)

    generate_html_report()
    publish_report()
    return 0


if __name__ == "__main__":
    sys.exit(main())