from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from extensions import db
from models import db, Game, GamePlatformID, MarketPrice, User, UserAsset
import os
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload


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

# --- 1. 首頁路由：提供初始 50 筆資料渲染 ---
@app.route('/')
def index():
    platform_mode = request.args.get('platform', 'ns')
    # 首頁一律先載入第 1 頁
    page = 1 
    
    # 🌟 使用 joinedload 優化 N+1 問題
    query = Game.query.options(joinedload(Game.platform_ids), joinedload(Game.prices))
    
    # 根據平台過濾
    if platform_mode == 'ns':
        query = query.join(GamePlatformID).filter(GamePlatformID.platform.like('%Switch%'))
    else:
        query = query.join(GamePlatformID).filter(
            (GamePlatformID.platform.like('%PS%')) | 
            (GamePlatformID.platform.like('%PlayStation%'))
        )

    # 取得前 50 筆
    pagination = query.distinct().paginate(page=page, per_page=50, error_out=False)
    
    return render_template('index.html', 
                           games=pagination.items, 
                           current_platform=platform_mode)

# --- 2. API 路由：供無限捲動使用 ---
@app.route('/api/games')
def api_games():
    platform_mode = request.args.get('platform', 'ns')
    page = request.args.get('page', 1, type=int)
    
    query = Game.query.options(joinedload(Game.platform_ids), joinedload(Game.prices))
    
    if platform_mode == 'ns':
        query = query.join(GamePlatformID).filter(GamePlatformID.platform.like('%Switch%'))
    else:
        query = query.join(GamePlatformID).filter(
            (GamePlatformID.platform.like('%PS%')) | 
            (GamePlatformID.platform.like('%PlayStation%'))
        )

    pagination = query.distinct().paginate(page=page, per_page=50, error_out=False)
    
    # 🌟 格式化回傳 JSON 資料
    game_list = []
    for game in pagination.items:
        # 呼叫 models.py 中的分析邏輯
        analysis = game.get_market_analysis(platform_mode=platform_mode)
        game_list.append({
            'id': game.id,
            'chinese_name': game.chinese_name or game.name,
            'name': game.name,
            'cover_url': game.cover_url,
            'digital_price': analysis['eshop'] if platform_mode == 'ns' else analysis['eshop'], # 這裡 eshop 欄位其實就是數位價
            'retail_price': analysis['retail'],
            'suggestion': analysis['suggestion'],
            'is_digital_cheaper': analysis['is_digital_cheaper'],
            'diff': analysis['diff'] if analysis['has_both'] else 0
        })
    
    return jsonify({
        'games': game_list,
        'has_next': pagination.has_next
    })

# --- 修改原本的遊戲詳情路由 ---
@app.route('/game/<int:game_id>')
def game_detail(game_id):
    # 1. 只從本地資料庫抓取遊戲基本資訊
    game = Game.query.get_or_404(game_id)
    
    # 2. 直接呼叫我們之前寫好的私有方法（只格式化現有資料，不爬蟲）
    # 🌟 關鍵：直接用 manager._get_cached_market_data 繞過 Live Fetch 判定
    market_data = manager._get_cached_market_data(game_id)
    
    # 3. 提取圖表需要的歷史資料
    history = market_data.get('history', [])
    
    # 依照日期排序（由舊到新）
    history_sorted = sorted(history, key=lambda x: x['date'])
    
    labels = [h['date'] for h in history_sorted]
    prices = [h['price'] for h in history_sorted]

    # 4. 渲染頁面（這時頁面會秒開，即使沒價格也只會顯示 "暫無行情"）
    return render_template(
        'game_detail.html', 
        game=game, 
        market_data=market_data, 
        labels=labels,           
        prices=prices            
    )

# --- 新增：手動更新 API (對應第三點) ---
@app.route('/api/game/<int:game_id>/refresh', methods=['POST'])
def refresh_game_price(game_id):
    try:
        # 強制執行爬蟲
        game = Game.query.get_or_404(game_id)
        new_data = manager.get_single_game_market_data(game_id, name=game.name, force_refresh=True)
        return jsonify({"status": "success", "data": new_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


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
    # 🌟 增加一個可選參數，讓 JS 決定要不要強制刷新
    force = request.args.get('force', 'false').lower() == 'true'
    
    clean_id = str(game_id).strip().lower()
    
    # 情況 1: 已經有 ID 的標準路徑 (最常用)
    if clean_id.isdigit():
        # 🌟 直接呼叫 Manager，不要在那邊 ensure_game 或 find_and_store
        # Manager 內部已經有 24 小時檢查邏輯了
        data = manager.get_single_game_market_data(int(clean_id), nsuid=nsuid, name=name, force_refresh=force)
        return jsonify(data)

    # 情況 2: 真的是新遊戲 (ID 為空)
    if clean_id in ['none', 'null', '']:
        # 只有在真的沒 ID 時，才去執行沉重的「認親存檔」流程
        game = manager.find_and_store_single_game(name, nsuid)
        if game and game.id:
            data = manager.get_single_game_market_data(game.id, nsuid=nsuid, name=name, force_refresh=force)
            data['new_game_id'] = game.id
            return jsonify(data)
            
    return jsonify({'status': 'error', 'message': '無效的請求'}), 400

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