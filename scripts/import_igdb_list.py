import os
import time
from app import app
from extensions import db
from models import EShopMapping
from services.igdb_service import IGDBService

def import_switch_titles():
    igdb = IGDBService()
    
    with app.app_context():
        print("🚀 開始從 IGDB 獲取 Switch 遊戲清單...")
        
        # 我們分批抓取，每批 500 筆
        total_needed = 2000
        offset = 0
        imported_count = 0
        
        while offset < total_needed:
            print(f"📡 正在抓取第 {offset} - {offset + 500} 筆資料...")
            games = igdb.get_popular_switch_games(limit=500, offset=offset)
            
            if not games:
                print("🏁 找不到更多遊戲，提前結束。")
                break
                
            batch_new_count = 0
            for g in games:
                # 避免重複導入
                existing = EShopMapping.query.filter_by(igdb_id=g['id']).first()
                if not existing:
                    new_mapping = EShopMapping(igdb_id=g['id'], game_name=g['name'])
                    db.session.add(new_mapping)
                    imported_count += 1
                    batch_new_count += 1
            
            db.session.commit()
            print(f"📦 本批次新增: {batch_new_count} 筆")
            
            # 重要：不論本批次有沒有新資料，offset 都要前進，否則會永遠抓同一批
            offset += 500
            time.sleep(1)

        print(f"✅ 成功導入 {imported_count} 筆新遊戲索引至 Mapping 表！")

if __name__ == "__main__":
    os.environ['PYTHONPATH'] = '.'
    import_switch_titles()