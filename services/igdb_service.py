import requests
import os
from dotenv import load_dotenv

# 載入 .env 裡面的金鑰
load_dotenv()

class IGDBService:
    def __init__(self):
        self.client_id = os.getenv('IGDB_CLIENT_ID')
        self.client_secret = os.getenv('IGDB_CLIENT_SECRET')
        self.access_token = None

    def get_access_token(self):
        """向 Twitch 申請臨時通行證 (Access Token)"""
        auth_url = "https://id.twitch.tv/oauth2/token"
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials'
        }
        response = requests.post(auth_url, params=params)
        if response.status_code == 200:
            self.access_token = response.json()['access_token']
            print("Successfully obtained IGDB Access Token!")
        else:
            print(f"Failed to get token: {response.status_code}")

    def search_game(self, game_name):
        """搜尋遊戲並回傳標準資料"""
        if not self.access_token:
            self.get_access_token()

        search_url = "https://api.igdb.com/v4/games"
        headers = {
            'Client-ID': self.client_id,
            'Authorization': f'Bearer {self.access_token}'
        }
        
        # IGDB 專用的查詢語法 (Query Body)
        # 我們抓取：id, 名稱, 封面圖, 平台
        body = f'search "{game_name}"; fields name, cover.url, platforms.name; limit 5;'
        
        response = requests.post(search_url, headers=headers, data=body)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Search failed: {response.status_code}")
            return None

# --- 測試代碼 ---
if __name__ == "__main__":
    service = IGDBService()
    results = service.search_game("Zelda")
    print(results)