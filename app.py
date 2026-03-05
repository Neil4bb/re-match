from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from extensions import db
from models import db, Game, MarketPrice, User, UserAsset
import os

app = Flask(__name__)

app.config['SECRET_KEY'] = 'dev-key-123456'

# 設定 SQLite 資料庫路徑
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_PATH'] = os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + app.config['SQLALCHEMY_DATABASE_PATH']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# 開啟 SQLite 的 WAL 模式 (增強並發效能)
with app.app_context():
    db.create_all()
    # 執行 WAL 模式指令
    db.session.execute(db.text("PRAGMA journal_mode=WAL;"))
    db.session.commit()
    print("資料庫初始化完成，已開啟 WAL 模式！")

# 初始化 LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # 未登入時嘗試進入受保護頁面會導向這裡

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- 首頁：顯示所有監控中的遊戲 ---
@app.route('/')
def index():
    games = Game.query.all()
    game_list = []
    for g in games:
        # 撈取最新的 eShop 與 Retail 價格
        eshop = MarketPrice.query.filter_by(game_id=g.id, source='eShop').order_by(MarketPrice.created_at.desc()).first()
        retail = MarketPrice.query.filter_by(game_id=g.id, source='Retail').order_by(MarketPrice.created_at.desc()).first()
        
        game_list.append({
            'id' : g.id,
            'name': g.name,
            'eshop': eshop.price if eshop else "N/A",
            'retail': retail.price if retail else "N/A",
            'nsuid': g.eshop_nsuid
        })
    return render_template('index.html', games=game_list)

# --- 註冊功能 ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('此帳號已被註冊')
            return redirect(url_for('register'))
            
        new_user = User(username=username)
        new_user.set_password(password) # 使用 generate_password_hash 加密
        db.session.add(new_user)
        db.session.commit()
        
        flash('註冊成功，請登入！')
        return redirect(url_for('login'))
    return render_template('register.html')

# --- 登入功能 ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user) # 建立 Session
            return redirect(url_for('index'))
        flash('帳號或密碼錯誤')
    return render_template('login.html')

# --- 登出功能 ---
@app.route('/logout')
@login_required
def logout():
    logout_user() # 銷毀 Session
    return redirect(url_for('login'))

@app.route('/add-to-assets/<int:game_id>')
@login_required # 確保只有登入者能執行此動作
def add_to_assets(game_id):
    # 1. 檢查該遊戲是否已存在於該使用者的清單中
    exists = UserAsset.query.filter_by(user_id=current_user.id, game_id=game_id).first()
    
    if exists:
        flash('此遊戲已在你的追蹤清單中囉！')
    else:
        # 2. 建立新的關聯紀錄，預設為願望清單 (wishlist)
        new_asset = UserAsset(
            user_id=current_user.id,
            game_id=game_id,
            status='wishlist',
            platform='Switch'  # 預設平台
        )
        db.session.add(new_asset)
        db.session.commit()
        flash('成功加入願望清單！')
    
    # 3. 完成後導回首頁
    return redirect(url_for('index'))

# --- 資產頁：僅顯示已購遊戲 ---
@app.route('/my-assets')
@login_required # 強制登入才能訪問
def my_assets():
    # 直接從 current_user 獲取其擁有的 assets
    all_user_assets = current_user.assets

    # 根據狀態分類
    owned = [a for a in all_user_assets if a.status == 'owned']
    wishlist = [a for a in all_user_assets if a.status == 'wishlist']

    return render_template('assets.html', owned=owned , wishlist=wishlist)

if __name__ == '__main__':
    app.run(debug=True)