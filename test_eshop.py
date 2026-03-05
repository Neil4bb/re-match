from app import app
from extensions import db
from models import Game, MarketPrice
from services.eshop_service import EShopService

def run_test():
    with app.app_context():
        # 1. 確保資料庫中有這款遊戲並填入正確 ID
        game_name = "瑪利歐賽車 8 豪華版"
        game = Game.query.filter_by(name=game_name).first()
        
        if not game:
            print(f"建立測試遊戲資料：{game_name}")
            game = Game(name=game_name, eshop_nsuid="70070000013724")
            db.session.add(game)
            db.session.commit()
        else:
            game.eshop_nsuid = "70070000013724"
            db.session.commit()

        # 2. 執行抓取服務
        service = EShopService()
        print(f"📡 正在嘗試抓取 {game.name} 的數位版行情...")
        
        price = service.update_game_price(game)
        
        if price:
            print(f"✅ 成功！")
            print(f"   - 抓取到港幣價格並換算台幣為：NT$ {price}")
            print(f"   - 已成功寫入 MarketPrice 表格，來源標記為 'eShop'")
        else:
            print("❌ 失敗：無法從 API 取得有效數據。")

if __name__ == "__main__":
    run_test()