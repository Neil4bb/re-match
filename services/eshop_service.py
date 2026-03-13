import re
import requests
from extensions import db
from models import MarketPrice, Game

class EShopService:
    def __init__(self):
        self.price_url = "https://api.ec.nintendo.com/v1/price"
        self.exchange_rate = 4.2
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1"
        }

    def search_nsuid(self, game_name, chinese_name=None):
        # 名稱清洗邏輯
        if chinese_name:
            search_query = re.split(r'[:：\-]', chinese_name)[0].strip()
        else:
            search_query = re.split(r'[:：\-]', game_name)[0].strip()
        
        url = "https://store.nintendo.com.hk/eshopsearch/result/"
        
        try:
            print(f"📡 [EShop Search] 正在請求關鍵字: {search_query}")
            session = requests.Session()
            response = session.get(url, params={"q": search_query}, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                html_content = response.text
                nsuids = re.findall(r'7001\d{10}', html_content)
                if nsuids:
                    nsuid = list(dict.fromkeys(nsuids))[0]
                    print(f"✅ [EShop Result] 成功獲取 NSUID: {nsuid}")
                    return nsuid
                else:
                    print(f"❌ [EShop Result] 搜尋失敗：HTML 中找不到 7001 ID")
            else:
                print(f"❌ [EShop Result] HTTP 請求失敗，狀態碼: {response.status_code}")
        except Exception as e:
            print(f"💥 [EShop Error] 發生異常: {e}")
        return None

    def get_price_twd(self, game_id, nsuid):
        if not nsuid: return None
        params = {"country": "HK", "lang": "zh", "ids": nsuid}
        headers = {"User-Agent": self.headers["User-Agent"]}
        
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
                    
                    # 儲存至資料庫邏輯 (照舊)
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