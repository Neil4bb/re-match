from playwright.sync_api import sync_playwright
import re

def get_nsuid_final_boss(game_name):
    """
    處理紅色彈窗，並從渲染後的 HTML 提取 titles/7001
    """
    with sync_playwright() as p:
        # 設定 headless=False 讓你可以看到它點掉彈窗的過程
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        
        # 優先嘗試搜尋中文，因為截圖顯示中文結果最齊全
        search_query = "巫師 3" if "Witcher" in game_name else game_name
        search_url = f"https://store.nintendo.com.hk/eshopsearch/result/?q={search_query}"
        
        try:
            print(f"🚀 正在獵殺：{search_query}...")
            page.goto(search_url, wait_until="networkidle", timeout=60000)
            
            # --- 關鍵：處理紅色彈窗 ---
            # 根據截圖，我們尋找彈窗上的「確認」按鈕
            confirm_btn = page.locator('button:has-text("確認"), .btn-confirm, .modal-footer button')
            if confirm_btn.count() > 0:
                print("🖱️ 發現阻擋彈窗，正在點擊「確認」...")
                confirm_btn.first.click()
                page.wait_for_timeout(2000) # 等待彈窗消失
            
            # 等待遊戲內容加載 (你截圖中的那些遊戲圖片)
            page.wait_for_selector(".product-item-info, a[href*='titles']", timeout=10000)
            
            # 抓取包含渲染後 ID 的所有連結
            html = page.content()
            ids = re.findall(r'titles/(7001\d{10})', html)
            
            if ids:
                # 排除可能重複的 ID 並取第一個
                nsuid = list(dict.fromkeys(ids))[0]
                print(f"🎯 獵殺成功！NSUID: {nsuid}")
                return nsuid
            else:
                print("❌ 彈窗已處理，但仍未發現遊戲本體 ID。")
                page.screenshot(path="after_popup_debug.png")
                return None
                
        except Exception as e:
            print(f"💥 執行出錯: {e}")
            return None
        finally:
            page.wait_for_timeout(3000) # 讓你看一眼成果再關閉
            browser.close()

if __name__ == "__main__":
    get_nsuid_final_boss("Witcher 3")