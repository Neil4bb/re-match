import time
from app import app, db
from models import Game, EShopMapping, GamePlatformID
from services.main_service import MainManager

def run_full_sync():
    with app.app_context():
        manager = MainManager()
        
        # 1. 獲取所有現有的遊戲紀錄 (包含那 120 筆 PS 遊戲)
        all_games = Game.query.all()
        total = len(all_games)
        print(f"🚀 開始執行優先配對補全 (共 {total} 筆)...")

        for index, game in enumerate(all_games, 1):
            print(f"\n[{index}/{total}] 處理中: {game.chinese_name or game.name} (ID: {game.id})")
            
            try:
                # 🔄 順序一：優先與 EShopMapping 進行中文名稱比對
                # 使用你清洗過的中文名稱進行精準匹配
                mapping = EShopMapping.query.filter_by(game_name=game.chinese_name).first()
                
                if mapping:
                    print(f"🔗 成功配對本地 EShopMapping！使用本地資料更新...")
                    
                    # 1. 更新 Game Table 欄位 (強制覆蓋為本地 Mapping 資料)
                    game.name = mapping.english_name or game.name
                    game.chinese_name = mapping.game_name or game.chinese_name
                    game.cover_url = mapping.icon_url or game.cover_url
                    game.summary = mapping.intro or game.summary  # 填入你剛匯入的介紹
                    
                    # 2. 綁定 NS 平台關聯 (GamePlatformID)
                    if mapping.nsuid:
                        ns_check = GamePlatformID.query.filter_by(
                            game_id=game.id, 
                            platform='NS'
                        ).first()
                        
                        if not ns_check:
                            new_ns = GamePlatformID(
                                game_id=game.id,
                                platform='NS',
                                platform_external_id=str(mapping.nsuid)
                            )
                            db.session.add(new_ns)
                            print(f"➕ 已新增 NSUID 關聯: {mapping.nsuid}")
                    
                    # 3. 回填 Mapping 表的 igdb_id 確保雙向關聯
                    if mapping.igdb_id != game.id:
                        mapping.igdb_id = game.id
                    
                    print(f"✅ 本地補全完成。")

                # 🔄 順序二：如果本地沒配對到，或是資料仍不完整，才求助 IGDB
                else:
                    is_still_incomplete = (
                        not game.cover_url or 
                        not game.summary or 
                        "PS_Pending" in (game.name or "")
                    )

                    if is_still_incomplete:
                        print(f"📡 本地未命中，請求 IGDB 權威資料補全...")
                        raw_data = manager.igdb.get_game_by_id(game.id)
                        
                        if raw_data:
                            # 更新基本資訊
                            game.name = raw_data.get('name', game.name)
                            game.cover_url = raw_data.get('cover_url', game.cover_url)
                            game.summary = raw_data.get('summary', game.summary)
                            
                            # 處理平台 ID (PS4, PS5 等)
                            if 'platforms' in raw_data:
                                for p in raw_data['platforms']:
                                    p_name = p.get('platform', {}).get('name', '')
                                    ext_id = p.get('external_id')
                                    
                                    p_type = None
                                    if 'PlayStation 4' in p_name: p_type = 'PS4'
                                    elif 'PlayStation 5' in p_name: p_type = 'PS5'
                                    
                                    if p_type and ext_id:
                                        exists = GamePlatformID.query.filter_by(game_id=game.id, platform=p_type).first()
                                        if not exists:
                                            db.session.add(GamePlatformID(
                                                game_id=game.id, 
                                                platform=p_type, 
                                                platform_external_id=str(ext_id)
                                            ))
                            print(f"✅ IGDB 補全完成。")
                        else:
                            print(f"⚠️ IGDB 查無資料。")

                # 每 10 筆提交一次
                if index % 10 == 0:
                    db.session.commit()

            except Exception as e:
                print(f"❌ 錯誤 (ID: {game.id}): {str(e)}")
                db.session.rollback()

            # 稍微休息保護 API
            time.sleep(0.2)

        db.session.commit()
        print("\n🎉 任務結束：本地優先補全計畫已達成！")

if __name__ == "__main__":
    run_full_sync()