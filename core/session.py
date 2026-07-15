from core.dolphin import start_profile
from core.browser import connect_to_browser
from core.warmup import prime_page


def create_session(browser):
    """
    Создает новый контекст и страницу.
    """

    context = browser.contexts[0]

    page = context.new_page()

    return context, page