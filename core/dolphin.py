import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("DOLPHIN_BASE_URL", "http://127.0.0.1:3001")
API_TOKEN = os.getenv("DOLPHIN_API_TOKEN", "")


def _check_token():
    if not API_TOKEN:
        raise Exception("DOLPHIN_API_TOKEN не задан в .env")


def authorize():
    _check_token()
    response = requests.post(
        f"{BASE_URL}/v1.0/auth/login-with-token",
        headers={"Content-Type": "application/json"},
        json={"token": API_TOKEN},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise Exception("Dolphin Anty: ошибка авторизации")
    return data


def start_profile(profile_id: int, *, restart: bool = True):
    authorize()

    if restart:
        stop_profile(profile_id)

    response = requests.get(
        f"{BASE_URL}/v1.0/browser_profiles/{profile_id}/start",
        params={"automation": 1},
        timeout=60,
    )

    if response.status_code == 500:
        data = response.json()
        error_text = str(data.get("error", ""))
        if "already running" in error_text.lower():
            stop_profile(profile_id)
            response = requests.get(
                f"{BASE_URL}/v1.0/browser_profiles/{profile_id}/start",
                params={"automation": 1},
                timeout=60,
            )

    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise Exception(f"Dolphin Anty error: {data}")
    return data["automation"]


def stop_profile(profile_id: int):
    try:
        authorize()
        requests.get(
            f"{BASE_URL}/v1.0/browser_profiles/{profile_id}/stop",
            timeout=30,
        )
    except Exception:
        pass