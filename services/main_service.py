from extensions import db
from models import Game, GamePlatformID, MarketPrice, UserAsset
from services.igdb_service import IGDBService
from services.eshop_service import EShopService
from flask import current_app

class MainManager:
    def __init__(self):
        self.igdb = IGDBService()
        self.eshop = EShopService()

    def store_game_logic(self, item):
        game = db.session.get(Game, item['id'])

        if not game:
            game = Game(
                id=item['id'],
                name=item['name'],
                chinese_name=item.get('chinese_name', ''),
                cover_url=item['cover_url'],
                summary=item.get('summary')
            )
            db.session.add(game)

        existing_platform = GamePlatformID.query.filter_by(
            game_id=game.id, 
            platform=item.get('platform', 'Switch') # 預設給 Switch 或從 item 抓
        ).first()

        if not existing_platform:
            new_platform_id = GamePlatformID(
                game_id=game.id,
                platform=item.get('platform', 'Switch'),
                external_id=item.get('nsuid') # 或是對應平台的外部 ID
            )
            db.session.add(new_platform_id)
            db.session.commit()
        return game

    def search_and_store_game(self, keyword):
        from services.ptt_service import PttAdapter
        ptt = PttAdapter()
        raw_results = self.igdb.search_game(keyword)
        if not raw_results: return []
        
        final_dict_list = []
        
        for item in raw_results:
            with current_app.app_context():
                game = self.store_game_logic(item)
                
                platform_rec = GamePlatformID.query.filter_by(game_id=game.id, platform='Switch').first()
                if not platform_rec:
                    platform_rec = GamePlatformID(game_id=game.id, platform='Switch')
                    db.session.add(platform_rec)
                    db.session.flush() # 讓 id 生效

                # 1. eShop NSUID (使用 platform_rec.external_id 替換 game.eshop_nsuid)
                #if not platform_rec.external_id:
                #    platform_rec.external_id = self.eshop.search_nsuid(game.name, game.chinese_name)
                #    db.session.commit()
                
                # 2. eShop 價格
                #current_eshop_price = "查詢失敗"
                #try:
                #    current_eshop_price = self.eshop.get_price_twd(game.id, platform_rec.external_id)
                #except Exception as e:
                #    print(f"⚠️ 價格抓取異常: {e}")

                # 3. PTT 價格
                #search_query = game.chinese_name if game.chinese_name else game.name
                #try:
                #    ptt_results = ptt.search_game_prices(search_query) 
                #    for r in ptt_results:
                #        if not MarketPrice.query.filter_by(game_id=game.id, title=r['title']).first():
                #            new_ptt = MarketPrice(game_id=game.id, price=r['price'], source='PTT', title=r['title'])
                #            db.session.add(new_ptt)
                #    db.session.commit()
                #except Exception as e:
                #    print(f"⚠️ PTT 抓取失敗: {e}")

                #latest_ptt = MarketPrice.query.filter_by(game_id=game.id, source='PTT')\
                #    .order_by(MarketPrice.created_at.desc()).first()

                # 4. 組裝回傳
                final_dict_list.append({
                    'id': game.id,
                    'name': game.name,
                    'chinese_name': game.chinese_name,
                    'cover_url': game.cover_url,
                    'platform': platform_rec.platform,
                    #'eshop_nsuid': platform_rec.external_id,
                    #'eshop_price': current_eshop_price or "N/A",
                    #'ptt_price': latest_ptt.price if latest_ptt else "暫無行情"
                })

        return final_dict_list
    
    def get_single_game_market_data(self, game_id):
        with current_app.app_context():
            game = db.session.get(Game, game_id)
            if not game: return None
            
            # A. 處理 eShop (抓 ID + 查價)
            platform_rec = GamePlatformID.query.filter_by(game_id=game_id, platform='Switch').first()
            if not platform_rec.external_id:
                platform_rec.external_id = self.eshop.search_nsuid(game.name, game.chinese_name)
                db.session.commit()
            
            eshop_price = self.eshop.get_price_twd(game.id, platform_rec.external_id) if platform_rec.external_id else "N/A"
            
            # B. 處理 PTT (查價)
            search_query = game.chinese_name if game.chinese_name else game.name
            ptt_results = self.ptt.search_game_prices(search_query) # 假設已在 __init__ 實例化
            # ... 存入 MarketPrice 的邏輯 ...
            
            latest_ptt = MarketPrice.query.filter_by(game_id=game.id, source='PTT')\
                .order_by(MarketPrice.created_at.desc()).first()

            return {
                'eshop_price': eshop_price,
                'ptt_price': latest_ptt.price if latest_ptt else "暫無行情"
            }

    def update_tracked_market_data(self):
        from services.ptt_service import PttAdapter
        ptt = PttAdapter()
        with current_app.app_context():
            tracked_games = Game.query.join(UserAsset).distinct().all()
            for game in tracked_games:
                p_rec = GamePlatformID.query.filter_by(game_id=game.id, platform='Switch').first()
                
                if not p_rec:
                    p_rec = GamePlatformID(game_id=game.id, platform='Switch')
                    db.session.add(p_rec)

                if not p_rec.external_id:
                    p_rec.external_id = self.eshop.search_nsuid(game.name, game.chinese_name)
                
                if p_rec.external_id:
                    self.eshop.get_price_twd(game.id, p_rec.external_id)

                search_query = game.chinese_name if game.chinese_name else game.name
                ptt_results = ptt.search_game_prices(search_query) 
                for r in ptt_results:
                    if not MarketPrice.query.filter_by(game_id=game.id, title=r['title']).first():
                        new_price = MarketPrice(game_id=game.id, price=r['price'], source='PTT', title=r['title'])
                        db.session.add(new_price)
            db.session.commit()