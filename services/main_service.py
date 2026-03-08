from extensions import db
from models import Game, MarketPrice, UserAsset
from services.igdb_service import IGDBService
from services.eshop_service import EShopService
from playwright.sync_api import sync_playwright

class MainManager:
    def __init__(self):
        self.igdb = IGDBService()
        self.eshop = EShopService()

    def store_game_logic(self, item):
        """將 IGDB 抓到的資料存入或更新資料庫"""
        game = db.session.get(Game, item['id'])
        if not game:
            game = Game(
                id=item['id'],
                name=item['name'],
                chinese_name=item.get('chinese_name', ''),
                cover_url=item['cover_url'],
                platform=item.get('platform_name', 'Switch')
            )
            db.session.add(game)
        return game

    def search_and_store_game(self, keyword):
        from app import app
        from services.ptt_service import PttAdapter
        
        ptt = PttAdapter()
        raw_results = self.igdb.search_game(keyword)
        if not raw_results: return []
        
        final_dict_list = []
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            page = browser.new_page()
            
            with app.app_context():
                for item in raw_results:
                    game = self.store_game_logic(item)
                    
                    # 獵殺 PTT (內文版)
                    # 傳入中文名，且只抓最新 3 筆以維持速度
                    ptt_query = game.chinese_name if game.chinese_name else game.name
                    print(f"🕵️ 正在深入 PTT 內文獵殺價格: {ptt_query}...")
                    
                    try:
                        # 限制 limit=3 避免請求過多
                        ptt_results = ptt.search_game_prices(ptt_query, limit=3, target_game=ptt_query)
                        for r in ptt_results:
                            if not MarketPrice.query.filter_by(game_id=game.id, title=r['title']).first():
                                db.session.add(MarketPrice(
                                    game_id=game.id, price=r['price'], source="PTT", title=r['title']
                                ))
                    except Exception as e:
                        print(f"⚠️ PTT 內文獵殺失敗: {e}")

                    # 2. 獵殺 eShop UID
                    if not game.eshop_nsuid:
                        game.eshop_nsuid = self.eshop.search_nsuid(page, item['name'], item.get('chinese_name'))
                    
                    # 3. 獲取 eShop 價格
                    current_eshop_price = None
                    if game.eshop_nsuid:
                        current_eshop_price = self.eshop.get_price_twd(game.id, game.eshop_nsuid)
                    
                    # 4. 獲取最新的 PTT 參考價格 (取最新一筆)
                    latest_ptt = MarketPrice.query.filter_by(
                        game_id=game.id, 
                        source="PTT"
                    ).order_by(MarketPrice.id.desc()).first()
                    
                    # 5. 轉成字典，包含所有顯示需要的欄位
                    final_dict_list.append({
                        'id': game.id,
                        'name': game.name,
                        'chinese_name': game.chinese_name,
                        'cover_url': game.cover_url,
                        'platform': game.platform,
                        'eshop_nsuid': game.eshop_nsuid,
                        'eshop_price': current_eshop_price,
                        'ptt_price': latest_ptt.price if latest_ptt else "暫無行情"
                    })
                
                # 統一 Commit 寫入資料庫
                db.session.commit()
            browser.close()
            
        return final_dict_list

    def update_tracked_market_data(self):
        """定時任務：同樣使用單一瀏覽器 Session 加速更新"""
        from app import app
        from services.ptt_service import PttAdapter
        ptt = PttAdapter()
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            page = browser.new_page()
            
            with app.app_context():
                tracked_games = Game.query.join(UserAsset).distinct().all()
                for game in tracked_games:
                    # eShop 更新
                    if not game.eshop_nsuid:
                        game.eshop_nsuid = self.eshop.search_nsuid(page, game.name, game.chinese_name)
                    if game.eshop_nsuid:
                        self.eshop.get_price_twd(game.id, game.eshop_nsuid)

                    # PTT 更新
                    search_query = game.chinese_name if game.chinese_name else game.name
                    ptt_results = ptt.search_game_prices(search_query) 
                    for r in ptt_results:
                        if not MarketPrice.query.filter_by(game_id=game.id, title=r['title']).first():
                            db.session.add(MarketPrice(game_id=game.id, price=r['price'], source="PTT", title=r['title']))
                
                db.session.commit()
            browser.close()