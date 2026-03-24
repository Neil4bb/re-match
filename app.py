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

# 🌟 新增以下連線池優化設定
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_recycle": 280,  # 每 280 秒自動回收連線（低於 MySQL 預設的 300秒）
    "pool_pre_ping": True, # 在執行 SQL 前先測試連線是否還活著
}

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
    # 🌟 使用 Session.get 取代 query.get
    return db.session.get(User, int(user_id))

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

#
@app.route('/game/<int:game_id>')
def game_detail(game_id):
    game = Game.query.get_or_404(game_id)
    # 這裡確保使用的是你從爬蟲或資料庫抓取的歷史紀錄
    prices = MarketPrice.query.filter_by(game_id=game_id).order_by(MarketPrice.created_at).all()
    
    def process_history(price_list, target_platform):
        digital_map = {}
        ptt_map = {}
        
        digital_src = 'eShop' if target_platform == 'ns' else 'PS_Store'
        ptt_keyword = '[NS' if target_platform == 'ns' else '[PS'

        for p in price_list:
            # 🌟 強制轉為字串日期 '2026-03-24'
            date_str = p.created_at.strftime('%Y-%m-%d')
            
            if p.source == digital_src:
                digital_map[date_str] = p.price
            elif p.source == 'PTT' and ptt_keyword in (p.title or ''):
                ptt_map[date_str] = p.price
        
        # 取得排序後的日期聯集
        all_dates = sorted(list(set(digital_map.keys()) | set(ptt_map.keys())))
        
        # 🌟 關鍵：確保 data 陣列長度與 labels 完全一致
        return {
            'labels': all_dates,
            'digital_values': [digital_map.get(d, None) for d in all_dates],
            'ptt_values': [ptt_map.get(d, None) for d in all_dates]
        }

    ns_chart = process_history(prices, 'ns')
    ps_chart = process_history(prices, 'ps')

    return render_template('game_detail.html', 
                           game=game, 
                           ns_chart=ns_chart, 
                           ps_chart=ps_chart)

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
    query = request.args.get('q', '').strip()
    
    results = []
    if query:
        # 1. 呼叫我們新寫的「智慧搜尋」，它會回傳字典清單
        results = manager.search_games(query)
    
    return render_template('search_results.html', games=results, query=query)


# app.py

@app.route('/api/market/<game_id>')
def get_market_api(game_id):
    nsuid = request.args.get('nsuid')
    name = request.args.get('name')
    # 🌟 增加一個可選參數，讓 JS 決定要不要強制刷新
    force = request.args.get('force', 'false').lower() == 'true'
    
    clean_id = str(game_id).strip().lower()

    # 🌟 新增：處理虛擬 ID 路徑 (解決認親前的 400 錯誤)
    # 當前端傳入 nsuid_7001... 時，代表這是本地字典有、但 IGDB 尚未綁定的遊戲
    if clean_id.startswith('nsuid_'):
        real_nsuid = clean_id.replace('nsuid_', '')
        print(f"🔗 [Virtual ID Route] 偵測到虛擬 ID，啟動強制認親: {real_nsuid}")
        
        # 執行認親存檔流程
        game = manager.find_and_store_single_game(name, real_nsuid)
        if game and game.id:
            # 認親成功後，改用真正的 ID 執行查價
            data = manager.get_single_game_market_data(game.id, nsuid=real_nsuid, name=name, force_refresh=force)
            data['new_game_id'] = game.id # 讓前端更新 DOM 中的 ID
            return jsonify(data)
        else:
            return jsonify({'status': 'error', 'message': '認親失敗，無法獲取行情'}), 404
    
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

# --- 資產頁  ---
@app.route('/my-assets')
@login_required
def my_assets():
    platform_mode = request.args.get('platform', 'ns') # 'ns' 或 'ps'
    view_mode = request.args.get('view', 'wishlist')
    
    # 1. 抓取該使用者的資產，並預先載入遊戲與平台 ID (優化效ne)
    user_assets = UserAsset.query.filter_by(user_id=current_user.id)\
        .join(Game).options(joinedload(UserAsset.game).joinedload(Game.platform_ids))\
        .all()
    
    # 2. 定義平台判定邏輯
    def match_platform(game):
        p_ids = [p.platform.lower() for p in game.platform_ids]
        if platform_mode == 'ns':
            return any('switch' in p or 'nintendo' in p for p in p_ids)
        else:
            return any('ps' in p or 'playstation' in p for p in p_ids)

    # 3. 執行「狀態」與「平台」雙重過濾
    filtered_assets = [
        a for a in user_assets 
        if a.status == view_mode and match_platform(a.game)
    ]
    
    # 為了維持模板中的數量統計準確，我們分開計算
    wishlist_count = len([a for a in user_assets if a.status == 'wishlist' and match_platform(a.game)])
    owned_count = len([a for a in user_assets if a.status == 'owned' and match_platform(a.game)])
    
    return render_template('assets.html', 
                           display_list=filtered_assets, 
                           wishlist_count=wishlist_count,
                           owned_count=owned_count,
                           current_platform=platform_mode, 
                           current_view=view_mode)

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
            platform='Switch' # 預設平台，可根據需求調整
        )
        db.session.add(new_asset)
        db.session.commit()
    
    # 🌟 關鍵修正：如果是 JavaScript 發送的 POST 請求，回傳 JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'POST':
        return jsonify({
            'status': 'success',
            'message': '已加入願望清單',
            'game_id': game_id
        }), 200
    
    # 傳統點擊連結則維持跳轉
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
    
    # 安全檢查
    if asset.user_id != current_user.id:
        flash('權限不足', 'danger')
        return redirect(url_for('my_assets'))
    
    db.session.delete(asset)
    db.session.commit()
    flash('已從資產箱移除', 'info')
    return redirect(url_for('my_assets',
                            platform=request.args.get('platform', 'ns'),
                            view=request.args.get('view', 'wishlist')))

# --- 切換資產狀態 ---
@app.route('/toggle_asset/<int:asset_id>', methods=['POST'])
@login_required
def toggle_asset(asset_id):
    # 使用與 load_user 一致的推薦寫法
    asset = db.session.get(UserAsset, asset_id)
    
    if not asset or asset.user_id != current_user.id:
        flash('找不到該資產或權限不足', 'danger')
        return redirect(url_for('my_assets'))
    
    origin_view = asset.status

    # 🌟 切換邏輯：wishlist 變 owned / owned 變 wishlist
    if asset.status == 'wishlist':
        asset.status = 'owned'
        # 切換到已持有時，將原本的「目標價」轉為「購入價」作為預設值 (選配邏輯)
        if asset.target_price:
            asset.purchase_price = asset.target_price
        flash(f'已將 {asset.game.chinese_name or asset.game.name} 移至已持有', 'success')
    else:
        asset.status = 'wishlist'
        flash(f'已將 {asset.game.chinese_name or asset.game.name} 移至希望清單', 'info')

    db.session.commit()
    
    # 保持在目前的平台分頁 (ns 或 ps)
    platform = 'ns' if asset.platform == 'Switch' else 'ps'
    
    # 導向切換後的視圖
    return redirect(url_for('my_assets', platform=platform, view=origin_view))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # 務必確保 host='0.0.0.0' 且 debug=False
    app.run(host='0.0.0.0', port=port, debug=True)