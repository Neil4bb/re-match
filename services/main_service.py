from extensions import db
from models import Game, MarketPrice, UserAsset
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
                platform=item.get('platform_name', 'Switch')
            )
            db.session.add(game)
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
                
                # 1. eShop NSUID
                if not game.eshop_nsuid:
                    game.eshop_nsuid = self.eshop.search_nsuid(game.name, game.chinese_name)
                    db.session.commit()
                
                # 2. eShop 價格
                current_eshop_price = self.eshop.get_price_twd(game.id, game.eshop_nsuid)

                # 3. PTT 價格
                search_query = game.chinese_name if game.chinese_name else game.name
                ptt_results = ptt.search_game_prices(search_query) 
                for r in ptt_results:
                    if not MarketPrice.query.filter_by(game_id=game.id, title=r['title']).first():
                        new_ptt = MarketPrice(game_id=game.id, price=r['price'], source='PTT', title=r['title'])
                        db.session.add(new_ptt)
                        db.session.commit()

                # --- 修正處：order_by ---
                latest_ptt = MarketPrice.query.filter_by(game_id=game.id, source='PTT')\
                    .order_by(MarketPrice.created_at.desc()).first()

                # 4. 組裝回傳
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

        return final_dict_list

    def update_tracked_market_data(self):
        from services.ptt_service import PttAdapter
        ptt = PttAdapter()
        with current_app.app_context():
            tracked_games = Game.query.join(UserAsset).distinct().all()
            for game in tracked_games:
                if not game.eshop_nsuid:
                    game.eshop_nsuid = self.eshop.search_nsuid(game.name, game.chinese_name)
                if game.eshop_nsuid:
                    self.eshop.get_price_twd(game.id, game.eshop_nsuid)

                search_query = game.chinese_name if game.chinese_name else game.name
                ptt_results = ptt.search_game_prices(search_query) 
                for r in ptt_results:
                    if not MarketPrice.query.filter_by(game_id=game.id, title=r['title']).first():
                        new_price = MarketPrice(game_id=game.id, price=r['price'], source='PTT', title=r['title'])
                        db.session.add(new_price)
            db.session.commit()