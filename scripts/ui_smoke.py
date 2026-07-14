from pathlib import Path

from playwright.sync_api import sync_playwright


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    console_errors: list[str] = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.goto("http://127.0.0.1:3000", wait_until="networkidle")
    page.get_by_role("heading", name="把零散知识，磨成你的判断力。").wait_for()
    assert page.get_by_text("仅依据你的资料回答").is_visible()
    page.screenshot(path="/tmp/ledger-dashboard.png", full_page=True)

    page.get_by_role("button", name="资料库").click()
    page.get_by_role("heading", name="资料库").wait_for()
    assert page.get_by_text("资料库还是空的").is_visible()

    page.get_by_role("button", name="AI 研讨").click()
    page.get_by_role("heading", name="AI 研讨室").wait_for()
    assert page.get_by_text("严格资料约束").is_visible()

    page.get_by_role("button", name="系统设置").click()
    page.get_by_role("heading", name="系统设置").wait_for()
    assert page.get_by_text("密钥安全边界").is_visible()
    page.wait_for_timeout(600)
    page.screenshot(path="/tmp/ledger-settings.png", full_page=True)

    filtered = [message for message in console_errors if "favicon" not in message.lower()]
    assert not filtered, f"browser console errors: {filtered}"
    print("UI smoke passed; screenshots: /tmp/ledger-dashboard.png, /tmp/ledger-settings.png")
    browser.close()
