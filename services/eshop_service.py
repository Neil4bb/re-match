import re
import requests
from extensions import db
from models import MarketPrice, Game

class EShopService:
    def __init__(self):
        self.price_url = "https://api.ec.nintendo.com/v1/price"
        # 匯率設定 (1 HKD = 4.2 TWD)
        self.exchange_rate = 4.2

    def search_nsuid(self, page, game_name, chinese_name=None):
        """
        不再自己啟動 Playwright，而是使用傳入的 page 執行搜尋。
        這能確保在同一個 Flask Request 執行緒中安全執行。
        """
        # --- 名稱清洗邏輯：中文優先 ---
        if chinese_name:
            search_query = re.split(r'[:：\-]', chinese_name)[0].strip()
        else:
            search_query = re.split(r'[:：\-]', game_name)[0].strip()
            if search_query.lower().startswith("the "):
                search_query = search_query[4:].strip()

        # 這裡不使用 with sync_playwright()，改用傳入的 page
        search_url = f"https://store.nintendo.com.hk/eshopsearch/result/?q={search_query}"
        
        try:
            print(f"🚀 [Scraper] 正在以關鍵字獵殺: {search_query}...")
            # 使用 wait_until="load" 提升首次導航速度
            page.goto(search_url, wait_until="load", timeout=20000)
            
            # 處理紅色阻擋彈窗
            # --- 關鍵修正：改為非阻塞檢查彈窗 ---
            confirm_btn = page.locator('button:has-text("確認"), .btn-confirm').first
            # 只有當按鈕「真的出現且可見」時才點擊，否則只等 2 秒就放棄
            try:
                if confirm_btn.is_visible(timeout=2000):
                    confirm_btn.click()
                    print("🖱️ 已自動點掉阻擋彈窗")
            except:
                pass # 沒出現就直接繼續，不要浪費 30 秒
            
            # 等待官方遊戲本體 ID 出現 ( titles/7001... )
            page.wait_for_selector("a[href*='titles/7001']", timeout=20000)
            html = page.content()
            ids = re.findall(r'titles/(7001\d{10})', html)
            
            if ids:
                nsuid = list(dict.fromkeys(ids))[0]
                print(f"🎯 [Scraper] 成功獲取 ID: {nsuid}")
                return nsuid
                
        except Exception as e:
            print(f"⚠️ [Scraper] 搜尋 {search_query} 失敗或超時: {e}")
            
        return None

    def get_price_twd(self, game_id, nsuid):
        if not nsuid: return None
        try:
            # 確保 ID 是乾淨的字串
            clean_id = str(nsuid).strip()
            
            # 使用正確的變數名稱 clean_id
            url = "https://api.ec.nintendo.com/v1/price"
            params = {
                'country': 'HK',
                'lang': 'zh',
                'ids': clean_id  # 👈 修正為 clean_id
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            }
            
            print(f"💰 正在請求價格 API (ID: {clean_id})...")
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            # 這是最保險的 Debug 方式：印出完整 URL，你可以直接點擊比對
            print(f"🔗 實際請求路徑: {response.url}")
            
            data = response.json()
            prices = data.get('prices', [])
            
            if prices and len(prices) > 0:
                p = prices[0]
                
                # 根據你提供的 JSON 結構，價格可能在 regular_price 或 discount_price
                price_info = p.get('discount_price') or p.get('regular_price')
                
                if price_info:
                    val = price_info.get('raw_value')
                    # 濾掉非數字字元後轉型
                    numeric_val = re.sub(r'[^\d.]', '', str(val))
                    price_twd = int(float(numeric_val) * self.exchange_rate)
                    
                    print(f"💵 成功獲取: HKD {numeric_val} -> TWD {price_twd}")
                    
                    # 儲存至資料庫邏輯
                    mp = MarketPrice.query.filter_by(game_id=game_id, source='eShop').first()
                    if not mp:
                        mp = MarketPrice(game_id=game_id, source='eShop')
                    mp.price = price_twd
                    mp.title = "eShop 數位版"
                    db.session.add(mp)
                    return price_twd
                    
            print(f"⚠️ API 回傳內容中找不到價格欄位: {data}")
        except Exception as e:
            print(f"❌ 價格同步過程出錯: {e}")
        return None