from extensions import db
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# ----------------------------------------------------------------
# 1. 遊戲標準資料表 (整合多平台支援與模糊搜尋索引)
# ----------------------------------------------------------------
class Game(db.Model):
    __tablename__ = 'games'
    id = db.Column(db.Integer, primary_key=True)  # 使用 IGDB ID
    name = db.Column(db.String(200), nullable=False, index=True) 
    chinese_name = db.Column(db.String(200), index=True)
    cover_url = db.Column(db.String(500))
    summary = db.Column(db.Text)
    
    # 關聯：一個遊戲對應多個平台的識別碼 (例如 NSUID, PS_Store_ID)
    platform_ids = db.relationship('GamePlatformID', backref='game', lazy=True, cascade="all, delete-orphan")
    # 關聯：一個遊戲有多個來源價格
    prices = db.relationship('MarketPrice', backref='game', lazy=True, cascade="all, delete-orphan")
    # 關聯：被哪些使用者收藏或持有
    user_assets = db.relationship('UserAsset', backref='game', lazy=True)

    def get_market_analysis(self, platform_mode='ns'):
        # 1. 數位來源映射
        target_source = 'eShop' if platform_mode == 'ns' else 'PS_Store'
        
        # 2. PTT 標籤映射 (增加模糊匹配能力)
        if platform_mode == 'ns':
            ptt_platforms = ['NS', 'NS2', 'Switch', 'Nintendo Switch']
        else:
            # 涵蓋你資料庫中可能存的所有 PS 字眼
            ptt_platforms = ['PS', 'PS4', 'PS5', 'PlayStation 4', 'PlayStation 5']

        # 3. 取得最新數位價 ( reversed 確保取到最新 created_at )
        digital = next((p for p in reversed(self.prices) if p.source == target_source), None)
        
        # 4. 取得最新 PTT 價 ( 修正點：使用 in 檢查列表 )
        retail = next((p for p in reversed(self.prices) 
                    if p.source == 'PTT' and p.platform in ptt_platforms), None)

        # 轉為數字運算
        d_price = int(digital.price) if digital and digital.price else None
        r_price = int(retail.price) if retail and retail.price else None

        # 5. 價差邏輯
        suggestion = "資料不足"
        diff = 0
        is_digital_cheaper = False

        if d_price and r_price:
            diff = r_price - d_price
            suggestion = "推薦買數位版" if diff > 0 else "推薦買實體版"
            is_digital_cheaper = diff > 0

        return {
            'eshop': d_price or "N/A",
            'retail': r_price or "N/A",
            'suggestion': suggestion,
            'diff': abs(diff),
            'is_digital_cheaper': is_digital_cheaper,
            'has_both': d_price is not None and r_price is not None
        }
    
    @property
    def nsuid(self):
        for p in self.platform_ids:
            if p.platform and 'Switch' in p.platform and p.external_id:
                return p.external_id
        return None

# ----------------------------------------------------------------
# 2. 平台外部 ID 表 (例如：Switch 用 NSUID, PS 用 ProductID)
# ----------------------------------------------------------------
class GamePlatformID(db.Model):
    __tablename__ = 'game_platform_ids'
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    platform = db.Column(db.String(50), nullable=False) # 'Switch', 'PS5'
    external_id = db.Column(db.String(100)) # 存 NSUID 或其他 ID
# ----------------------------------------------------------------
# 新增. EshopMapping
# ----------------------------------------------------------------
class EShopMapping(db.Model):
    __tablename__ = 'eshop_mappings'
    
    id = db.Column(db.Integer, primary_key=True)
    # 共通的 Title ID (例如: 01007EF00011E000)
    title_id = db.Column(db.String(32), index=True, nullable=True) 
    # 香港版名稱 (中文)
    game_name = db.Column(db.String(255), nullable=False, index=True)
    # 美國版名稱 (英文) - 認親成功的關鍵
    english_name = db.Column(db.String(255), nullable=True)
    # 7001 開頭的香港 NSUID (查價用)
    nsuid = db.Column(db.String(20), unique=True, nullable=False)
    icon_url = db.Column(db.String(500), nullable=True)
    intro = db.Column(db.Text)
    
    igdb_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=True)
    
    game = db.relationship('Game', backref='eshop_mapping', uselist=False)

    @property
    def platform_ids(self):
        # 🌟 讓 Mapping 透過關聯的 game 物件去抓 platform_ids
        return self.game.platform_ids if self.game else []

    @property
    def effective_nsuid(self):
        """
        定義一個新的屬性，明確邏輯：優先抓 Game 表存好的，沒有才抓 Mapping 自己的
        """
        # 1. 檢查有沒有關聯到 Game，且 Game 下面有沒有 platform_ids
        if self.game and self.game.nsuid:
            return self.game.nsuid
        # 2. 如果沒綁定，回傳 Mapping 表自己的 nsuid 欄位
        return self.nsuid

# ----------------------------------------------------------------
# 3. 市場行情紀錄表 (加入 Platform 欄位區分平台價格)
# ----------------------------------------------------------------
class MarketPrice(db.Model):
    __tablename__ = 'market_prices'
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    platform = db.Column(db.String(50), default="Switch") # 區分這筆錢是哪家的
    price = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(50)) # 'eShop', 'PTT', 'PS_Store'
    source_url = db.Column(db.String(500))
    title = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ----------------------------------------------------------------
# 4. 使用者與資產 (維持 User 與 UserAsset 的關聯邏輯)
# ----------------------------------------------------------------
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    assets = db.relationship('UserAsset', backref='owner', lazy=True)

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class UserAsset(db.Model):
    __tablename__ = 'user_assets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    
    platform = db.Column(db.String(20), nullable=False, default='Switch') 
    status = db.Column(db.String(20), nullable=False, default='owned') 
    purchase_price = db.Column(db.Integer) 
    target_price = db.Column(db.Integer) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_analysis(self):
        """強化版資產分析：自動判斷所屬平台的數位商店"""
        # 取得最新 PTT 價格
        ptt_price = next((p.price for p in reversed(self.game.prices) if p.source == 'PTT'), None)
        
        # 根據平台動態抓數位價格
        target_src = 'eShop' if self.platform == 'Switch' else 'PS_Store'
        if self.platform == 'Xbox': target_src = 'Xbox_Store'
        
        digital_price = next((p.price for p in reversed(self.game.prices) if p.source == target_src), None)
        
        status = "success"
        reason = "狀態良好"
        
        if self.status == 'owned':
            loss_threshold = (self.purchase_price or 0) * 0.7
            if digital_price and ptt_price and digital_price < ptt_price:
                status = "danger"
                reason = "流動性死結：數位比二手便宜"
            elif ptt_price and ptt_price < loss_threshold:
                status = "warning"
                reason = "殘值跌破 70%"
        elif self.status == 'wishlist':
            if ptt_price and self.target_price and ptt_price <= self.target_price:
                status = "info"
                reason = f"實體版已達標！目前 NT$ {int(ptt_price)}"
            elif digital_price and self.target_price and digital_price <= self.target_price:
                status = "info"
                reason = f"數位版已達標！目前 NT$ {int(digital_price)}"
            else:
                reason = "等待特價中"
            
        return {"status": status, "reason": reason, "ptt": ptt_price, "digital": digital_price}