import re
import requests
import time
import random
from extensions import db
from models import MarketPrice, Game

class EShopService:
    def __init__(self):
        self.price_url = "https://api.ec.nintendo.com/v1/price"
        self.exchange_rate = 4.2
        # 建立 User-Agent 清單進行輪換
        self.ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
        ]

    def _get_headers(self):
        """動態生成隨機 Headers"""
        return {
            "User-Agent": random.choice(self.ua_list),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://store.nintendo.com.hk/"
        }

    def search_nsuid(self, game_name, chinese_name=None):
        # 請求前加入 1-3 秒的隨機延遲，模擬真人行為
        time.sleep(random.uniform(1.0, 3.0))

        # 名稱清洗邏輯
        if chinese_name:
            search_query = re.split(r'[:：\-]', chinese_name)[0].strip()
        else:
            search_query = re.split(r'[:：\-]', game_name)[0].strip()
        
        url = "https://store.nintendo.com.hk/eshopsearch/result/"
        
        try:
            print(f"📡 [EShop Search] 正在請求關鍵字: {search_query}")
            session = requests.Session()
            # 使用動態 Headers
            response = session.get(url, params={"q": search_query}, headers=self._get_headers(), timeout=15)
            
            if response.status_code == 200:
                html_content = response.text
                nsuids = re.findall(r'7001\d{10}', html_content)
                if nsuids:
                    nsuid = list(dict.fromkeys(nsuids))[0]
                    print(f"✅ [EShop Result] 成功獲取 NSUID: {nsuid}")
                    return nsuid
                else:
                    print(f"❌ [EShop Result] 搜尋失敗：HTML 中找不到 7001 ID")
            elif response.status_code == 429:
                print("⚠️ [EShop Alert] 觸發 429 Too Many Requests，建議停止操作。")
            else:
                print(f"❌ [EShop Result] HTTP 請求失敗，狀態碼: {response.status_code}")
        except Exception as e:
            print(f"💥 [EShop Error] 發生異常: {e}")
        return None

    def get_price_twd(self, game_id, nsuid):
        if not nsuid: return None
        # 請求前加入隨機延遲
        time.sleep(random.uniform(1.0, 2.0))

        params = {"country": "HK", "lang": "zh", "ids": nsuid}
        # 使用隨機 User-Agent
        headers = {"User-Agent": random.choice(self.ua_list)}
        
        try:
            response = requests.get(self.price_url, params=params, headers=headers, timeout=10)
            data = response.json()
            prices = data.get('prices', [])
            
            if prices and len(prices) > 0:
                p = prices[0]
                price_info = p.get('discount_price') or p.get('regular_price')
                
                if price_info:
                    val = price_info.get('raw_value')
                    numeric_val = re.sub(r'[^\d.]', '', str(val))
                    price_twd = int(float(numeric_val) * self.exchange_rate)
                    
                    # 儲存至資料庫邏輯
                    mp = MarketPrice.query.filter_by(game_id=game_id, source='eShop').first()
                    if not mp:
                        mp = MarketPrice(game_id=game_id, source='eShop')
                    mp.price = price_twd
                    mp.title = "eShop 數位版價格"
                    db.session.add(mp)
                    db.session.commit()
                    return price_twd
        except Exception as e:
            print(f"Error fetching price: {e}")
        return None

if __name__ == "__main__":
    service = EShopService()
    test_game_name = "巫師3"
    
    nsuid = service.search_nsuid(test_game_name)
    
    if nsuid:
        # 注意：此處測試仍需在 app_context 下執行方可成功寫入資料庫
        print(f"🔍 測試 NSUID: {nsuid}")