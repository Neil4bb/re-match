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
        target_ids = [48, 130, 167, 508]
        
       # --- 第一階段：精準搜尋 + 平台過濾 ---
        # 加入 where platforms = ... 確保回傳結果皆符合平台要求
        body = f"""
        search "{game_name}"; 
        fields name, cover.url, summary, category, platforms.id, platforms.name, alternative_names.name; 
        where platforms = {target_platforms};
        limit 10;
        """
        
        try:
            response = requests.post(search_url, headers=headers, data=body)
            raw_games = response.json()
            
            # --- 第二階段：模糊比對 + 平台過濾 ---
            # 如果精準搜尋沒結果，改用「包含模式」，同樣強制過濾平台

            if not raw_games:
                print(f"🔍 模式切換：執行模糊比對...")
                body = f"""
                fields name, cover.url, summary, category, platforms.id, platforms.name, alternative_names.name; 
                where name ~ *"{game_name}"* & platforms = {target_platforms}; 
                limit 10;
                """
                response = requests.post(search_url, headers=headers, data=body)
                raw_games = response.json()

            # --- 資料清洗與標準化 ---
            for game in raw_games:
                # ---平台 ---
                platforms = game.get('platforms', [])
                matched_names = [p['name'] for p in platforms if p.get('id') in target_ids]
                game['platform'] = " / ".join(matched_names)

                # 初始化預設值
                game['chinese_name'] = ""
                
                if 'alternative_names' in game:
                    alts = game.get('alternative_names', [])
                    
                    # 💡 策略：建立一個「絕對排除」的簡體關鍵字清單
                    exclude_keywords = ['simplified', 'china', 'mainland']
                    # 針對特定譯名差異建立排除詞
                    exclude_names = ['塞尔达', '精靈寶可夢', '马力欧'] 

                    # 第一輪：尋找明確標註繁體、台灣或香港的別名
                    for alt in alts:
                        name = alt.get('name', '')
                        comment = alt.get('comment', '').lower()
                        if any(tag in comment for tag in ['traditional', 'taiwan', 'hong kong', '繁體', '台灣']):
                            game['chinese_name'] = cc.convert(name)
                            break
                    
                    # 第二輪：如果沒找到標註，找「不含簡體關鍵字」且「不含排除詞」的中文別名
                    if not game['chinese_name']:
                        for alt in alts:
                            name = alt.get('name', '')
                            comment = alt.get('comment', '').lower()
                            
                            # 檢查是否包含中文字元
                            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in name)
                            # 檢查是否觸發排除條件
                            is_simplified = any(k in comment for k in exclude_keywords)
                            is_excluded_name = any(en in name for en in exclude_names)
                            
                            if has_chinese and not is_simplified and not is_excluded_name:
                                game['chinese_name'] = cc.convert(name)
                                break
                
                # 如果以上都沒抓到，最後才考慮搜尋關鍵字
                if not game['chinese_name'] and any('\u4e00' <= char <= '\u9fff' for char in game_name):
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
        
    def get_popular_switch_games(self, limit=500, offset=0):
            """獲取遊戲清單 (終極相容版：移除所有過濾條件進行測試)"""
            if not self.access_token:
                self.get_access_token()
            if not self.access_token:
                return []

            search_url = "https://api.igdb.com/v4/games"
            headers = {
                'Client-ID': self.client_id,
                'Authorization': f'Bearer {self.access_token}'
            }

            # 終極測試：完全不設 where，看能不能抓到任何東西
            # 如果這有反應，我們再慢慢把 platforms = (130) 加回去
            body = f"fields name, id; limit {limit}; offset {offset};"
            
            try:
                # 使用 print 偵錯，確保我們送出的 body 長什麼樣
                print(f"DEBUG: Sending Body -> {body}")
                response = requests.post(search_url, headers=headers, data=body)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"DEBUG: IGDB 成功回傳 {len(data)} 筆遊戲")
                    return data
                else:
                    print(f"❌ IGDB API 錯誤: {response.status_code} - {response.text}")
                    return []
            except Exception as e:
                print(f"💥 請求異常: {e}")
                return []
            
    def get_game_by_id(self, game_id):
        """修正：確保 ID 查詢也能抓到中文別名並清洗"""
        if not self.access_token: self.get_access_token()
        cc = OpenCC('s2twp')
        
        # 🌟 關鍵：必須在 fields 加入 alternative_names 相關欄位
        body = f"""
            fields name, cover.url, summary, first_release_date, 
                platforms.id, platforms.name, 
                alternative_names.name, alternative_names.comment; 
            where id = {game_id};
        """
        
        try:
            res = requests.post("https://api.igdb.com/v4/games", 
                                headers={'Client-ID': self.client_id, 'Authorization': f'Bearer {self.access_token}'}, 
                                data=body)
            data = res.json()
            if not data: return None
            
            game = data[0]
            # --- 開始移植你的搜尋清洗邏輯 ---
            game['chinese_name'] = ""
            alts = game.get('alternative_names', [])
            
            # 第一輪：找繁體標籤
            for alt in alts:
                name = alt.get('name', '')
                comment = alt.get('comment', '').lower()
                if any(tag in comment for tag in ['traditional', 'taiwan', 'hong kong', '繁體', '台灣']):
                    game['chinese_name'] = cc.convert(name)
                    break
            
            # 第二輪：過濾簡體與排除詞 (這部分直接套用你 search_game 的邏輯)
            if not game['chinese_name']:
                exclude_keywords = ['simplified', 'china', 'mainland']
                exclude_names = ['塞尔达', '精靈寶可夢', '马力欧']
                for alt in alts:
                    name = alt.get('name', '')
                    has_chinese = any('\u4e00' <= char <= '\u9fff' for char in name)
                    is_simplified = any(k in alt.get('comment', '').lower() for k in exclude_keywords)
                    is_excluded = any(en in name for en in exclude_names)
                    if has_chinese and not is_simplified and not is_excluded:
                        game['chinese_name'] = cc.convert(name)
                        break
            
            # 處理圖片與平台
            if 'cover' in game:
                game['cover_url'] = "https:" + game['cover']['url'].replace('t_thumb', 't_cover_big')
            return game
        except Exception as e:
            print(f"❌ ID 查詢補完失敗: {e}")
            return None
        
    def get_games_by_custom_query(self, query_body):
        """
        通用型 IGDB 查詢方法，接受自定義的查詢字串 (body)
        """
        if not self.access_token:
            self.get_access_token()
        print(f"🔑 目前使用的 Token: {self.access_token[:10]}***") # 偵錯用
        if not self.access_token:
            return []

        search_url = "https://api.igdb.com/v4/games"
        headers = {
            'Client-ID': self.client_id,
            'Authorization': f'Bearer {self.access_token}'
        }

        try:
            # 🌟 這裡使用你現有的 requests.post 邏輯
            response = requests.post(search_url, headers=headers, data=query_body)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ IGDB API 錯誤: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            print(f"💥 請求異常: {e}")
            return []
        
    def get_game_platforms_only(self, game_id):
        """專門為修復腳本設計：只獲取平台資訊，不更動名稱"""
        if not self.access_token: self.get_access_token()
        
        body = f"fields name, platforms.name; where id = {game_id};"
        
        try:
            res = requests.post(
                "https://api.igdb.com/v4/games", 
                headers={'Client-ID': self.client_id, 'Authorization': f'Bearer {self.access_token}'}, 
                data=body
            )
            data = res.json()
            return data[0] if data else None
        except Exception as e:
            print(f"❌ 僅平台查詢失敗 (ID: {game_id}): {e}")
            return None
        
# --- 測試代碼 (當你直接執行此檔案時才會跑) ---
if __name__ == "__main__":
    service = IGDBService()
    # 測試搜尋 Zelda
    results = service.search_game("薩爾達傳說")
    print(results)
    for game in results:
        print(f"遊戲名稱: {game['name']}")
        print(f"遊戲名稱: {game['chinese_name']}")
        print(f"封面網址: {game['cover_url']}")
        print(f"平台: {game['platform_name']}")
        print("-" * 20)
    