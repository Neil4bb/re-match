from extensions import db
from models import Game, GamePlatformID, MarketPrice, UserAsset, EShopMapping # 【新增】導入 EShopMapping
from services.igdb_service import IGDBService
from services.eshop_service import EShopService
from services.ps_service import PSStoreService
from flask import current_app
from services.ptt_service import PttAdapter
from sqlalchemy import or_
import re
import unicodedata

class MainManager:
    def __init__(self):
        self.igdb = IGDBService()
        self.eshop = EShopService()
        self.ps_store = PSStoreService()
        self.ptt = PttAdapter()

    def search_games(self, query):
        # 1. 抓取本地 EShopMapping
        mappings = EShopMapping.query.filter(EShopMapping.game_name.like(f"%{query}%")).all()
        
        local_results = []
        seen_igdb_ids = set()
        # 🌟 動態建立關鍵字清單，用來擋掉標題太像的 IGDB 結果
        local_titles = [] 

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
            local_titles.append(m.game_name.lower())

        # 2. 抓取 IGDB 並執行去重
        igdb_items = self.igdb.search_game(query)
        additional_results = []
        
        for item in igdb_items:
            # 判定重複的條件：
            # 1. ID 已經在本地出現過
            # 2. 或是英文名/中文名與本地現有的非常接近 (例如 P5R vs Persona 5 Royal)
            is_duplicate = (item['id'] in seen_igdb_ids)
            
            # 額外比對邏輯：如果 IGDB 的名字出現在本地標題裡，也視為重複
            if not is_duplicate:
                clean_igdb_name = item['name'].replace(" ", "").lower()
                for lt in local_titles:
                    # 檢查雙向包含：例如 "曠野之息" in "薩爾達傳說曠野之息"
                    if clean_igdb_name in lt or lt in clean_igdb_name:
                        is_duplicate = True
                        print(f"🚫 [去重成功] 偵測到重複項: {item['name']} (ID: {item['id']})")
                        break

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
            # 1. 🌟 保留字典與清洗邏輯 (不變)
            search_query = name 
            if name:
                # A. 先查 EShopMapping 字典表
                mapping = EShopMapping.query.filter(
                    or_(EShopMapping.english_name == name,
                        EShopMapping.game_name == name,
                        EShopMapping.english_name.like(f"{name}%"))
                ).first()

                if mapping:
                    search_query = mapping.game_name
                    if not nsuid: nsuid = mapping.nsuid
                    print(f"🌍 [Match] 成功對應字典: {name} -> {search_query} (NSUID: {nsuid})")
                else:
                    # B. 字典沒中，回頭查 Game 主表有沒有中文名
                    game_rec = db.session.get(Game, game_id) if game_id else None
                    if game_rec and game_rec.chinese_name:
                        search_query = game_rec.chinese_name
                        print(f"🏮 [Database] 字典無紀錄，從 Game 表獲取中文名: {search_query}")
                    else:
                        # C. 都沒招了，才用原始名稱清洗
                        search_query = name
                        print(f"🧹 [Fallback] 全無紀錄，使用原始名稱: {search_query}")

            clean_query = self.clean_game_name(search_query)
            
            results = {
                'status': 'success',
                'ps_digital': "--",
                'ps_ptt': "--",
                'ns_digital': "--",
                'ns_ptt': "--"
            }

            # 2. --- PlayStation 區域 ---
            # 💡 確保這裡呼叫的是你 ps_service.py 裡的 get_game_price
            ps_data = self.ps_store.get_game_price(name, search_query)
            if ps_data:
                results['ps_digital'] = ps_data['price']
                self._save_to_market_price(game_id, 'PS_Store', ps_data['name'], ps_data['price'], ps_data['url'])
            

            # 3. --- eShop 區域 ---
            if nsuid:
                print(f"📡 [eShop] 使用 NSUID 查價: {nsuid}")
                self.eshop.get_price_twd(game_id, nsuid)
                rec = MarketPrice.query.filter_by(game_id=game_id, title=f"eShop_{nsuid}").first()
                results['ns_digital'] = rec.price if rec else "--"
            

            # 4. --- PTT 分平台區域 ---
            
            clean_query = self.clean_game_name(search_query)

            print(f"🕵️ [PTT] 最終送往爬蟲的關鍵字: {clean_query}")

            # --- 第一次執行：獲取 PS 價格 ---
            ptt_results_ps = self.ptt.search_game_prices(clean_query, "PS")
            if ptt_results_ps:
                best_info = ptt_results_ps[0]
                new_ptt = MarketPrice(
                    game_id=game_id,
                    source='PTT',
                    title=best_info['title'],
                    price=best_info['price'],
                    source_url=best_info.get('url', "")
                )
                db.session.add(new_ptt)
                db.session.commit()
                results['ps_ptt'] = best_info['price']

            # --- 第二次執行：獲取 NS 價格 ---
            ptt_results_ns = self.ptt.search_game_prices(clean_query, "NS")
            if ptt_results_ns:
                best_info = ptt_results_ns[0]
                new_ptt = MarketPrice(
                    game_id=game_id,
                    source='PTT',
                    title=best_info['title'],
                    price=best_info['price'],
                    source_url=best_info.get('url', "")
                )
                db.session.add(new_ptt)
                db.session.commit()
                results['ns_ptt'] = best_info['price']
            

            db.session.commit()
            return results
        
        except Exception as e:
            db.session.rollback()
            return {'status': 'error', 'message': str(e)}


    def _save_to_market_price(self, game_id, source, title, price, url):
        """輔助存檔，確保不重複紀錄"""
        existing = MarketPrice.query.filter_by(game_id=game_id, source=source, title=title).first()
        if not existing:
            new_price = MarketPrice(
                game_id=game_id,
                source=source,
                title=title,
                price=price,
                source_url=url
            )
            db.session.add(new_price)
        
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
        
        # 🌟 核心：NFKC 會將全形字元(如：５、Ａ、（）) 自動轉為半形
        name = unicodedata.normalize('NFKC', name)

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
        #name = name.replace(" ", "").replace("　", "")
        
        # 確保回傳的是最乾淨的連體字，例如 "巫師3"
        return name.strip()