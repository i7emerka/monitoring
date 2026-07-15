import os
import re

from dotenv import load_dotenv

load_dotenv()

# Dolphin / MangoProxy: socks5://host:port:username:password
_EMBEDDED_PROXY_RE = re.compile(
    r"^(?P<scheme>https?|socks5)://(?P<host>[^:]+):(?P<port>\d+):(?P<username>[^:]+):(?P<password>.+)$"
)
# Стандартный URL: socks5://username:password@host:port
_AT_PROXY_RE = re.compile(
    r"^(?P<scheme>https?|socks5)://(?P<username>[^:]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)$"
)

PROFILES = {
    "UZ": {
        "profile_id": 822754225,
        "geo": "Uzbekistan",
    },
    "BD": {
        "profile_id": 822754495,
        "geo": "Bangladesh",
    },
    "RU": {
        "profile_id": int(os.getenv("DOLPHIN_RU_PROFILE_ID", "825752486")),
        "geo": "Russia",
    },
}


def parse_proxy_config(
    server: str,
    username: str = "",
    password: str = "",
) -> dict | None:
    """Парсит прокси для Playwright. Поддерживает формат Dolphin/Mango в одной строке."""
    server = (server or "").strip()
    if not server:
        return None

    match = _EMBEDDED_PROXY_RE.match(server) or _AT_PROXY_RE.match(server)
    if match:
        parts = match.groupdict()
        # Playwright/Chromium не поддерживает SOCKS5 с логином (Dolphin-формат).
        # MangoProxy и аналоги принимают HTTP на том же host:port.
        scheme = "http" if parts["scheme"] == "socks5" else parts["scheme"]
        proxy = {
            "server": f"{scheme}://{parts['host']}:{parts['port']}",
            "username": parts["username"],
            "password": parts["password"],
        }
    else:
        proxy = {"server": server}
        if username.strip():
            proxy["username"] = username.strip()
        if password.strip():
            proxy["password"] = password.strip()

    return proxy


def get_profile_proxy(profile_key: str) -> dict | None:
    """Прокси для локального Playwright."""
    prefix = profile_key.upper()
    server = os.getenv(f"{prefix}_PROXY_SERVER", "").strip()
    username = os.getenv(f"{prefix}_PROXY_USERNAME", "").strip()
    password = os.getenv(f"{prefix}_PROXY_PASSWORD", "").strip()
    return parse_proxy_config(server, username, password)