import time
import random
from app import app, db
from models import Game, UserAsset
from services.main_service import MainManager
from sqlalchemy.exc import IntegrityError, PendingRollbackError

def run_integrated_sync():
    with app.app_context():
        manager = MainManager()
        
        # 🌟 核心優化：只抓取「出現在使用者資產箱」裡的遊戲 ID
        # 使用 distinct() 確保同款遊戲被多人收藏時，只會爬一次
        target_game_ids = db.session.query(UserAsset.game_id).distinct().all()
        target_game_ids = [tid[0] for tid in target_game_ids if tid[0] is not None]

        # 根據這些 ID 抓取完整的 Game 物件
        existing_games = Game.query.filter(Game.id.in_(target_game_ids)).all()
        
        print(f"🔥 任務啟動：僅針對使用者關注的 {len(existing_games)} 筆遊戲進行更新")

        # --- 執行查價 ---
        for index, game in enumerate(existing_games, 1):
            try:
                # 取得該遊戲對應的 NSUID (從關聯表抓)
                # 這是為了確保 eshop 查價能精準命中
                platform_rec = GamePlatformID.query.filter_by(game_id=game.id, platform='Switch').first()
                current_nsuid = platform_rec.external_id if platform_rec else None

                print(f"[{index}/{len(existing_games)}] 📡 監控中遊戲查價: {game.chinese_name or game.name}")
                
                manager.get_single_game_market_data(
                    game_id=game.id, 
                    nsuid=current_nsuid, 
                    name=game.chinese_name or game.name
                )
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"💥 處理 {game.name} 時發生錯誤: {e}")

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
        print("☕ 已處理 50 筆，長休息 60 秒...")
        time.sleep(60)
    else:
        wait = random.uniform(2.0, 5.0)
        print(f"😴 休息 {wait:.1f} 秒...")
        time.sleep(wait)

if __name__ == "__main__":
    run_integrated_sync()