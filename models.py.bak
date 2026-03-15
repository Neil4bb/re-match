from extensions import db
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


# 1. 遊戲標準資料表 (Master Games)
class Game(db.Model):
    __tablename__ = 'games'
    id = db.Column(db.Integer, primary_key=True)  # IGDB ID
    name = db.Column(db.String(200), nullable=False) # 英文原名
    chinese_name = db.Column(db.String(200)) # 中文譯名
    platform = db.Column(db.String(50))
    cover_url = db.Column(db.String(500))
    eshop_nsuid = db.Column(db.String(20), nullable=True)
    historical_low = db.Column(db.Float, default=0)
    # 關聯：一個遊戲可以有多個行情紀錄
    prices = db.relationship('MarketPrice', backref='game', lazy=True)
    user_assets = db.relationship('UserAsset',backref='game', lazy=True)

    def get_market_analysis(self):
        """利用 relationship 進行記憶體內過濾，不再重複 query"""
        # 1. 從關聯好的 prices 中挑出資料，並按時間排序 (created_at)
        # 我們直接對 self.prices 這個 list 進行操作
        sorted_prices = sorted(self.prices, key=lambda p: p.created_at, reverse=True)
        
        # 2. 找出最新的一筆 eShop 與 PTT 紀錄
        latest_eshop = next((p for p in sorted_prices if p.source == 'eShop'), None)
        # 注意：這裡修正為 'PTT'，對位你的爬蟲來源
        latest_ptt = next((p for p in sorted_prices if p.source == 'PTT'), None)
        
        e_price = latest_eshop.price if latest_eshop else None
        r_price = latest_ptt.price if latest_ptt else None
        
        # 3. 計算建議 (維持你原本的邏輯)
        suggestion = "資料不足"
        diff = 0
        if e_price and r_price:
            diff = r_price - e_price
            suggestion = "推薦買數位版" if diff > 0 else "推薦買實體版"
            
        return {
            'eshop': e_price or "N/A",   # 確保沒資料時回傳前端等待的 "N/A"
            'retail': r_price or "N/A",  # 對齊 index.html 的 analysis.retail
            'suggestion': suggestion,
            'diff': abs(diff),
            'has_both': e_price is not None and r_price is not None,
            'is_digital_cheaper': diff > 0
        }
    
# 2. 市場行情紀錄表 (Market Prices)
class MarketPrice(db.Model):
    __tablename__ = 'market_prices'
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(50), default="PTT") # 預設為 PTT，未來可擴充
    source_url = db.Column(db.String(500)) # 存下 PTT 貼文的網址，方便以後檢驗真偽
    title = db.Column(db.String(200)) # 額外保留原始標題，這對「預警系統」除錯很有幫助
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    
    # 與資產建立連結：透過 current_user.assets 即可抓到該使用者的所有 UserAsset
    assets = db.relationship('UserAsset', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class UserAsset(db.Model):
    __tablename__ = 'user_assets'
    id = db.Column(db.Integer, primary_key=True)
    
    # 關鍵：新增 User 關聯
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    
    platform = db.Column(db.String(20), nullable=False, default='Switch') 
    status = db.Column(db.String(20), nullable=False, default='owned') # 'owned' 或 'wishlist' 
    
    purchase_price = db.Column(db.Integer) 
    target_price = db.Column(db.Integer) 
    alert_threshold = db.Column(db.Float, default=0.2) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_analysis(self):
        """核心邏輯封裝：針對持有或願望清單回傳不同建議"""
        # 1. 抓取最新價格
        # 注意：這裡改用 self.game.prices 存取，前提是 Game 模型有定義 relationship
        ptt_price = next((p.price for p in reversed(self.game.prices) if p.source == 'PTT'), None)
        target_src = 'eShop' if self.platform == 'Switch' else 'PS_Store'
        digital_price = next((p.price for p in reversed(self.game.prices) if p.source == target_src), None)
        
        status = "success" 
        reason = "狀態良好"
        
        # 2. 判定邏輯 (區分狀態)
        if self.status == 'owned':
            # 已持有時的預警邏輯 (維持你原本的邏輯)
            loss_threshold = (self.purchase_price or 0) * 0.7
            if digital_price and ptt_price and digital_price < ptt_price:
                status = "danger"
                reason = "流動性死結：數位比二手便宜"
            elif ptt_price and ptt_price < loss_threshold:
                status = "warning"
                reason = "殘值跌破 70%"
        
        elif self.status == 'wishlist':
            # 願望清單邏輯：價格跌破目標價時給予提示
            if ptt_price and self.target_price and ptt_price <= self.target_price:
                status = "info"
                reason = f"實體版已達標！目前 NT$ {int(ptt_price)}"
            elif digital_price and self.target_price and digital_price <= self.target_price:
                status = "info" # 建議買入
                reason = f"數位版已達標！目前 NT$ {int(digital_price)}"
            else:
                reason = "等待特價中"
            
        return {"status": status, "reason": reason, "ptt": ptt_price, "digital": digital_price}