import requests

API_KEY = "393727ce73de6d5087238317447855d9008f3bd3a15ba9df"
BASE_URL = "http://127.0.0.1:50325"

HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def start_profile(profile_id):
    response = requests.post(
        f"{BASE_URL}/api/v2/browser-profile/start",
        headers=HEADERS,
        json={"profile_id": profile_id},
        timeout=30
    )
    
    response.raise_for_status()        # ← важно!
    
    data = response.json()
    
    if data.get("code") != 0:
        raise Exception(f"AdsPower error: {data.get('msg')}")
        
    return data["data"]