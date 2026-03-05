from app import app
from extensions import db
from models import Game, MarketPrice

with app.app_context():
    print("=" * 50)
    # 1. 顯示遊戲庫內容
    all_games = Game.query.all()
    if not all_games:
        print("【遊戲庫】目前是空的。")
    else:
        print(f"【遊戲庫】目前共有 {len(all_games)} 款遊戲：")
        for g in all_games:
            print(f"ID: {g.id} | 名稱: {g.name} | 平台: {g.platform}")

    print("-" * 50)

    # 2. 顯示市場行情內容
    all_prices = MarketPrice.query.all()
    if not all_prices:
        print("【市場行情】目前沒有任何抓取到的市價紀錄。")
    else:
        print(f"【市場行情】目前共有 {len(all_prices)} 筆紀錄：")
        for p in all_prices:
            # 這裡利用了 p.game.name 獲取關聯的遊戲名稱
            print(f"遊戲: {p.game.name} | 價格: {p.price} | 來源: {p.source}")
            print(f"標題: {p.title}")
            print(f"時間: {p.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print("." * 30)
    print("=" * 50)