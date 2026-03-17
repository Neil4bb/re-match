from extensions import db
from models import Game, GamePlatformID, MarketPrice, UserAsset
from services.igdb_service import IGDBService
from services.eshop_service import EShopService
from flask import current_app
from services.ptt_service import PttAdapter
from models import EShopMapping

class MainManager:
    def __init__(self):
        self.igdb = IGDBService()
        self.eshop = EShopService()
        self.ptt = PttAdapter()

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
            
            # 1. 先確認該遊戲在 Switch 平台的紀錄
            p_rec = GamePlatformID.query.filter_by(game_id=game_id, platform='Switch').first()
            
            # 如果連平台紀錄都沒有，先建立一個空殼（確保後續可以存 external_id）
            if not p_rec:
                p_rec = GamePlatformID(game_id=game_id, platform='Switch')
                db.session.add(p_rec)
                db.session.commit()

            nsuid = p_rec.external_id

            # 2. 核心邏輯：如果沒有 NSUID，則進入「緩存優先」搜尋流程
            if not nsuid:
                # A. 優先從 EShopMapping 尋找 (這張表是我們導入的 2000 筆名單)
                mapping = EShopMapping.query.filter_by(igdb_id=game_id).first()
                
                if mapping and mapping.nsuid:
                    # 命中快取！直接拿來用
                    nsuid = mapping.nsuid
                    print(f"🎯 從 Mapping 表命中快取: {game.name} -> {nsuid}")
                else:
                    # B. Mapping 也沒資料，才動態爬取 eShop (最後保底)
                    print(f"🕵️ Mapping 無紀錄，即時搜尋 eShop: {game.name}")
                    result = self.eshop.search_nsuid(game.name, game.chinese_name)
                    if result and isinstance(result, dict):
                        nsuid = result.get('nsuid')
                        # 同步回 Mapping 表與 Game 表 (反抓中文名)
                        self._sync_eshop_data_back(game, mapping, result)
                
                # 寫回 GamePlatformID，這樣下次連 Mapping 都不用查，直接讀 p_rec.external_id
                if nsuid:
                    p_rec.external_id = nsuid
                    db.session.commit()

            # 3. 根據最終拿到的 nsuid 查價
            eshop_price = self.eshop.get_price_twd(game.id, nsuid) if nsuid else "N/A"

            # B. 處理 PTT (查價)
            search_query = game.chinese_name if game.chinese_name else game.name
            try:
                # 使用我們在 __init__ 定義好的 self.ptt
                ptt_results = self.ptt.search_game_prices(search_query) 
                for r in ptt_results:
                    # 檢查是否已存過同標題的價格，避免重複
                    if not MarketPrice.query.filter_by(game_id=game.id, title=r['title']).first():
                        new_ptt = MarketPrice(game_id=game.id, price=r['price'], source='PTT', title=r['title'])
                        db.session.add(new_ptt)
                db.session.commit()
            except Exception as e:
                print(f"⚠️ PTT 抓取失敗: {e}")
            
            latest_ptt = MarketPrice.query.filter_by(game_id=game.id, source='PTT')\
                .order_by(MarketPrice.created_at.desc()).first()

            return {
                'eshop_price': eshop_price,
                'ptt_price': latest_ptt.price if latest_ptt else "暫無行情"
            }

    def update_tracked_market_data(self):
        
        with current_app.app_context():
            tracked_games = Game.query.join(UserAsset).distinct().all()
            for game in tracked_games:
                p_rec = GamePlatformID.query.filter_by(game_id=game.id, platform='Switch').first()
                
                if not p_rec:
                    p_rec = GamePlatformID(game_id=game.id, platform='Switch')
                    db.session.add(p_rec)

                if not p_rec.external_id:
                    # --- 關鍵修正處 ---
                    result = self.eshop.search_nsuid(game.name, game.chinese_name)
                    if result and isinstance(result, dict):
                        p_rec.external_id = result.get('nsuid')
                    # ------------------

                if p_rec.external_id:
                    self.eshop.get_price_twd(game.id, p_rec.external_id)

                search_query = game.chinese_name if game.chinese_name else game.name
                ptt_results = self.ptt.search_game_prices(search_query) 
                for r in ptt_results:
                    if not MarketPrice.query.filter_by(game_id=game.id, title=r['title']).first():
                        new_price = MarketPrice(game_id=game.id, price=r['price'], source='PTT', title=r['title'])
                        db.session.add(new_price)
            db.session.commit()