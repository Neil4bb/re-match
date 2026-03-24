import re
import requests
import time
import random
from extensions import db
from models import MarketPrice, Game
from datetime import datetime

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
        time.sleep(random.uniform(0.5, 1.2))

        # 名稱清洗邏輯
        if chinese_name:
            search_query = re.split(r'[:：\-]', chinese_name)[0].strip()
        else:
            search_query = re.split(r'[:：\-]', game_name)[0].strip()
        
        url = "https://store.nintendo.com.hk/eshopsearch/result/"
        
        try:
            print(f"📡 [EShop Search] 正在請求關鍵字: {search_query}")
            session = requests.Session()
            response = session.get(url, params={"q": search_query}, headers=self._get_headers(), timeout=15)
            
            if response.status_code == 200:
                html_content = response.text
                
                # 1. 抓取 NSUID
                nsuids = re.findall(r'7001\d{10}', html_content)
                
                # 2. 抓取官方名稱 (利用正則表達式定位連結文字)
                # 尋找 <a class="product-item-link" ...> 這裡面的文字
                title_match = re.search(r'class="product-item-link">\s*(.*?)\s*</a>', html_content, re.DOTALL)
                eshop_title = title_match.group(1).strip() if title_match else None

                if nsuids:
                    nsuid = list(dict.fromkeys(nsuids))[0]
                    print(f"✅ [EShop Result] 成功獲取: {eshop_title} ({nsuid})")
                    # 🚀 重要：改回傳字典格式
                    return {
                        "nsuid": nsuid,
                        "eshop_name": eshop_title
                    }
                else:
                    print(f"❌ [EShop Result] 搜尋失敗：HTML 中找不到 7001 ID")
            elif response.status_code == 429:
                print("⚠️ [EShop Alert] 觸發 429 流量限制")
        except Exception as e:
            print(f"💥 [EShop Error] 發生異常: {e}")
        return None

    def get_price_twd(self, game_id, nsuid):
        if not nsuid: return None
        time.sleep(random.uniform(0.5, 1.0))

        # 1. 確保 ids 參數正確傳遞
        params = {"country": "HK", "lang": "zh", "ids": nsuid}
        headers = {"User-Agent": random.choice(self.ua_list)}
        
        try:
            print(f"📡 [Price API] 正在請求 NSUID 價格: {nsuid}")
            response = requests.get(self.price_url, params=params, headers=headers, timeout=10)
            data = response.json()
            
            # 💡 偵錯用：看看 API 回傳了什麼
            print(f"DEBUG API Response: {data}")

            prices = data.get('prices', [])
            
            if prices and len(prices) > 0:
                p = prices[0]
                # 香港 eShop 有時只回傳 regular_price，有特價才回傳 discount_price
                price_info = p.get('discount_price') or p.get('regular_price')
                
                if price_info:
                    # 取得原始數值 (例如 "HKD 429")
                    val = price_info.get('raw_value')
                    # 只留下數字與小數點
                    numeric_val = re.sub(r'[^\d.]', '', str(val))
                    
                    # 2. 計算台幣
                    price_twd = int(float(numeric_val) * self.exchange_rate)
                    
                    # 3. 存入資料庫，使用我們約定好的標籤
                    specific_title = f"eShop_{nsuid}"
                    
                    # 這裡必須確保是在 app.app_context 下執行，否則 db 操作會失敗
                    today = datetime.utcnow().date()
                    mp = MarketPrice.query.filter(
                        MarketPrice.game_id == game_id,
                        MarketPrice.source == 'eShop',
                        MarketPrice.title == specific_title,
                        db.func.date(MarketPrice.created_at) == today # 檢查日期
                    ).first()
                    
                    if not mp:
                        # 今天沒存過，建立新紀錄，這樣圖表才會多一個點
                        mp = MarketPrice(
                            game_id=game_id, 
                            source='eShop', 
                            title=specific_title,
                            price=price_twd
                        )
                        db.session.add(mp)
                    else:
                        # 今天存過了，則更新今天的價格 (防止一天內點多次產生太多點)
                        mp.price = price_twd
                        
                    db.session.commit()
                    print(f"✅ [Price Saved] {specific_title} 成功存入價格: NT$ {price_twd}")
                    return price_twd
                else:
                    print(f"⚠️ [Price API] NSUID {nsuid} 找不到價格欄位 (price_info is None)")
            else:
                print(f"❌ [Price API] NSUID {nsuid} 無效或 API 未回傳價格")
                
        except Exception as e:
            db.session.rollback()
            print(f"💥 [Price Error] 抓取價格異常: {e}")
        return None

if __name__ == "__main__":
    service = EShopService()
    test_game_name = "巫師3"
    
    nsuid = service.search_nsuid(test_game_name)
    
    if nsuid:
        # 注意：此處測試仍需在 app_context 下執行方可成功寫入資料庫
        print(f"🔍 測試 NSUID: {nsuid}")