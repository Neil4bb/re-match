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
        """
        提供給首頁與搜尋結果的通用市場分析邏輯。
        platform_mode: 'ns' (Switch) 或 'ps' (PlayStation)
        """
        # 1. 根據模式決定數位價與 PTT 關鍵字
        if platform_mode == 'ns':
            target_source = 'eShop'
            ptt_keyword = '[NS'
        else:
            target_source = 'PS_Store'
            ptt_keyword = '[PS'

        # 2. 取得該模式對應的最新數位價 (更名為 digital)
        digital = next((p for p in reversed(self.prices) if p.source == target_source), None)
        
        # 3. 取得該模式對應的最新 PTT 二手價 (精確匹配平台標籤)
        retail = next((p for p in reversed(self.prices) 
                    if p.source == 'PTT' and ptt_keyword in (p.title or '')), None)

        # 4. 轉換為數值
        d_price = int(digital.price) if digital else None
        r_price = int(retail.price) if retail else None

        # 5. 計算分析建議
        suggestion = "資料不足"
        diff = 0
        is_digital_cheaper = False

        if d_price and r_price:
            diff = r_price - d_price
            suggestion = "推薦買數位版" if diff > 0 else "推薦買實體版"
            is_digital_cheaper = diff > 0

        # 🌟 回傳字典中的 Key 已從 eshop 改為 digital
        return {
            'digital': d_price or "N/A",
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
    
    game = db.relationship('Game', backref=db.backref('eshop_mappings', lazy='dynamic'))

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

    #
    def status_analysis(self):
        """精準平台資產分析：統一變數名稱並整合 Debug 資訊"""
            
        # 1. 強化平台判定 (不分大小寫，包含關鍵字即判定)
        # 假設資料庫存 'Switch', 'NS', 'Nintendo' 都跑 NS 邏輯
        current_p = (self.platform or "").lower()
        
        if 'switch' in current_p or 'ns' in current_p:
            target_src, ptt_keyword = 'eShop', '[NS'
            platform_label = "Nintendo"
        else:
            # 只要不是 Switch 就跑 PS 邏輯
            target_src, ptt_keyword = 'PS_Store', '[PS'
            platform_label = "PlayStation"

        # 2. 抓取最新價格
        digital_p = next((p.price for p in reversed(self.game.prices) if p.source == target_src), None)
        ptt_p = next((p.price for p in reversed(self.game.prices) 
                    if p.source == 'PTT' and ptt_keyword in (p.title or '')), None)

        # 3. 計算當前市值
        market_prices = [p for p in [digital_p, ptt_p] if p is not None]
        current_val = min(market_prices) if market_prices else None
        
        # 🌟 [Debug Log] 增加平台標籤檢查
        print(f"--- 🔍 損益分析 Debug: {self.game.chinese_name or self.game.name} ---")
        print(f"   > 資產平台欄位內容: '{self.platform}'")
        print(f"   > 最終判定路徑: {platform_label} (搜尋 {target_src})")
        print(f"   > 購入價: {self.purchase_price} | 數位價: {digital_p} | PTT價: {ptt_p}")
        print(f"   > 判定市值 (current_val): {current_val}")

        status = "success"
        reason = "狀態良好"
        
        # --- 4. 判定邏輯：已持有 (owned) ---
        if self.status == 'owned':
            loss_limit = (self.purchase_price or 0) * 0.7  # 70% 門檻
            
            # A. 流動性陷阱 (數位特價比二手實體還便宜)
            if digital_p and ptt_p and digital_p < ptt_p:
                status = "danger"
                reason = f"流動性死結：數位版僅 NT$ {int(digital_p)}"
            
            # B. 價值大幅縮水 (只要市場最低價跌破 70% 門檻)
            elif current_val and current_val < loss_limit:
                status = "warning"
                reason = f"資產縮水：目前市值約 NT$ {int(current_val)}"
                
        # --- 5. 判定邏輯：希望清單 (wishlist) ---
        elif self.status == 'wishlist':
            is_ptt_deal = ptt_p and self.target_price and ptt_p <= self.target_price
            is_digital_deal = digital_p and self.target_price and digital_p <= self.target_price

            if is_ptt_deal and is_digital_deal:
                cheaper_type = "實體版" if ptt_p <= digital_p else "數位版"
                status = "info"
                reason = f"雙重達標！{cheaper_type}最划算 (NT$ {int(min(ptt_p, digital_p))})"
            elif is_ptt_deal:
                status = "info"
                reason = f"實體版已達標！目前 NT$ {int(ptt_p)}"
            elif is_digital_deal:
                status = "info"
                reason = f"數位版已達標！目前 NT$ {int(digital_p)}"
            else:
                reason = "等待特價中"
                
        return {
            "status": status, 
            "reason": reason, 
            "ptt": ptt_p, 
            "digital": digital_p
        }