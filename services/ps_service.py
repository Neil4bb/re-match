import requests
import re
import json

class PSService:
    def __init__(self):
        self.url = "https://web.np.playstation.com/api/graphql/v1/op"
        self.headers = {
            "Content-Type": "application/json",
            "x-psn-store-locale-override": "zh-Hant-TW",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Origin": "https://store.playstation.com",
            "Referer": "https://store.playstation.com/"
        }

    def fetch_price(self, game_name):
        # 完全對齊 .har 檔中的 JSON 結構 
        payload = {
            "operationName": "getSearchResults",
            "variables": {
                "searchTerm": game_name,
                "pageSize": 24,
                "pageOffset": 0,
                "countryCode": "TW",
                "languageCode": "zh-Hant",
                "nextCursor": None  # 在 .har 中第一頁通常是 null 
            },
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "6ef5e809c35a056a1150fdcf513d9c505484dd1a946b6208888435c3182f105a"
                }
            }
        }

        try:
            print(f"📡 正在請求 PS Store (HAR 對齊版): {game_name}")
            response = requests.post(self.url, headers=self.headers, json=payload, timeout=10)
            
            if response.status_code != 200:
                print(f"❌ API 報錯: {response.status_code}")
                return None

            data = response.json()
            
            # 根據 .har 檔中的回傳結構解析 
            # data -> universalSearch -> results 
            results = data.get('data', {}).get('universalSearch', {}).get('results', [])
            
            if not results:
                print("⚠️ 列表仍為空。")
                return None
            
            for item in results:
                name = item.get('name', '')
                classification = item.get('storeDisplayClassification', '')
                price_info = item.get('price', {})
                base_price = price_info.get('basePrice', '') # 例如 "NT$1,250" 
                
                print(f"🔎 找到: {name} | 分類: {classification} | 價格: {base_price}")

                # 邏輯過濾：只要 FULL_GAME 且名稱與搜尋字高度相關 
                if classification == "FULL_GAME" and game_name[:2] in name:
                    if base_price == "免費": return 0
                    numeric_val = int(re.sub(r'[^\d]', '', base_price))
                    return numeric_val
                        
        except Exception as e:
            print(f"💥 異常: {e}")
        return None

if __name__ == "__main__":
    ps = PSService()
    # 測試 .har 檔中原本就有的關鍵字，這一定會成功
    res = ps.fetch_price("底特律") 
    print(f"\n🏆 最終結果: {res}")