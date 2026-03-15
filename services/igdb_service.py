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

        # 定義目標平台
        target_platforms = "(48, 130, 167, 465)"
        target_ids = [48, 130, 167, 465]
        
       # --- 第一階段：精準搜尋 + 平台過濾 ---
        # 加入 where platforms = ... 確保回傳結果皆符合平台要求
        body = f"""
        search "{game_name}"; 
        fields name, cover.url, platforms.name, alternative_names.name, summary; 
        where platforms = {target_platforms}; 
        limit 10;
        """
        
        try:
            response = requests.post(search_url, headers=headers, data=body)
            raw_games = response.json()
            
            # --- 第二階段：模糊比對 + 平台過濾 ---
            # 如果精準搜尋沒結果，改用「包含模式」，同樣強制過濾平台
            if not raw_games and len(game_name) >= 1:
                print(f"🔍 模式切換：針對 '{game_name}' 執行模糊過濾並鎖定平台...")
                body = f"""
                fields name, cover.url, platforms.name, alternative_names.name; 
                where (name ~ *"{game_name}"* | alternative_names.name ~ *"{game_name}"*) 
                & platforms = {target_platforms}; 
                limit 10;
                """
                response = requests.post(search_url, headers=headers, data=body)
                raw_games = response.json()

            # --- 資料清洗與標準化 ---
            for game in raw_games:
                # ---平台 ---
                platforms = game.get('platforms', [])
                matched_names = [p['name'] for p in platforms if p.get('id') in target_ids]
                game['platform_name'] = " / ".join(matched_names)

                # 初始化預設值
                game['chinese_name'] = ""
                
                # 優先從別名找中文
                if 'alternative_names' in game:
                    alts = [alt.get('name', '') for alt in game['alternative_names']]
                    # 這裡多加一個判斷：如果別名包含 game_name 或者是中文
                    for alt_n in alts:
                        if any('\u4e00' <= char <= '\u9fff' for char in alt_n):
                            game['chinese_name'] = cc.convert(alt_n)
                            break
                
                # 如果 IGDB 根本沒給中文別名，我們試著看搜尋字串是否就是中文
                if not game['chinese_name'] and any('\u4e00' <= char <= '\u9fff' for char in game_name):
                    # 如果使用者搜的是中文，且結果的名稱與搜尋詞有部分重疊，就暫時當作中文名
                    game['chinese_name'] = cc.convert(game_name)
                
                # 處理圖片：補上 https 並換成大圖 t_cover_big
                if 'cover' in game and 'url' in game['cover']:
                    original_url = game['cover']['url']
                    game['cover_url'] = "https:" + original_url.replace('t_thumb', 't_cover_big')
                else:
                    # 給一個漂亮的預留圖網址
                    game['cover_url'] = "https://placehold.co/264x352?text=No+Cover"
                

            return raw_games
        except Exception as e:
            print(f"Search failed: {e}")
            return []

# --- 測試代碼 (當你直接執行此檔案時才會跑) ---
if __name__ == "__main__":
    service = IGDBService()
    # 測試搜尋 Zelda
    results = service.search_game("巫")
    print(results)
    for game in results:
        print(f"遊戲名稱: {game['name']}")
        print(f"封面網址: {game['cover_url']}")
        print(f"平台: {game['platform_name']}")
        print("-" * 20)
    