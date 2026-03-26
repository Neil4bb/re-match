from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from extensions import db
from models import db, Game, GamePlatformID, MarketPrice, User, UserAsset
import os
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload
from collections import defaultdict


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
            'digital_price': analysis['digital'],
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
@app.route('/game/<game_id>')
def game_detail(game_id):
    str_id = str(game_id).strip()
    
    # 🌟 增加對 'None' 或 'null' 的防禦
    if not str_id or str_id.lower() in ['none', 'null']:
        flash("無效的遊戲 ID", "danger")
        return redirect(url_for('index'))
    
    if str_id.startswith('nsuid_'):
        # ... 原有的認親邏輯 ...
        real_nsuid = str_id.replace('nsuid_', '')
        game = manager.find_and_store_single_game("新搜尋遊戲", real_nsuid)
    else:
        try:
            # 🌟 確保是數字才轉換
            game = db.session.get(Game, int(str_id))
        except ValueError:
            flash("遊戲 ID 格式錯誤", "danger")
            return redirect(url_for('index'))
            
    if not game:
        flash("找不到該遊戲", "danger")
        return redirect(url_for('index'))
        
    prices = MarketPrice.query.filter_by(game_id=game_id).order_by(MarketPrice.created_at).all()
    
    def process_history(price_list, target_platform):
        
        # 用字典將同日期的資料歸類
        daily_groups = defaultdict(list)
        digital_src = 'eShop' if target_platform == 'ns' else 'PS_Store'
        ptt_keyword = '[NS' if target_platform == 'ns' else '[PS'

        for p in price_list:
            # 🌟 強制轉為字串日期 '2026-03-24'
            date_key = p.created_at.strftime('%Y-%m-%d')

            if p.source == digital_src:
                daily_groups[(date_key, 'digital')].append(p)
            elif p.source == 'PTT' and ptt_keyword in (p.title or ''):
                daily_groups[(date_key, 'ptt')].append(p)
        
        # 使用字典暫存，最後再統一排序日期
        temp_data = defaultdict(lambda: {'digital': None, 'ptt': None})
        
        # 遍歷所有組別 (例如: ('2026-03-26', 'digital'), ('2026-03-26', 'ptt'))
        for (date_str, s_type) in daily_groups.keys():
            group = sorted(daily_groups[(date_str, s_type)], key=lambda x: x.created_at)
            
            indices = [0] # 建立空白清單，預設拿第一筆
            if len(group) > 1:
                indices.append(-1) # 如果有兩筆以上，拿最後一筆
                
            for idx in indices:
                p = group[idx]
                # 建立唯一的標籤：日期 + 時間 (精確到秒或分以區隔點位)
                full_ts = p.created_at.strftime('%Y-%m-%d %H:%M:%S')
                
                if s_type == 'digital':
                    temp_data[full_ts]['digital'] = p.price
                else:
                    temp_data[full_ts]['ptt'] = p.price

        # 3. 依照時間戳記排序，生成最終陣列
        sorted_ts = sorted(temp_data.keys())
        
        return {
            'labels': [f"{ts[:-6]}h" for ts in sorted_ts], # ts[:-6] 是裁切掉 ":MM:SS" (分與秒)，只保留到小時
            'digital_values': [temp_data[ts]['digital'] for ts in sorted_ts],
            'ptt_values': [temp_data[ts]['ptt'] for ts in sorted_ts]
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
    
    # 1. 抓取該使用者的所有資產 (預先載入 game 加速)
    user_assets = UserAsset.query.filter_by(user_id=current_user.id)\
        .options(joinedload(UserAsset.game))\
        .all()
    
    # 2. 🌟 關鍵改動：直接對比 UserAsset 裡存的平台標籤
    # 這樣 Switch 存的就只會出現在 ns 分頁，PS 存的只會出現在 ps 分頁
    db_platform = 'Switch' if platform_mode == 'ns' else 'PlayStation'
    
    filtered_assets = [
        a for a in user_assets 
        if a.status == view_mode and a.platform == db_platform
    ]
    
    # 3. 統計數量也要同步修改，確保導覽列數字正確
    wishlist_count = len([a for a in user_assets if a.status == 'wishlist' and a.platform == db_platform])
    owned_count = len([a for a in user_assets if a.status == 'owned' and a.platform == db_platform])
    
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
    # 1. 取得前端傳來的平台代碼 (ns 或 ps)，預設為 ns
    platform_code = request.args.get('platform', 'ns').lower()

    db_platform = 'Switch' if platform_code == 'ns' else 'PlayStation'

    exists = UserAsset.query.filter_by(
        user_id=current_user.id,
        game_id=game_id,
        platform=db_platform
    ).first()
    
    if not exists:
        new_asset = UserAsset(
            user_id=current_user.id,
            game_id=game_id,
            status='wishlist',
            platform=db_platform
        )
        db.session.add(new_asset)
        db.session.commit()
    
    # 🌟 關鍵修正：如果是 JavaScript 發送的 POST 請求，回傳 JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'POST':
        return jsonify({
            'status': 'success',
            'message': f'已加入 {db_platform} 願望清單',
            'game_id': game_id
        }), 200
    
    flash(f'成功加入 {db_platform} 願望清單！')
    return redirect(url_for('index', platform=platform_code))

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
    platform_url_code = 'ns' if asset.platform == 'Switch' else 'ps'
    
    # 導向切換後的視圖
    return redirect(url_for('my_assets', platform=platform_url_code, view=origin_view))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # 務必確保 host='0.0.0.0' 且 debug=False
    app.run(host='0.0.0.0', port=port, debug=True)