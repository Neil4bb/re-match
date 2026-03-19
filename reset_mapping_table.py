from app import app, db
from models import EShopMapping

with app.app_context():
    try:
        # 使用 SQLAlchemy 的方式清空資料表
        num_rows_deleted = db.session.query(EShopMapping).delete()
        db.session.commit()
        print(f"✅ 成功刪除 {num_rows_deleted} 筆舊資料！")
    except Exception as e:
        db.session.rollback()
        print(f"❌ 發生錯誤: {e}")