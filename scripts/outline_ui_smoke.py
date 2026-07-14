from playwright.sync_api import sync_playwright


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    console_errors: list[str] = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.goto("http://127.0.0.1:3100", wait_until="networkidle")
    page.get_by_role("button", name="资料库").click()
    page.get_by_role("heading", name="资料库").wait_for()
    page.locator('input[type="file"]').set_input_files({
        "name": "收入准则讲义.md",
        "mimeType": "text/markdown",
        "buffer": "# 收入准则\n\n## 合同识别\n\n合同识别应当根据资料所列条件判断。\n\n## 履约义务\n\n履约义务需要单独识别。".encode(),
    })
    page.get_by_text("等待你的确认").wait_for(timeout=20000)
    page.locator('.proposal-chapter-head input[value="收入准则"]').wait_for()
    page.locator('.proposal-point input[value="合同识别"]').wait_for()
    page.screenshot(path="/tmp/ledger-outline-review.png", full_page=True)

    chapter_input = page.locator(".proposal-chapter-head input").first
    chapter_input.fill("收入五步法")
    page.get_by_role("button", name="保存草稿").click()
    page.get_by_text("目录草稿已保存").wait_for()
    page.get_by_role("button", name="确认写入课程").click()
    page.get_by_text("目录已写入正式课程树").wait_for()
    page.get_by_role("button", name="课程目录").click()
    page.locator(".subject-node > button").first.click()
    page.get_by_text("收入五步法", exact=True).wait_for(timeout=10000)
    page.screenshot(path="/tmp/ledger-outline-confirmed.png", full_page=True)

    filtered = [message for message in console_errors if "favicon" not in message.lower()]
    assert not filtered, f"browser console errors: {filtered}"
    print("outline UI smoke passed")
    browser.close()
