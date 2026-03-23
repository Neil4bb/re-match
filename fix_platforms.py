from app import app, db
from models import Game, GamePlatformID
from services.main_service import MainManager
import time
import sys

def repair():
    """
    專用修復腳本：
    遍歷資料庫中所有遊戲，補齊遺失的 PlayStation (PS4/PS5) 平台標籤。
    """
    with app.app_context():
        # 初始化管理員與 IGDB 服務
        manager = MainManager()
        
        # 取得所有已在 games 表中的遊戲
        games = Game.query.all()
        total = len(games)
        
        print(f"🚀 開始執行平台標籤補齊任務...")
        print(f"📊 目前 games 表中共有 {total} 筆遊戲需檢查。")
        print("-" * 50)

        success_count = 0
        skip_count = 0
        error_count = 0

        for index, g in enumerate(games, 1):
            try:
                # 🌟 呼叫輕量化專用方法，只抓 platforms
                # 注意：請確認 igdb_service.py 已包含 get_game_platforms_only 方法
                detail = manager.igdb.get_game_platforms_only(g.id)
                
                if detail and 'platforms' in detail:
                    added_platforms = []
                    
                    for p in detail['platforms']:
                        p_name = p.get('name', '')
                        
                        # 定義我們感興趣的平台關鍵字
                        target_keywords = ['PlayStation 4', 'PlayStation 5', 'PS4', 'PS5', 'Switch', 'Nintendo Switch','Switch 2', 'Nintendo Switch 2']
                        
                        if any(k in p_name for k in target_keywords):
                            # 檢查該遊戲是否已具備此平台標籤
                            exists = GamePlatformID.query.filter_by(
                                game_id=g.id, 
                                platform=p_name
                            ).first()
                            
                            if not exists:
                                # 建立新的關聯紀錄
                                new_pid = GamePlatformID(game_id=g.id, platform=p_name)
                                db.session.add(new_pid)
                                added_platforms.append(p_name)
                    
                    if added_platforms:
                        db.session.commit()
                        success_count += 1
                        print(f"[{index}/{total}] ✅ {g.name}: 已補齊 {added_platforms}")
                    else:
                        skip_count += 1
                        # 為了不讓日誌太長，每 50 筆才印一次跳過訊息
                        if index % 50 == 0:
                            print(f"[{index}/{total}] ⏭️ 處理中 (目前跳過 {skip_count} 筆無須更新項目)...")
                else:
                    print(f"[{index}/{total}] ⚠️ {g.name}: IGDB 回傳資料不完整 (ID: {g.id})")
                
                # 遵守 IGDB API 頻率限制 (每秒約 4 次)
                time.sleep(0.3)
                
            except Exception as e:
                db.session.rollback()
                error_count += 1
                print(f"[{index}/{total}] ❌ {g.name} 修復出錯: {str(e)}")

        print("-" * 50)
        print(f"✨ 任務完成！")
        print(f"✅ 成功補齊: {success_count} 筆")
        print(f"⏭️ 無須更動: {skip_count} 筆")
        print(f"❌ 執行出錯: {error_count} 筆")

if __name__ == "__main__":
    repair()