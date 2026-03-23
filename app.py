from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from extensions import db
from models import db, Game, MarketPrice, User, UserAsset
import os
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)

migrate = Migrate(app, db)

from services.main_service import MainManager
manager = MainManager()

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')

# 設定 SQLite 資料庫路徑
#basedir = os.path.abspath(os.path.dirname(__file__))
#app.config['SQLALCHEMY_DATABASE_PATH'] = os.path.join(basedir, 'database.db')
#app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + app.config['SQLALCHEMY_DATABASE_PATH']
#app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# RDS 資訊
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')

app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:3306/{DB_NAME}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# 開啟 SQLite 的 WAL 模式 (增強並發效能)
with app.app_context():
    db.create_all()
    print("✅ 成功連線到 AWS RDS！資料表已在雲端建立完成。")
    # 執行 WAL 模式指令
    #db.session.execute(db.text("PRAGMA journal_mode=WAL;"))
    #db.session.commit()
    #print("資料庫初始化完成，已開啟 WAL 模式！")

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
    platform_mode = request.args.get('platform', 'ns')
    page = request.args.get('page', 1, type=int) # 取得當前頁碼
    
    from sqlalchemy.orm import joinedload
    from models import GamePlatformID

    # 1. 使用 joinedload 解決載入過慢的 N+1 問題
    query = Game.query.options(joinedload(Game.platform_ids), joinedload(Game.prices))
    
    # 2. 修改過濾邏輯，確保 PS 遊戲能被搜到
    if platform_mode == 'ns':
        # 匹配包含 Switch 字眼的平台
        query = query.join(GamePlatformID).filter(GamePlatformID.platform.like('%Switch%'))
    else:
        # 擴大 PS 的匹配範圍，包含 PS, PlayStation, PS4, PS5
        query = query.join(GamePlatformID).filter(
            (GamePlatformID.platform.like('%PS%')) | 
            (GamePlatformID.platform.like('%PlayStation%'))
        )

    # 3. 使用分頁 (每頁 50 筆)，解決載入過久的問題
    pagination = query.distinct().paginate(page=page, per_page=50, error_out=False)
    games = pagination.items
    
    return render_template('index.html', 
                           games=games, 
                           pagination=pagination, 
                           current_platform=platform_mode)
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
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user:
            # 檢查密碼比對
            is_correct = user.check_password(password)
            print(f"DEBUG: 使用者 {username} 存在, 密碼比對結果: {is_correct}")
            if is_correct:
                login_user(user)
                return redirect(url_for('index'))
        else:
            print(f"DEBUG: 找不到使用者 {username}")
            
        flash('帳號或密碼錯誤')
    return render_template('login.html')

# --- 登出功能 ---
@app.route('/logout')
@login_required
def logout():
    logout_user() # 銷毀 Session
    return redirect(url_for('login'))



@app.route('/search')
def search():
    query = request.args.get('q', '') 
    
    results = []
    if query:
        # 1. 呼叫我們新寫的「智慧搜尋」，它會回傳字典清單
        results = manager.search_games(query)
        
        # 2. 選配：如果你希望「搜到就存」的舊行為不變
        # 你可以對 results 做迴圈呼叫 store_game_logic
        # 但我建議不要，讓「點擊詳情」去觸發儲存會更流暢。
    
    return render_template('search_results.html', games=results, query=query)


# app.py

@app.route('/api/market/<game_id>')
def get_market_api(game_id):
    nsuid = request.args.get('nsuid')
    name = request.args.get('name')
    clean_id = str(game_id).strip().lower()

    print(f"📡 收到查價請求: ID={game_id}, NSUID={nsuid}, Name={name}")

    try:
        # 情況 1: 如果 game_id 是純數字 (已有綁定 ID)
        if clean_id.isdigit():
            # 🌟 關鍵修改：呼叫時必須把抓到的 nsuid 傳進去！
            data = manager.get_single_game_market_data(int(clean_id), nsuid=nsuid, name=name)
            return jsonify(data)

        # 情況 2: 如果 game_id 是 'none' 或 'null' (需要自動綁定)
        if clean_id in ['none', 'null', '']:
            if nsuid and name:
                print(f"🔗 正在為 {name} 執行自動綁定...")
                game = manager.find_and_store_single_game(name, nsuid)
                
                # 🌟 [關鍵修改：分流處理]
                if game:
                    # A. 綁定成功：使用正式 game.id 查價
                    data = manager.get_single_game_market_data(game.id, nsuid=nsuid, name=name)
                    data.update({'new_game_id': game.id, 'status': 'success'})
                else:
                    # B. 🌟 關鍵修正：如果 find_and_store_single_game 回傳 None (IGDB 沒搜到)
                    # 我們依然執行查價，只是 game_id 傳入 None
                    print(f"⚠️ IGDB 無匹配，執行無 ID 基礎查價 (NSUID: {nsuid})")
                    data = manager.get_single_game_market_data(None, nsuid=nsuid, name=name)
                    data.update({
                        'new_game_id': None,
                        'status': 'no_igdb_match'
                    })
                
                return jsonify(data)
            
            return jsonify({'status': 'error', 'message': '找不到 NSUID 或名稱'}), 400

    except Exception as e:
        # ... 你的錯誤處理邏輯 ...
        return jsonify({'status': 'error', 'message': str(e)}), 500

    return jsonify({'status': 'error', 'message': '無效的請求格式'}), 400

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

# 修改為同時支援 GET (原本的跳轉) 與 POST (JS 請求)
@app.route('/add_to_assets/<int:game_id>', methods=['GET', 'POST'])
@login_required
def add_to_assets(game_id):
    exists = UserAsset.query.filter_by(user_id=current_user.id, game_id=game_id).first()
    
    if not exists:
        new_asset = UserAsset(
            user_id=current_user.id,
            game_id=game_id,
            status='wishlist',
            platform='Switch'
        )
        db.session.add(new_asset)
        db.session.commit()
    
    # --- 關鍵修正：判斷請求方式 ---
    if request.method == 'POST':
        return '', 200 # 讓 JS 收到 OK 訊號
    
    # 這是給原本點擊連結的使用者導向用的
    flash('成功加入願望清單！')
    return redirect(url_for('index'))

# --- 請將以下路由加入到 app.py 中 (建議放在 add_to_assets 之後) ---

@app.route('/edit_asset/<int:asset_id>', methods=['POST'])
@login_required
def edit_asset(asset_id):
    asset = UserAsset.query.get_or_404(asset_id)
    
    # 安全檢查：確保使用者只能編輯自己的資產
    if asset.user_id != current_user.id:
        flash('權限不足', 'danger')
        return redirect(url_for('my_assets'))
    
    # 根據提交的表單內容更新欄位
    # 如果是已持有則更新購入價，如果是願望清單則更新目標價
    p_price = request.form.get('purchase_price')
    t_price = request.form.get('target_price')
    status = request.form.get('status')

    if p_price is not None: asset.purchase_price = float(p_price) if p_price else 0
    if t_price is not None: asset.target_price = float(t_price) if t_price else 0
    if status: asset.status = status
    
    db.session.commit()
    flash('資產資訊已更新！', 'success')
    return redirect(url_for('my_assets'))

@app.route('/delete_asset/<int:asset_id>', methods=['POST'])
@login_required
def delete_asset(asset_id):
    asset = UserAsset.query.get_or_404(asset_id)
    if asset.user_id == current_user.id:
        db.session.delete(asset)
        db.session.commit()
        flash('已從清單中移除。', 'info')
    return redirect(url_for('my_assets'))


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # 務必確保 host='0.0.0.0' 且 debug=False
    app.run(host='0.0.0.0', port=port, debug=True)