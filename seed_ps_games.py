import time
from app import app, db
from models import Game
from services.main_service import MainManager
from services.ps_expert_mapping import PS_CLEAN_DATA

def import_ps_expert_games():
    with app.app_context():
        manager = MainManager()
        total = len(PS_CLEAN_DATA)
        print(f"🚀 開始匯入 PS 專家清單 (共 {total} 筆)...")

        for index, data in enumerate(PS_CLEAN_DATA, 1):
            cn_name = data['cn']
            en_name = data['en']
            
            print(f"\n[{index}/{total}] 處理中: {cn_name}")

            try:
                # 🌟 使用名稱搜尋 IGDB (避免 ID 錯誤)
                # 使用你現有的 get_games_by_custom_query 進行 search
                query_body = f'search "{en_name}"; fields id, name, cover.url, summary, platforms.name; limit 1;'
                search_results = manager.igdb.get_games_by_custom_query(query_body)

                if not search_results:
                    print(f"  ⚠️ IGDB 搜尋不到: {en_name}")
                    continue

                item = search_results[0]
                
                # 處理圖片 URL (套用你 igdb_service 裡的邏輯)
                cover_obj = item.get('cover')
                cover_url = cover_obj.get('url').replace('t_thumb', 't_cover_big') if cover_obj else None
                if cover_url and cover_url.startswith('//'):
                    cover_url = 'https:' + cover_url

                # 🌟 準備丟入 store_game_logic 的資料格式
                # 強制將名稱設定為你字典裡的版本
                formatted_data = {
                    'id': item['id'],
                    'name': en_name,           # 鎖定字典英文
                    'chinese_name': cn_name,    # 鎖定字典中文
                    'cover_url': cover_url,
                    'summary': item.get('summary'),
                    'platforms': item.get('platforms', [])
                }

                # 調用你現有的核心邏輯
                # 這會自動處理 Game 存檔與 GamePlatformID 關聯
                manager.store_game_logic(formatted_data)
                
                print(f"  ✅ 成功同步: {en_name} (IGDB ID: {item['id']})")

            except Exception as e:
                print(f"  ❌ 處理出錯: {e}")
                db.session.rollback()

            # 遵守 API 速率限制
            time.sleep(0.3)

        db.session.commit()
        print("\n🎉 PS 專家清單匯入與 IGDB ID 校正完成！")

if __name__ == "__main__":
    import_ps_expert_games()