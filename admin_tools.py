# admin_tools.py
from app import app
from extensions import db
from models import Game, EShopMapping, UserAsset

def force_bind_nsuid_to_igdb(nsuid, igdb_id, chinese_name):
    """
    最穩健的綁定方法：
    1. 先確保 Game 表有這筆 ID，沒有就生一個
    2. 再進行 Mapping 綁定
    """
    with app.app_context():
        # 1. 檢查 Game 表
        game = db.session.get(Game, igdb_id)
        if not game:
            print(f"🎮 正在建立新的遊戲紀錄 (ID: {igdb_id})...")
            game = Game(id=igdb_id, name=chinese_name, chinese_name=chinese_name)
            db.session.add(game)
            db.session.flush() # 先流向資料庫但不提交，確保外鍵檢查能通過
        
        # 2. 檢查並更新 Mapping
        mapping = EShopMapping.query.filter_by(nsuid=nsuid).first()
        if mapping:
            mapping.igdb_id = igdb_id
            print(f"✅ 已將 NSUID:{nsuid} 綁定至 GameID:{igdb_id} ({chinese_name})")
        else:
            print(f"❌ 找不到 NSUID: {nsuid} 的 Mapping 紀錄")
            return

        db.session.commit()
        print("🚀 資料庫更新成功！")


def delete_virtual_game(virtual_id):
    """精準刪除虛擬 ID 遊戲"""
    with app.app_context():
        # 尋找那個 nsuid_ 開頭的錯誤紀錄
        target = db.session.get(Game, virtual_id)
        if target:
            print(f"🗑️ 正在刪除虛擬遊戲: {target.name} ({virtual_id})")
            db.session.delete(target)
            db.session.commit()
            print("✅ 刪除成功！")
        else:
            print("❌ 找不到該虛擬 ID，可能已經被刪除了")


def cleanup_duplicate_games(keep_id, delete_ids):
    """
    清理重複的遊戲紀錄。
    keep_id: 你想要保留的正確 IGDB ID (例如 143613)
    delete_ids: 那些自動產生、名稱混亂或沒有封面的錯誤 ID 列表
    """
    with app.app_context():
        for d_id in delete_ids:
            game_to_del = db.session.get(Game, d_id)
            if game_to_del:
                print(f"🗑️ 正在刪除重複資料: {game_to_del.name} (ID: {d_id})")
                db.session.delete(game_to_del)
        
        db.session.commit()
        print("✅ 清理完成！")

def reset_game_data(game_id):
    """徹底刪除遊戲紀錄，讓系統重新搜尋與認親"""
    with app.app_context():
        # 1. 先解除 EShopMapping 的綁定，否則會因為外鍵約束刪不掉
        mappings = EShopMapping.query.filter_by(igdb_id=game_id).all()
        for m in mappings:
            m.igdb_id = None
            print(f"🔗 已解除 Mapping 綁定: {m.game_name}")

        # 2. 刪除 Game 本體
        game = db.session.get(Game, game_id)
        if game:
            print(f"🗑️ 正在刪除遊戲主體: {game.name} (ID: {game_id})")
            db.session.delete(game)
            db.session.commit()
            print("✅ 該遊戲已從資料庫完全抹除，現在你可以重新搜尋它了。")
        else:
            print("❌ 找不到該 Game ID")


def force_fix_game_full_data(nsuid, igdb_id, chinese_name, english_name, cover_url):
    with app.app_context():
        # 🌟 1. 先處理 Game 表 (確保父層存在)
        game = db.session.get(Game, igdb_id)
        if not game:
            print(f"🆕 正在建立 Game 紀錄: {igdb_id}")
            game = Game(id=igdb_id)
            db.session.add(game)
        
        # 寫入遊戲資料
        game.name = english_name
        game.chinese_name = chinese_name
        game.cover_url = cover_url
        
        # 🌟 2. 執行一次 Flush，確保 Game 先進入資料庫緩衝
        db.session.flush()

        # 🌟 3. 最後才修正 EShopMapping 導向
        mapping = EShopMapping.query.filter_by(nsuid=nsuid).first()
        if mapping:
            mapping.igdb_id = igdb_id
            mapping.english_name = english_name
            print(f"🔗 字典已導向: {nsuid} -> IGDB:{igdb_id}")
        
        db.session.commit()
        print(f"✨ 成功！遊戲 '{chinese_name}' 資料已完全手工校正。")


def delete_game_by_id(game_id):
    """
    安全刪除指定 ID 的遊戲：
    1. 先解除 EShopMapping 的關聯 (防止外鍵衝突)
    2. 刪除 Game 本體 (會自動觸發價格與平台 ID 的連帶刪除)
    """
    with app.app_context():
        # 🌟 步驟 1: 解除字典 (EShopMapping) 的綁定
        mappings = EShopMapping.query.filter_by(igdb_id=game_id).all()
        for m in mappings:
            m.igdb_id = None
            print(f"🔗 已解除 Mapping 綁定: {m.game_name}")

        # 2. 🌟 新增：刪除所有引用此遊戲的使用者資產
        # 因為 user_assets.game_id 設有外鍵約束，必須先消失
        assets_deleted = UserAsset.query.filter_by(game_id=game_id).delete()
        print(f"📦 已從 {assets_deleted} 個使用者的資產箱中移除此遊戲")

        # 🌟 步驟 2: 執行刪除
        game = db.session.get(Game, game_id)
        if game:
            name = game.chinese_name or game.name
            print(f"🗑️ 正在從資料庫完全抹除: {name} (ID: {game_id})")
            db.session.delete(game)
            db.session.commit()
            print(f"✅ 成功刪除遊戲：{name}")
        else:
            print(f"❌ 找不到 ID 為 {game_id} 的遊戲，可能已被刪除。")


if __name__ == "__main__":
    # 執行修正：斯普拉遁 3 (IGDB ID: 143613)
    #force_bind_nsuid_to_igdb(
    #    nsuid='70010000046398', 
    #    igdb_id=143613, 
    #    chinese_name="斯普拉遁 3"
    #)

    # 保留 143613，刪除那個虛擬字串 ID
    #cleanup_duplicate_games(keep_id=143613, delete_ids=['nsuid_70010000046398'])

    # 🌟 執行這行來刪除左邊那張破圖的卡片
    #delete_virtual_game('nsuid_70010000046398')

    # 執行重置：斯普拉遁 3
    #reset_game_data(143613)

    # 🌟 斯普拉遁 3 完整修復範例
    #force_fix_game_full_data(
    #    nsuid='70010000046398', 
    #    igdb_id=143613, 
    #    chinese_name="斯普拉遁3",
    #    english_name="Splatoon 3",
    #    cover_url="https://img-eshop.cdn.nintendo.net/i/f8b83a587fe7235cc3fe842eaccf3d9679500a6b206e119b772f8f52572161d4.jpg"
    #)

    target_ids = [431, 565, 512]

    for gid in target_ids:
        delete_game_by_id(gid)