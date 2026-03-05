from app import app
from models import db, Game

with app.app_context():
    # 建立一個測試遊戲物件
    test_game = Game(name="薩爾達傳說:曠野之息", platform="Switch")

    db.session.add(test_game)
    db.session.commit()

    # 查詢是否成功
    game = Game.query.filter_by(name="薩爾達傳說:曠野之息").first()
    if game:
        print(f"成功存入! ID:{game.id}, 遊戲: {game.name}, 平台: {game.platform}")