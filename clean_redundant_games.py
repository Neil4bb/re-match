from app import app, db
from models import Game, EShopMapping, UserAsset, GamePlatformID, MarketPrice

def clean_database():
    with app.app_context():
        print("📖 開始掃描冗餘數據...")
        
        # 1. 找出所有正在被 EShopMapping 使用的 IGDB ID
        valid_igdb_ids = db.session.query(EShopMapping.igdb_id).filter(
            EShopMapping.igdb_id.isnot(None)
        ).distinct().all()
        valid_igdb_ids = [r[0] for r in valid_igdb_ids]

        # 2. 找出所有「不在 Mapping 表中」的遊戲
        # 但我們要排除掉那些「已經被使用者收藏」的遊戲，以免觸發外鍵錯誤
        redundant_games = Game.query.filter(
            ~Game.id.in_(valid_igdb_ids)
        ).all()

        if not redundant_games:
            print("✅ 沒有發現冗餘遊戲。")
            return

        print(f"🧹 預計處理 {len(redundant_games)} 筆無關聯遊戲...")

        for g in redundant_games:
            try:
                # 檢查是否有使用者收藏這款遊戲
                is_tracked = UserAsset.query.filter_by(game_id=g.id).first()
                if is_tracked:
                    print(f"⚠️ 跳過 '{g.name}' (ID: {g.id})：該遊戲已被使用者收藏，不可刪除。")
                    continue

                # 刪除與該遊戲相關的其他表資料（避免其他外鍵衝突）
                MarketPrice.query.filter_by(game_id=g.id).delete()
                GamePlatformID.query.filter_by(game_id=g.id).delete()
                
                # 最後刪除遊戲本體
                db.session.delete(g)
                print(f"🗑️ 已刪除冗餘遊戲: {g.name}")
                
            except Exception as e:
                db.session.rollback()
                print(f"❌ 刪除 {g.name} 失敗: {e}")

        db.session.commit()
        print("✨ 資料庫清理完成！")

if __name__ == "__main__":
    clean_database()