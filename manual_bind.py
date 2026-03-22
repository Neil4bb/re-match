import os
from app import app, db
from models import EShopMapping, Game, GamePlatformID, MarketPrice, UserAsset
from services.main_service import MainManager

def rebuild_zelda_precisely():
    manager = MainManager()
    with app.app_context():
        # 🌟 定義正確的連結資訊
        TARGET_NSUID = "70010000009367"
        CORRECT_IGDB_ID = 7346
        
        print(f"🛠️  正在執行精準重構：{TARGET_NSUID} -> IGDB:{CORRECT_IGDB_ID}")

        try:
            # 1. 取得本地 Mapping 資料 (為了拿取正確的中文名)
            mapping = EShopMapping.query.filter_by(nsuid=TARGET_NSUID).first()
            if not mapping:
                print("❌ 錯誤：找不到對應的 NSUID 紀錄")
                return

            # 2. 清理所有與此 NSUID 曾關聯過的錯誤 ID (如 150080)
            if mapping.igdb_id and mapping.igdb_id != CORRECT_IGDB_ID:
                old_id = mapping.igdb_id
                print(f"⚠️  正在清理舊的錯誤關聯 (ID: {old_id})...")
                MarketPrice.query.filter_by(game_id=old_id).delete()
                GamePlatformID.query.filter_by(game_id=old_id).delete()
                UserAsset.query.filter_by(game_id=old_id).delete()
                Game.query.filter_by(id=old_id).delete()
                mapping.igdb_id = None
                db.session.flush()

            # 3. 直接從 IGDB 抓取指定 ID 的詳細資訊 (包含平台資訊)
            print(f"📡 正在抓取正宗 IGDB ID {CORRECT_IGDB_ID} 的資料與平台資訊...")
            igdb_data = manager.igdb.get_game_by_id(CORRECT_IGDB_ID)
            
            if not igdb_data:
                print("❌ 錯誤：無法從 IGDB 取得資料")
                return

            # 4. 核心邏輯：將 IGDB 資料與本地 Mapping 結合
            # 我們手動把 nsuid 塞進去，這樣 store_game_logic 就會優先用 mapping 的中文名
            igdb_data['nsuid'] = TARGET_NSUID 
            
            # 5. 執行儲存 (這會建立 Game 與正確的 GamePlatformID)
            new_game = manager.store_game_logic(igdb_data)
            
            # 6. 最後確保 Mapping 指向正確 ID
            mapping.igdb_id = CORRECT_IGDB_ID
            db.session.commit()

            print(f"✨ 成功！已建立正確資料：{new_game.name}")
            print(f"🎮 平台資訊已儲存，現在首頁應該會顯示正確的封面與譯名。")

        except Exception as e:
            db.session.rollback()
            print(f"💥 失敗：{e}")

if __name__ == "__main__":
    rebuild_zelda_precisely()