import time
import random
from app import app, db
from models import Game
from services.main_service import MainManager

def run_price_crawler():
    with app.app_context():
        manager = MainManager()
        
        # 1. 只抓取目前 games table 裡的遊戲 (那 120 筆)
        targets = Game.query.all()
        total = len(targets)
        
        print(f"🚀 開始執行 120 筆 PS 大作即時查價 (共 {total} 筆)...")

        for index, game in enumerate(targets, 1):
            # 取得搜尋用的關鍵字 (優先用中文名)
            search_name = game.chinese_name or game.name
            
            print(f"\n[{index}/{total}] 📡 正在爬取價格: {search_name}")

            try:
                # 2. 直接調用你現有的查價核心
                # 此函數會自動爬取 PS Digital, PS PTT, NS Digital, NS PTT
                # 我們傳入 game.id，它內部會自動去 handle nsuid 的關聯
                results = manager.get_single_game_market_data(
                    game_id=game.id,
                    name=search_name
                )
                
                if results.get('status') == 'success':
                    print(f"   💰 PS 數位: {results['ps_digital']} | PTT: {results['ps_ptt']}")
                    print(f"   💰 NS 數位: {results['ns_digital']} | PTT: {results['ns_ptt']}")
                else:
                    print(f"   ⚠️ 查價失敗: {results.get('message')}")

            except Exception as e:
                print(f"   ❌ 執行異常 ({search_name}): {str(e)}")
                db.session.rollback()

            # 🌟 模仿你 sync_trending.py 的保護策略
            if index % 50 == 0:
                print("☕ 已處理 50 筆，長休息 180 秒以保護 IP...")
                time.sleep(180)
            else:
                # 隨機休息 6~12 秒，避免被 PTT 或 PS Store 封鎖
                wait = random.uniform(6.0, 12.0)
                print(f"😴 休息 {wait:.1f} 秒...")
                time.sleep(wait)

        print("\n🎉 120 筆價格爬取任務完成！資料已存入 market_prices 表。")

if __name__ == "__main__":
    run_price_crawler()