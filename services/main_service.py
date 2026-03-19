from extensions import db
from models import Game, GamePlatformID, MarketPrice, UserAsset, EShopMapping # 【新增】導入 EShopMapping
from services.igdb_service import IGDBService
from services.eshop_service import EShopService
from flask import current_app
from services.ptt_service import PttAdapter
from sqlalchemy import or_
import re

class MainManager:
    def __init__(self):
        self.igdb = IGDBService()
        self.eshop = EShopService()
        self.ptt = PttAdapter()

    def search_games(self, query):
        # 1. 抓取本地 EShopMapping (前三款的來源)
        mappings = EShopMapping.query.filter(EShopMapping.game_name.like(f"%{query}%")).all()
        
        local_results = []
        seen_igdb_ids = set()
        # 建立一個基礎名稱清單，用來擋掉重複的英文分身
        base_names = ["曠野之息", "Breath of the Wild"] 

        for m in mappings:
            local_results.append({
                'id': m.igdb_id,
                'name': m.game_name,
                'nsuid': m.nsuid,
                'cover_url': m.icon_url,
                'is_local': True
            })
            if m.igdb_id:
                seen_igdb_ids.add(m.igdb_id)

        # 2. 抓取 IGDB 並執行「強勢去重」
        igdb_items = self.igdb.search_game(query)
        additional_results = []
        
        for item in igdb_items:
            # 🌟 判定為分身的條件：
            # A. ID 已經在本地綁定過了
            # B. 名稱中包含核心關鍵字，且該遊戲沒有 NSUID (代表它是多餘的分身)
            is_duplicate = (
                item['id'] in seen_igdb_ids or 
                (any(bn in item['name'] for bn in base_names) and not item.get('nsuid'))
            )
            
            # 額外補刀：如果你這筆 ID=7346 真的太煩，直接在代碼層級黑名單
            if item['id'] == 7346:
                is_duplicate = True

            if not is_duplicate:
                item['is_local'] = False
                additional_results.append(item)

        return local_results + additional_results

    def store_game_logic(self, item):
        """
        【修改】保留原邏輯，並增加「自動綁定 Mapping」功能
        """
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
            db.session.flush() # 取得實體以供關聯

        # 【新增】如果這是一個來自搜尋的結果，且帶有 nsuid，嘗試回填 EShopMapping
        if item.get('nsuid'):
            mapping = EShopMapping.query.filter_by(nsuid=item['nsuid']).first()
            if mapping and mapping.igdb_id is None:
                mapping.igdb_id = game.id
                print(f"🔗 自動綁定: {mapping.game_name} -> IGDB ID: {game.id}")

        existing_platform = GamePlatformID.query.filter_by(
            game_id=game.id, 
            platform=item.get('platform', 'Switch')
        ).first()

        if not existing_platform:
            new_platform_id = GamePlatformID(
                game_id=game.id,
                platform=item.get('platform', 'Switch'),
                external_id=item.get('nsuid')
            )
            db.session.add(new_platform_id)
        
        db.session.commit()
        return game

    def get_game_details(self, game_id):
        """保留原邏輯"""
        game = db.session.get(Game, game_id)
        if not game:
            return None
        
        prices = MarketPrice.query.filter_by(game_id=game_id).all()
        latest_eshop = next((p for p in reversed(prices) if p.source == 'eShop'), None)
        latest_ptt = next((p for p in reversed(prices) if p.source == 'PTT'), None)

        return {
            'id': game.id,
            'name': game.name,
            'chinese_name': game.chinese_name,
            'cover_url': game.cover_url,
            'summary': game.summary,
            'eshop_price': latest_eshop.price if latest_eshop else "暫無價格",
            'ptt_price': latest_ptt.price if latest_ptt else "暫無行情"
        }

    def update_tracked_market_data(self):
        """
        【修改】大幅優化配對效率，改從本地 EShopMapping 獲取 NSUID
        """
        with current_app.app_context():
            tracked_games = Game.query.join(UserAsset).distinct().all()
            for game in tracked_games:
                p_rec = GamePlatformID.query.filter_by(game_id=game.id, platform='Switch').first()
                
                if not p_rec:
                    p_rec = GamePlatformID(game_id=game.id, platform='Switch')
                    db.session.add(p_rec)

                if not p_rec.external_id:
                    # --- 【優化處】不再爬網頁，改查本地 8907 筆字典 ---
                    # 優先用中文名精準匹配，再用英文名
                    mapping = EShopMapping.query.filter(
                        or_(
                            EShopMapping.game_name == game.chinese_name,
                            EShopMapping.game_name == game.name,
                            EShopMapping.igdb_id == game.id
                        )
                    ).first()

                    if mapping:
                        p_rec.external_id = mapping.nsuid
                        if mapping.igdb_id is None:
                            mapping.igdb_id = game.id
                    # ------------------

                if p_rec.external_id:
                    self.eshop.get_price_twd(game.id, p_rec.external_id)

                search_query = game.chinese_name if game.chinese_name else game.name
                ptt_results = self.ptt.search_game_prices(search_query) 
                for r in ptt_results:
                    if not MarketPrice.query.filter_by(game_id=game.id, title=r['title']).first():
                        new_price = MarketPrice(
                            game_id=game.id,
                            source='PTT',
                            title=r['title'],
                            price=r['price'],
                            url=r['url']
                        )
                        db.session.add(new_price)
                db.session.commit()

    # services/main_service.py

    def get_single_game_market_data(self, game_id, nsuid=None, name=None):
        try:
            # 1. 🌟 精確翻譯與 NSUID 補完邏輯
            search_query = name # 預設用原始名稱
            
            if name:
                # 改用精確匹配 english_name，避免 The Witcher 變成 薩爾達
                mapping = EShopMapping.query.filter(
                    or_(EShopMapping.english_name == name,
                        EShopMapping.game_name == name,
                        EShopMapping.english_name.like(f"{name}%")) # 至少要開頭一樣
                ).first()

                if mapping:
                    # 這裡才是正確的對應
                    search_query = mapping.game_name
                    if not nsuid:
                        nsuid = mapping.nsuid # 🌟 補回遺失的 NSUID
                    print(f"🌍 [Match] 成功對應字典: {name} -> {search_query} (NSUID: {nsuid})")
                else:
                    # 如果字典真的沒這款遊戲，就進行基本清洗（移除 : Wild Hunt 等）
                    search_query = self.clean_game_name(name)
                    print(f"🧹 [Clean] 字典無紀錄，使用清洗名稱: {search_query}")

            # 2. --- eShop 區域 ---
            eshop_price = "--"
            if nsuid:
                print(f"📡 [eShop] 使用 NSUID 查價: {nsuid}")
                self.eshop.get_price_twd(game_id, nsuid)
                rec = MarketPrice.query.filter_by(game_id=game_id, title=f"eShop_{nsuid}").first()
                eshop_price = rec.price if rec else "--"

            # 3. --- PTT 區域 ---
            ptt_price = "--"
            # 這裡使用剛才確定的 search_query (如果是巫師，現在應該是巫師了)
            clean_query = self.clean_game_name(search_query)

            print(f"🕵️ [PTT] 最終送往爬蟲的關鍵字: {clean_query}")

            # 傳入清洗後的結果
            ptt_results = self.ptt.search_game_prices(clean_query)
            
            if ptt_results:
                best_info = ptt_results[0]
                new_ptt = MarketPrice(
                    game_id=game_id,
                    source='PTT',
                    title=best_info['title'],
                    price=best_info['price'],
                    source_url=best_info.get('url', "")
                )
                db.session.add(new_ptt)
                db.session.commit()
                ptt_price = best_info['price']

            return {'status': 'success', 'eshop_price': eshop_price, 'ptt_price': ptt_price}
        except Exception as e:
            db.session.rollback()
            print(f"❌ [Fatal] 查價崩潰: {e}")
            return {'status': 'error', 'message': str(e)}
        
    # 在 main_service.py 的 MainManager 類別中新增
    def find_and_store_single_game(self, name, nsuid):
        # 1. 先從 Mapping 表找出這筆資料
        mapping = EShopMapping.query.filter_by(nsuid=nsuid).first()
        
        # 2. 決定搜尋關鍵字：有英文名就用英文，沒有才用原本傳入的名稱
        # 取得原始英文名
        raw_query = mapping.english_name if mapping and mapping.english_name else name
        
        # 🌟 執行清洗邏輯
        search_query = self.clean_game_name(raw_query)
        
        print(f"🎯 [Final Query] 清洗後的搜尋字串: '{search_query}'")
        
        # 策略 1：直接搜尋 (原本的邏輯)
        igdb_results = self.igdb.search_game(search_query)
        
        # 策略 2：如果沒結果，且名字包含中英文混雜，嘗試拆分
        if not igdb_results:
            import re
            # 提取英文部分 (假設名字長得像 "遊戲名 Game Name")
            english_parts = re.findall(r'[a-zA-Z0-9\s]{3,}', name)
            if english_parts:
                alt_name = english_parts[-1].strip()
                print(f"🔄 [Retry] 使用英文名稱重試: {alt_name}")
                igdb_results = self.igdb.search_game(alt_name)

        if igdb_results:
            # 挑選最像的一筆
            best_match = igdb_results[0]
            best_match['nsuid'] = nsuid
            
            # 執行儲存 (這會觸發你原本的 store_game_logic)
            game_obj = self.store_game_logic(best_match)
            print(f"✅ [Success] 成功綁定: {name} -> IGDB ID: {game_obj.id}")
            return game_obj
        
        print(f"❌ [Failed] IGDB 找不到任何與 '{name}' 相關的資料")
        return None
    
    def clean_game_name(self, name):
        """
        清理搜尋字串，同時支援 IGDB 英文與字典中文名
        """
        if not name:
            return ""

        # 1. 🌟 新增：移除 PTT 搜尋大敵 —— 書名號
        name = name.replace('《', '').replace('》', '')

        # 2. 移除 ™ 和 ® 符號 (原本的)
        name = name.replace('™', '').replace('®', '')
        
        # 3. 移除括號內的內容 (原本的)
        name = re.sub(r'\(.*?\)', '', name)
        
        # 🌟 關鍵修正：先切斷副標題 (遇到冒號或連字號就切斷)
        name = re.split(r'[:：\-－]', name)[0]
        
        # 🌟 關鍵修正：要把「中間」的空格也殺掉，不能只用 strip()
        # 同時處理半形空格 " " 和全形空格 "　"
        name = name.replace(" ", "").replace("　", "")
        
        # 確保回傳的是最乾淨的連體字，例如 "巫師3"
        return name.strip()