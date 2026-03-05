from app import app
from extensions import db
from models import Game, MarketPrice, UserAsset
from igdb_service import IGDBService

class MainManager:
    def __init__(self):
        self.igdb = IGDBService()

    def search_and_store_game(self, keyword):
        """搜尋並將結果存入資料庫 (如果不存在的話)"""
        # 1. 先去 IGDB 抓資料
        raw_results = self.igdb.search_game(keyword)
        if not raw_results:
            return "找不到相關遊戲"

        processed_games = []
        
        with app.app_context():
            for item in raw_results:
                # 檢查資料庫是否已經有這款遊戲 (避免重複存檔)
                existing_game = Game.query.get(item['id'])
                
                if not existing_game:
                    # 處理封面圖網址 (IGDB 給的是相對路徑，我們幫它補齊)
                    cover = item.get('cover', {}).get('url', '')
                    if cover:
                        cover = "https:" + cover.replace('t_thumb', 't_cover_big')

                    # 建立新遊戲物件
                    new_game = Game(
                        id=item['id'],
                        name=item['name'],
                        cover_url=cover,
                        platform=item.get('platforms', [{}])[0].get('name', 'Unknown')
                    )
                    db.session.add(new_game)
                    processed_games.append(f"新存入: {new_game.name}")
                else:
                    processed_games.append(f"已存在: {existing_game.name}")
            
            db.session.commit()
        return processed_games
    
    #把ptt的標題 對應到資料庫裡的game_id
    def update_market_prices(self):
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

# --- 測試整合邏輯 ---
if __name__ == "__main__":
    # 1. 實例化指揮官
    manager = MainManager()
    
    # 2. 執行市價更新任務
    print("--- 開始執行 Day 4 市價更新任務 ---")
    status_message = manager.update_market_prices()
    
    # 3. 印出結果
    print(status_message)
    print("--- 任務結束 ---")