import time
import random
from app import app, db
from models import Game, EShopMapping
from services.main_service import MainManager
from sqlalchemy.exc import IntegrityError, PendingRollbackError

def run_integrated_sync():
    with app.app_context():
        manager = MainManager()
        
        # 1. 取得執行目標
        existing_games = Game.query.all()
        # 這裡建議加上 order_by，確保重新啟動時順序一致
        pending_mappings = EShopMapping.query.filter(EShopMapping.igdb_id == None).all()
        
        print(f"🔥 任務啟動：既存遊戲 {len(existing_games)} 筆，待處理 Mapping {len(pending_mappings)} 筆")

        # --- 第一階段：既存遊戲查價 ---
        print("\n--- 階段 1：更新既存遊戲價格 ---")
        for index, game in enumerate(existing_games, 1):
            try:
                print(f"[{index}/{len(existing_games)}] 📡 查價中: {game.chinese_name or game.name}")
                manager.get_single_game_market_data(
                    game_id=game.id, 
                    nsuid=game.nsuid, 
                    name=game.chinese_name or game.name
                )
                db.session.commit() # 🌟 每筆存檔，最穩
            except Exception as e:
                db.session.rollback() # 🌟 萬一出錯，立即修復 Session
                print(f"❌ 階段 1 報錯 (跳過): {e}")
            
            smart_sleep(index)

        # --- 第二階段：處理 Mapping 表 ---
        print("\n--- 階段 2：處理 Mapping 表資料 ---")
        for index, m in enumerate(pending_mappings, 1):
            try:
                print(f"[{index}/{len(pending_mappings)}] 📡 處理新遊戲: {m.game_name}")
                
                # 🌟 步驟 A: 認親
                game = manager.find_and_store_single_game(m.game_name, m.nsuid)
                
                if game and game.id:
                    # 🌟 步驟 B: 有 ID 的完整模式
                    manager.get_single_game_market_data(
                        game_id=game.id, 
                        nsuid=m.nsuid, 
                        name=m.game_name
                    )
                    print(f"   ✅ 完成認親與查價: IGDB_ID={game.id}")
                else:
                    # 🌟 步驟 C: 無 ID 的基礎模式
                    print(f"   ⚠️ IGDB 查無結果，執行基礎查價模式...")
                    manager.get_single_game_market_data(
                        game_id=None, 
                        nsuid=m.nsuid, 
                        name=m.game_name
                    )

                db.session.commit() # 🌟 每筆存檔
                
            except (IntegrityError, PendingRollbackError) as db_err:
                db.session.rollback() # 🌟 針對資料庫衝突的專門處理
                print(f"💥 資料庫衝突 (跳過): {db_err}")
            except Exception as e:
                db.session.rollback() # 🌟 萬用保險
                print(f"💥 嚴重錯誤 (跳過): {e}")

            smart_sleep(index)

def smart_sleep(index):
    """隨機休息策略，防止 IP 被封鎖"""
    if index % 50 == 0:
        print("☕ 已處理 50 筆，長休息 180 秒...")
        time.sleep(60)
    else:
        wait = random.uniform(2.0, 5.0)
        print(f"😴 休息 {wait:.1f} 秒...")
        time.sleep(wait)

if __name__ == "__main__":
    run_integrated_sync()