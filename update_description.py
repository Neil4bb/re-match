import json
from app import app
from extensions import db
from models import EShopMapping

def update_descriptions():
    # 1. 載入 JSON
    try:
        with open('HK.zh.json', 'r', encoding='utf-8') as f:
            data = json.load(f) # 這裡得到的是一個大字典
    except FileNotFoundError:
        print("❌ 找不到 HK.zh.json")
        return

    with app.app_context():
        print("🚀 開始根據 JSON Key (NSUID) 更新 Description...")
        update_count = 0

        # 🌟 修正：遍歷字典的 Key (nsuid) 與 Value (info)
        for nsuid, info in data.items():
            # 只處理 7001 開頭的正規遊戲
            if not nsuid.startswith('7001'):
                continue

            # 取得完整的長描述
            full_desc = info.get('description')
            
            if not full_desc:
                continue

            # 2. 尋找資料庫中對應的紀錄
            mapping = EShopMapping.query.filter_by(nsuid=nsuid).first()

            if mapping:
                # 3. 將原本短小的 intro 替換成完整的 description
                mapping.intro = full_desc
                update_count += 1
                
                if update_count % 100 == 0:
                    print(f"🔄 已更新 {update_count} 筆...")

        try:
            db.session.commit()
            print(f"✨ 更新完成！共修復 {update_count} 筆遊戲長描述。")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Commit 失敗: {e}")

if __name__ == "__main__":
    update_descriptions()