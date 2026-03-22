from app import app, db  # 🌟 確保從你的 app.py 匯入 app 與 db
from services.main_service import MainManager
import time

def sync_ps_top_200():
    with app.app_context():
        manager = MainManager()
    
        # 🌟 執行專屬 PS 查詢
        
        # 🌟 在這裡定義你的「PS 專屬熱門」查詢邏輯
        # platforms = 48 (PS4), 167 (PS5)
        # platforms != 130 (排除 Switch)
        # category = 0 (主遊戲)
        # total_rating_count (確保是大家聽過的大作)
        ps_query_body = """
            fields name, total_rating_count, platforms;
            where (platforms = 48 | platforms = 167) 
            & platforms != 130  
            & total_rating_count > 10;
            sort total_rating_count desc;
            limit 200;
        """
        
        print("🚀 正在從 IGDB 獲取 PS4/PS5 熱門遊戲清單 (排除 Switch)...")

        
        ps_games = manager.igdb.get_games_by_custom_query(ps_query_body)
        
        if not ps_games:
            print("❌ 找不到符合條件的遊戲")
            return

        print(f"🔥 準備更新 {len(ps_games)} 筆 PS 重要遊戲資料...")

        for index, game_data in enumerate(ps_games, 1):
            gid = game_data['id']
            gname = game_data['name']
            
            print(f"[{index}/200] 📡 同步中: {gname} (ID: {gid})")
            
            # 執行查價與存檔邏輯 (會跑 ensure_game_exists 與雙軌策略)
            manager.get_single_game_market_data(gid, name=gname, is_priority=True)
            
            # 為了防止 PTT 10054 錯誤，PS 專區建議休息久一點
            wait = 12 + (index % 5) # 12-16 秒隨機
            print(f"😴 休息 {wait} 秒...")
            time.sleep(wait)

if __name__ == "__main__":
    sync_ps_top_200()