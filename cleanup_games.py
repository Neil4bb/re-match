import os
from app import app, db 
from models import Game, GamePlatformID, MarketPrice, EShopMapping, UserAsset # 🌟 新增匯入 UserAsset

def cleanup_database():
    with app.app_context():
        print("🧪 [Cleanup] 正在執行深度清理...")
        try:
            # 1. 刪除價格紀錄
            num_prices = MarketPrice.query.delete()
            print(f"🗑️ 已刪除 {num_prices} 筆價格紀錄")

            # 2. 刪除平台關聯 ID
            num_pids = GamePlatformID.query.delete()
            print(f"🗑️ 已刪除 {num_pids} 筆平台 ID 紀錄")

            # 🌟 3. 新增：刪除所有使用者的資產與願望清單
            # 這是解決 IntegrityError 1451 的關鍵
            num_assets = UserAsset.query.delete()
            print(f"🗑️ 已刪除 {num_assets} 筆使用者資產紀錄 (願望清單/持有)")

            # 4. 重置 Mapping 狀態
            num_mappings = EShopMapping.query.update({EShopMapping.igdb_id: None})
            print(f"🔗 已重置 {num_mappings} 筆 Mapping 關聯狀態")

            # 5. 現在可以安全清空遊戲主表了
            num_games = Game.query.delete()
            print(f"🔥 已清空 {num_games} 筆遊戲主資料")

            db.session.commit()
            print("\n✅ [Success] 資料庫已徹底清理完成！")
            print("💡 現在搜尋或查價，系統會重新建立『中文名稱優先』的資料。")

        except Exception as e:
            db.session.rollback()
            print(f"❌ [Error] 清理失敗: {e}")

if __name__ == "__main__":
    cleanup_database()