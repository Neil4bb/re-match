import os
import unicodedata
from sqlalchemy import create_engine, Table, MetaData
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# 1. 載入本地 .env
load_dotenv()

# 2. 從 .env 抓取拆開的變數
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST")  # 你剛才提供的這行
port = os.getenv("DB_PORT", "3306")
dbname = os.getenv("DB_NAME")

# 3. 拼湊成完整的 SQLAlchemy URL
# 格式：mysql+pymysql://user:password@host:port/dbname
db_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{dbname}"

print(f"📡 嘗試連線至主機: {host}")

try:
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # 測試連線
    conn = engine.connect()
    conn.close()
    print("✅ 連線成功，開始處理資料...")

    def migrate_to_nfkc():
        metadata = MetaData()
        # 反射資料表結構
        mapping_table = Table('eshop_mappings', metadata, autoload_with=engine)
        game_table = Table('games', metadata, autoload_with=engine)

        # 1. 處理 EShopMapping
        mappings = session.execute(mapping_table.select()).all()
        for m in mappings:
            new_gn = unicodedata.normalize('NFKC', m.game_name) if m.game_name else None
            new_en = unicodedata.normalize('NFKC', m.english_name) if m.english_name else None
            
            if new_gn != m.game_name or new_en != m.english_name:
                session.execute(
                    mapping_table.update().where(mapping_table.c.id == m.id).values(
                        game_name=new_gn,
                        english_name=new_en
                    )
                )

        # 2. 處理 Game
        games = session.execute(game_table.select()).all()
        for g in games:
            new_cn = unicodedata.normalize('NFKC', g.chinese_name) if g.chinese_name else None
            new_n = unicodedata.normalize('NFKC', g.name) if g.name else None

            if new_cn != g.chinese_name or new_n != g.name:
                session.execute(
                    game_table.update().where(game_table.c.id == g.id).values(
                        chinese_name=new_cn,
                        name=new_n
                    )
                )

        session.commit()
        print("🎉 RDS 資料標準化完成！")

    migrate_to_nfkc()

except Exception as e:
    print(f"❌ 錯誤: {e}")
finally:
    if 'session' in locals():
        session.close()