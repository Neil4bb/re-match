import time
import random
from app import app, db
from models import Game, EShopMapping
from services.main_service import MainManager

def run_integrated_sync():
    with app.app_context():
        manager = MainManager()
        
        # 1. 取得執行目標
        # 階段一：已存在於 games 表的遊戲 (包含 PS 專家清單)
        existing_games = Game.query.all()
        # 階段二：尚未關聯到 IGDB ID 的 Mapping 紀錄
        pending_mappings = EShopMapping.query.filter(EShopMapping.igdb_id == None).all()
        
        print(f"🔥 任務啟動：既存遊戲 {len(existing_games)} 筆，待處理 Mapping {len(pending_mappings)} 筆")

        # --- 第一階段：既存遊戲查價 ---
        #print("\n--- 階段 1：更新既存遊戲價格 (PS 專家與已認親遊戲) ---")
        #for index, game in enumerate(existing_games, 1):
        #    print(f"[{index}/{len(existing_games)}] 📡 查價中: {game.chinese_name or game.name}")
        #    
        #    # 直接查價，此函數內部會自動處理 NSUID 回填
        #    manager.get_single_game_market_data(
        #        game_id=game.id, 
        #        nsuid=game.nsuid, 
        #        name=game.chinese_name or game.name
        #    )
        #    
        #    smart_sleep(index)

        # --- 第二階段：處理 Mapping 表 (認親 + 建立 Game + 查價) ---
        print("\n--- 階段 2：處理 Mapping 表資料 (自動建立 Game 紀錄) ---")
        for index, m in enumerate(pending_mappings, 1):
            print(f"[{index}/{len(pending_mappings)}] 📡 處理新遊戲: {m.game_name}")
            
            # 🌟 步驟 A: 先去 IGDB 搜尋並建立 Game 紀錄
            # 此方法會回傳儲存後的 game 物件，包含從 IGDB 抓到的正式 ID
            game = manager.find_and_store_single_game(m.game_name, m.nsuid)
            
            if game and game.id:
                # 🌟 步驟 B: 有了正式 game_id，執行完整查價並存檔
                manager.get_single_game_market_data(
                    game_id=game.id, 
                    nsuid=m.nsuid, 
                    name=m.game_name
                )
                print(f"   ✅ 完成認親與查價: IGDB_ID={game.id}")
            else:
                # 若 IGDB 搜尋完全沒結果，至少也要記錄查價 (使用無 ID 模式)
                print(f"   ⚠️ IGDB 查無結果，執行基礎查價模式...")
                manager.get_single_game_market_data(
                    game_id=None, 
                    nsuid=m.nsuid, 
                    name=m.game_name
                )

            # 每 20 筆強制提交，確保進度存入 RDS
            if index % 20 == 0:
                db.session.commit()
                print("💾 進度已存檔...")
            
            smart_sleep(index)

def smart_sleep(index):
    """隨機休息策略，防止 IP 被封鎖"""
    if index % 50 == 0:
        print("☕ 已處理 50 筆，長休息 180 秒...")
        time.sleep(180)
    else:
        wait = random.uniform(6.0, 12.0)
        print(f"😴 休息 {wait:.1f} 秒...")
        time.sleep(wait)

if __name__ == "__main__":
    run_integrated_sync()