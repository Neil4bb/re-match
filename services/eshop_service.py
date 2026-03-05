import requests
from models import MarketPrice
from extensions import db
from datetime import datetime

class EShopService:
    def __init__(self):
        self.api_url = "https://api.ec.nintendo.com/v1/price"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    def get_price_twd(self, nsuid):
        """
        透過香港 API 抓取價格並換算台幣
        """
        params = {
            'country': 'HK',
            'lang': 'zh',
            'ids': str(nsuid)
        }
        try:
            response = requests.get(self.api_url, params=params, headers=self.headers, timeout=10)
            data = response.json()

            # 驗證資料存在且狀態為 onsale
            if not data.get('prices') or data['prices'][0].get('sales_status') == 'not_found':
                return None

            price_info = data['prices'][0]
            
            # 優先抓取特價，若無則抓原價，使用你發現的 raw_value 欄位
            if 'discount_price' in price_info:
                hkd_val = float(price_info['discount_price']['raw_value'])
            else:
                hkd_val = float(price_info['regular_price']['raw_value'])
            
            # 匯率換算 (港幣 HKD 轉台幣 TWD，暫定 4.2)
            return round(hkd_val * 4.2)

        except Exception as e:
            print(f"eShop API 請求異常: {e}")
            return None

    def update_game_price(self, game_obj):
        """
        傳入遊戲物件，自動抓取並寫入 MarketPrice 表格
        """
        if not game_obj.eshop_nsuid:
            print(f"跳過 {game_obj.name}：未設定 eshop_nsuid")
            return None

        twd_price = self.get_price_twd(game_obj.eshop_nsuid)
        if twd_price:
            new_price = MarketPrice(
                game_id=game_obj.id,
                price=twd_price,
                source='eShop',
                created_at=datetime.now()
            )
            db.session.add(new_price)
            db.session.commit()
            return twd_price
        return None