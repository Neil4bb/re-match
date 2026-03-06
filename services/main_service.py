from extensions import db
from models import Game, MarketPrice, UserAsset
from services.igdb_service import IGDBService

class MainManager:
    def __init__(self):
        self.igdb = IGDBService()

    # --- Day 8 新增/修改：搜尋與存檔 ---
    def search_and_store_game(self, keyword):
        """搜尋並將結果存入資料庫，回傳物件清單"""
        # 將導入移到這裡！只有執行這個函式時才會去找 app 避免循環導入
        from app import app

        # 呼叫已經重構好的 igdb_service，這裡拿到的資料已經處理過圖片與平台
        raw_results = self.igdb.search_game(keyword)
        
        if not raw_results:
            return []

        processed_games = []
        
        with app.app_context():
            for item in raw_results:
                # 使用 filter_by 確保抓到最新的資料庫物件
                existing_game = Game.query.filter_by(id=item['id']).first()
                
                # 取得 igdb_service 抓到的中文名
                c_name = item.get('chinese_name', '')

                if not existing_game:
                    # 建立新遊戲
                    new_game = Game(
                        id=item['id'],
                        name=item['name'],
                        chinese_name=c_name,
                        cover_url=item['cover_url'],
                        platform=item['platform_name']
                    )
                    db.session.add(new_game)
                    processed_games.append(new_game)
                else:
                    # 🔥 [關鍵修正]：如果資料庫裡沒中文，但 API 有抓到，就立刻補填
                    if c_name and not existing_game.chinese_name:
                        existing_game.chinese_name = c_name
                    
                    # 為了保險，同步更新可能變動的封面或平台資訊
                    existing_game.cover_url = item['cover_url']
                    existing_game.platform = item['platform_name']
                    
                    processed_games.append(existing_game)
            
            db.session.commit() # 這一行會把所有的「補填」寫入資料庫
            # 🔥 [解決方案]：在 commit 後手動把物件從 session 中「剝離」
            # 這樣就算 session 關閉，HTML 範本還是能讀取到欄位內容
            for g in processed_games:
                db.session.refresh(g) # 確保最新資料已載入
                db.session.expunge(g) # 讓物件脫離 Session 狀態，變成獨立的資料字典

        return processed_games

    # --- 原本的功能：PTT 標題對應 (務必保留) ---
    def update_market_prices(self):
        from app import app
        from ptt_service import PttAdapter
        ptt = PttAdapter()
        posts = ptt.fetch_latest_posts() # 抓回標題
        
        with app.app_context():
            # 1. 抓出資料庫所有的遊戲名稱與 ID
            all_games = Game.query.all()
            
            matches_found = 0
            for title in posts:
                # 2. 針對每一條標題，先摳出價格
                price = ptt.extract_price(title)
                if not price:
                    continue
                
                # 3. 尋找標題中有沒有包含我們資料庫裡的遊戲
                for game in all_games:
                    if game.name in title:
                        # 4. 發現配對！存入 MarketPrice 表
                        new_price = MarketPrice(
                            game_id=game.id,
                            price=price,
                            source="PTT",
                            title=title # 保留標題方便後續檢閱
                        )
                        db.session.add(new_price)
                        matches_found += 1
            
            db.session.commit()
            return f"掃描完成！成功更新 {matches_found} 筆市價資料。"