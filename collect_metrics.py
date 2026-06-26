from config.profiles import PROFILES
from config.pages import PAGES

from core.adspower import start_profile
from core.browser import connect_to_browser, get_or_create_context, create_page, close_all_pages
from core.monitor import monitor_page
from core.warmup import warmup
from core.html_report import generate_html_report

def run_for_profile(profile_key: str):
    profile = PROFILES[profile_key]
    print(f"\n🚀 Запуск профиля {profile_key} ({profile['geo']})")
    
    try:
        profile_data = start_profile(profile["profile_id"])
        ws_url = profile_data["ws"]["puppeteer"]
        
        pw, browser = connect_to_browser(ws_url)
        context = get_or_create_context(browser)
        
        # Warmup
        warmup_page = create_page(context)
        warmup(warmup_page)
        warmup_page.close()
        
        # Тесты
        for page_name, url in PAGES.items():
            page = create_page(context)
            monitor_page(page, profile["geo"], page_name, url)
            page.close()
            
    except Exception as e:
        print(f"❌ Критическая ошибка в профиле {profile_key}: {e}")
    finally:
        try:
            close_all_pages(context)
            browser.close()
            pw.stop()
        except:
            pass

if __name__ == "__main__":
    # Запуск по одному или всем
    for profile_key in PROFILES.keys():
        run_for_profile(profile_key)
    
    generate_html_report()