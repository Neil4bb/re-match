import requests
import os
from dotenv import load_dotenv
from opencc import OpenCC #繁簡轉換工具

# 1. 載入 .env 裡面的金鑰 (本地開發用，Render 上會自動抓環境變數)
load_dotenv()

class IGDBService:
    def __init__(self):
        # 統一使用 os.environ.get 以對接 Render 後台設定
        self.client_id = os.environ.get('IGDB_CLIENT_ID')
        self.client_secret = os.environ.get('IGDB_CLIENT_SECRET')
        self.access_token = None

    def get_access_token(self):
        """向 Twitch 申請臨時通行證 (Access Token)"""
        if not self.client_id or not self.client_secret:
            print("Error: Missing IGDB_CLIENT_ID or IGDB_CLIENT_SECRET!")
            return None

        auth_url = "https://id.twitch.tv/oauth2/token"
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials'
        }
        
        try:
            response = requests.post(auth_url, params=params)
            response.raise_for_status() # 若狀態碼不是 200 會拋出異常
            data = response.json()
            self.access_token = data.get('access_token')
            print("Successfully obtained IGDB Access Token!")
        except Exception as e:
            print(f"Failed to get token: {e}")

    def search_game(self, game_name):
        # 初始化轉換器，s2twp 代表：簡體到台灣繁體（含慣用語轉換）
        cc = OpenCC('s2twp')
        """搜尋遊戲並回傳已處理好的資料清單"""
        # 如果沒有 Token 就去拿一個
        if not self.access_token:
            self.get_access_token()

        if not self.access_token:
            return []

        search_url = "https://api.igdb.com/v4/games"
        headers = {
            'Client-ID': self.client_id,
            'Authorization': f'Bearer {self.access_token}'
        }

        # 定義我們要的平台 ID 清單 (PS4, Switch, PS5, Switch2)
        target_ids_priority = [48, 130, 167, 465]
        target_platforms_str = "(48, 130, 167, 465)"
        
        # 查詢語法：抓取名稱、封面、平台名稱
        # 修正後的 Query Body：
        # 1. 增加 where platforms = ... 條件
        # 2. 只有當遊戲有在這些平台發布時，才會被搜出來
        body = f'search "{game_name}"; fields name, cover.url, platforms.name, alternative_names.name; where platforms = {target_platforms_str}; limit 5;'
        
        try:
            response = requests.post(search_url, headers=headers, data=body)
            response.raise_for_status()
            raw_games = response.json()

            # --- 資料清洗與標準化 ---
            for game in raw_games:
                chinese_name = ""
                if 'alternative_names' in game:
                    # 1. 先找出所有包含中文的別名
                    all_chinese_alts = []
                    for alt in game['alternative_names']:
                        alt_n = alt.get('name', '')
                        if any('\u4e00' <= char <= '\u9fff' for char in alt_n):
                            all_chinese_alts.append(alt_n)
                    
                    if all_chinese_alts:
                        # 2. 假設我們優先取第一個抓到的
                        # 3. 強制轉換為繁體中文，解決簡繁混雜問題
                        raw_chinese = all_chinese_alts[0]
                        chinese_name = cc.convert(raw_chinese)
                
                game['chinese_name'] = chinese_name
                
                # 處理圖片：補上 https 並換成大圖 t_cover_big
                if 'cover' in game and 'url' in game['cover']:
                    original_url = game['cover']['url']
                    game['cover_url'] = "https:" + original_url.replace('t_thumb', 't_cover_big')
                else:
                    # 給一個漂亮的預留圖網址
                    game['cover_url'] = "https://placehold.co/264x352?text=No+Cover"
                
                # 處理平台：平台顯示校正
                if 'platforms' in game:
                    # 找出所有匹配我們 target_ids 的平台名稱
                    matched_names = [p['name'] for p in game['platforms'] if p.get('id') in target_ids_priority]
                    
                    if matched_names:
                        # 將它們串接成字串，例如 "PS4, Nintendo Switch"
                        game['platform_name'] = " / ".join(matched_names)
                    else:
                        game['platform_name'] = game['platforms'][0].get('name', 'Unknown')

            return raw_games
        except Exception as e:
            print(f"Search failed: {e}")
            return []

# --- 測試代碼 (當你直接執行此檔案時才會跑) ---
if __name__ == "__main__":
    service = IGDBService()
    # 測試搜尋 Zelda
    results = service.search_game("巫師3")
    print(results)
    for game in results:
        print(f"遊戲名稱: {game['name']}")
        print(f"封面網址: {game['cover_url']}")
        print(f"平台: {game['platform_name']}")
        print("-" * 20)
    