from app import app, db
from models import EShopMapping
from sqlalchemy import func

def check_database_health():
    with app.app_context():
        print("="*60)
        print("🔍 EShop Mapping 資料庫全量檢查報告")
        print("="*60)

        # 1. 總量統計
        total_count = EShopMapping.query.count()
        english_count = EShopMapping.query.filter(EShopMapping.english_name.isnot(None)).count()
        missing_english = total_count - english_count
        
        print(f"📊 數據統計：")
        print(f"   - 總遊戲筆數 (7001): {total_count}")
        print(f"   - 中英對照成功數  : {english_count} ({(english_count/total_count*100):.2f}%)")
        print(f"   - 僅有中文名稱數  : {missing_english}")

        # 2. 隨機抽查 10 筆資料
        print("\n🎲 隨機抽查 10 筆資料：")
        print("-" * 60)
        samples = EShopMapping.query.order_by(func.rand()).limit(10).all()
        for s in samples:
            status = "✅" if s.english_name else "❌"
            print(f"{status} [{s.nsuid}] {s.game_name[:20]}... -> {s.english_name if s.english_name else 'None'}")

        # 3. 核心大作精確檢查
        print("\n🎯 核心大作縫合狀態確認：")
        print("-" * 60)
        key_games = ["薩爾達傳說", "瑪利歐", "寶可夢", "斯普拉遁"]
        for search_term in key_games:
            game = EShopMapping.query.filter(EShopMapping.game_name.like(f'%{search_term}%')).first()
            if game:
                status = "✅" if game.english_name else "❌"
                print(f"{status} 搜尋 '{search_term}': {game.game_name} -> {game.english_name}")
            else:
                print(f"❓ 搜尋 '{search_term}': 找不到任何相關資料")

        print("="*60)
        
        if english_count > 0:
            print("🚀 檢查完成：資料庫已準備好進行 IGDB 自動綁定。")
        else:
            print("⚠️ 警告：english_name 欄位全部為空，請重新檢查匯入邏輯。")

if __name__ == "__main__":
    check_database_health()