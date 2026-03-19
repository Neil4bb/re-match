import time
from app import app
from extensions import db
from models import Game, EShopMapping
from services.igdb_service import IGDBService

def fix_2000_mappings():
    igdb = IGDBService()
    with app.app_context():
        # 1. 直接針對那 2000 筆待處理的 Mapping 進行遍歷
        # 條件：nsuid 為空（代表還沒爬到）且 game_name 是英文
        mappings_to_fix = EShopMapping.query.filter(EShopMapping.nsuid == None).all()
        
        total = len(mappings_to_fix)
        print(f"🚀 準備針對 {total} 筆 EShopMapping 進行中文名稱修復...")

        for index, mapping in enumerate(mappings_to_fix, 1):
            try:
                print(f"[{index}/{total}] 🔍 處理中: {mapping.game_name}")
                
                # 改為：嘗試簡化關鍵字
                clean_name = mapping.game_name.split(':')[0].split('-')[0].strip()
                results = igdb.search_game(clean_name) 

                # 如果還是沒有，再嘗試更短的關鍵字
                if not results and len(clean_name.split()) > 2:
                    short_name = " ".join(clean_name.split()[:2])
                    results = igdb.search_game(short_name)
                
                if results:
                    # 抓取第一筆結果（通常搜尋最準確的那筆）
                    best_match = results[0]
                    chinese_name = best_match.get('chinese_name')
                    
                    if chinese_name:
                        # 3. 更新 Game 表（為了讓爬蟲 fetch_nsuid_task 能抓到中文）
                        # 先看 Game 表有沒有這一筆
                        game = Game.query.get(mapping.igdb_id)
                        if game:
                            game.chinese_name = chinese_name
                            print(f"   ✅ 已更新 Game 表中文名: {chinese_name}")
                        else:
                            # 如果 Game 表沒這筆，就建一筆新的
                            new_game = Game(
                                id=mapping.igdb_id,
                                name=mapping.game_name,
                                chinese_name=chinese_name
                            )
                            db.session.add(new_game)
                            print(f"   🆕 已在 Game 表新建中文資料: {chinese_name}")
                        
                        db.session.commit()
                    else:
                        print(f"   ⚠️ IGDB 有結果但無中文名稱")
                else:
                    print(f"   ❌ IGDB 查無此遊戲")
                
            except Exception as e:
                db.session.rollback()
                print(f"   💥 錯誤: {e}")
            
            time.sleep(0.5) # 頻率控制

if __name__ == "__main__":
    fix_2000_mappings()