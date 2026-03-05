from app import app
from extensions import db
from models import Game, UserAsset

def setup_mariocart8():
    with app.app_context():
        # 建立瑪利歐賽車 8 的底稿
        mc8 = Game(name="瑪利歐賽車 8 豪華版", eshop_nsuid="70070000013724")
        db.session.add(mc8)
        db.session.commit()
        print("✅ 測試遊戲已歸位，現在可以去首頁點追蹤了！")

if __name__ == "__main__":
    setup_mariocart8()