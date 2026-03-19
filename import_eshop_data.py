import json
from app import app, db
from models import EShopMapping

def import_all_games():
    with app.app_context():
        print("📖 正在讀取 JSON 檔案...")
        try:
            with open('HK.zh.json', 'r', encoding='utf-8') as f:
                hk_raw = json.load(f)
            with open('US.en.json', 'r', encoding='utf-8') as f:
                us_raw = json.load(f)
        except FileNotFoundError as e:
            print(f"❌ 找不到檔案: {e.filename}")
            return

        # 1. 建立美國版查找表 (內部的 id -> name)
        # 這是為了避免在迴圈中重複掃描美國版 JSON，提升效能
        us_lookup = {}
        for item in us_raw.values():
            tid = item.get('id')
            if tid:
                # 統一轉大寫字串，確保比對格式絕對一致
                us_lookup[str(tid).strip().upper()] = item.get('name')
        
        print(f"✅ 美國版索引建立完成，共計 {len(us_lookup)} 筆 Title ID 對照項目。")

        seen_nsuids = set()
        added_count = 0
        match_count = 0

        print("🔗 開始執行全量資料縫合 (僅限香港 7001 正式遊戲)...")
        
        # 2. 遍歷香港版 (依據你提供的結構，info 是內容，hk_key 是 NSUID)
        for hk_key, info in hk_raw.items():
            nsuid = info.get('nsuId')
            game_name = info.get('name')
            hk_tid = info.get('id')

            # 基本過濾：沒名稱或沒 ID 就跳過
            if not nsuid or not game_name or not hk_tid:
                continue
            
            str_nsuid = str(nsuid)
            clean_hk_tid = str(hk_tid).strip().upper()

            # 關鍵過濾：僅處理正式遊戲 (7001) 且不重複
            if str_nsuid.startswith('7001') and str_nsuid not in seen_nsuids:
                # 3. 執行精確匹配：從 lookup 表中獲取英文名稱
                english_name = us_lookup.get(clean_hk_tid)
                
                if english_name:
                    match_count += 1
                
                new_mapping = EShopMapping(
                    title_id=clean_hk_tid,
                    game_name=game_name,
                    english_name=english_name,
                    nsuid=str_nsuid,
                    icon_url=info.get('iconUrl')
                )
                
                db.session.add(new_mapping)
                seen_nsuids.add(str_nsuid)
                added_count += 1
                
                # 每 500 筆批次提交
                if added_count % 500 == 0:
                    db.session.commit()
                    print(f"已處理 {added_count} 筆...")

        db.session.commit()
        print(f"\n✅ 匯入完成！")
        print(f"📊 總計匯入: {added_count} 筆正式遊戲")
        print(f"🎯 成功匹配英文名: {match_count} 筆")
        print(f"⚠️ 只有中文名 (美國版無對應): {added_count - match_count} 筆")

if __name__ == "__main__":
    import_all_games()