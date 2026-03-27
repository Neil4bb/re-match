from extensions import db
from models import Game, GamePlatformID, MarketPrice, UserAsset, EShopMapping # 【新增】導入 EShopMapping
from services.igdb_service import IGDBService
from services.eshop_service import EShopService
from services.ps_service import PSStoreService
from flask import current_app
from services.ptt_service import PttAdapter
from sqlalchemy import or_
import re, time, random, unicodedata
from datetime import datetime, timedelta

class MainManager:
    def __init__(self):
        self.igdb = IGDBService()
        self.eshop = EShopService()
        self.ps_store = PSStoreService()
        self.ptt = PttAdapter()

    def search_games(self, query):
        if not query:
            return []

        print(f"🔎 [Search] 開始搜尋關鍵字: {query}")
        db_results = []
        seen_nsuids = set()
        seen_igdb_ids = set()

        # --- 階段 1：本地 Games 表搜尋 (已入庫的遊戲) ---
        # 這裡的遊戲資料最完整，包含已有的 ID 關聯
        local_games = Game.query.filter(
            or_(
                Game.name.like(f"%{query}%"),
                Game.chinese_name.like(f"%{query}%")
            )
        ).limit(10).all()

        for g in local_games:
            # 嘗試獲取該遊戲已綁定的 NSUID
            platform_rec = GamePlatformID.query.filter_by(game_id=g.id, platform='Switch').first()
            nsuid = platform_rec.external_id if platform_rec else None
            
            db_results.append({
                'id': g.id,
                'name': g.chinese_name or g.name,
                'nsuid': nsuid,
                'cover_url': g.cover_url,
                'is_local': True,
                'source': 'Database'
            })
            seen_igdb_ids.add(g.id)
            if nsuid: seen_nsuids.add(nsuid)

        # --- 階段 2：本地 EShopMapping 字典搜尋 ---
        # 即使 Games 表沒有，也要檢查 8900 筆字典檔是否有匹配
        if len(db_results) < 10:
            mappings = EShopMapping.query.filter(
                or_(
                    EShopMapping.game_name.like(f"%{query}%"),
                    EShopMapping.english_name.like(f"%{query}%")
                )
            ).limit(10).all()

            for m in mappings:
                if m.nsuid not in seen_nsuids:
                    # 🌟 虛擬 ID 策略：若無 igdb_id，則傳遞虛擬 ID 防止前端傳送 "None"
                    virtual_id = m.igdb_id if m.igdb_id else f"nsuid_{m.nsuid}"
                    
                    db_results.append({
                        'id': virtual_id,
                        'name': m.game_name,
                        'nsuid': m.nsuid,
                        'cover_url': m.icon_url,
                        'is_local': True,
                        'source': 'Mapping'
                    })
                    seen_nsuids.add(m.nsuid)
                    if m.igdb_id: seen_igdb_ids.add(m.igdb_id)

        # --- 判斷門檻：若本地有結果 (>=1)，則直接回傳，節省 API 呼叫 ---
        if len(db_results) >= 1:
            print(f"✅ [Local Match] 找到 {len(db_results)} 筆本地結果，跳過遠端搜尋")
            return db_results

        # --- 階段 3：原版備援搜尋 (僅在本地無結果時觸發) ---
        print(f"🌐 [IGDB] 本地無匹配，啟動原版 IGDB 備援搜尋...")
        
        # 🌟 以下為你原版的去重與搜尋邏輯
        local_titles = [] # 此時 local_titles 為空，因為本地無結果
        
        # 呼叫你原有的 IGDB Service
        igdb_items = self.igdb.search_game(query)
        additional_results = []
        
        for item in igdb_items:
            # 判斷 1：ID 是否完全相同 (雖然本地無結果，但保留結構相容性)
            is_duplicate = (item['id'] in seen_igdb_ids)
            
            # 判斷 2：名稱模糊比對
            if not is_duplicate:
                clean_igdb_name = item['name'].replace(" ", "").lower()
                for lt in local_titles:
                    if clean_igdb_name in lt or lt in clean_igdb_name:
                        is_duplicate = True
                        break

            # 判斷 3：硬編碼黑名單
            if item['id'] == 150080:
                is_duplicate = True

            if not is_duplicate:
                item['is_local'] = False
                item['source'] = 'IGDB'
                additional_results.append(item)

        return additional_results

    def store_game_logic(self, item):
        """
        【修改】強化名稱儲存邏輯：優先採用 Mapping 表的中文名稱
        """
        # 1. 取得現有的遊戲紀錄
        game = db.session.get(Game, item['id'])

        if not game:
            # 🌟 [新增邏輯]：在存檔前，先去 Mapping 表看看有沒有這款遊戲的中文名
            # 優先用 nsuid 查，若無則用 igdb_id 查
            mapping = None
            if item.get('nsuid'):
                mapping = EShopMapping.query.filter_by(nsuid=item['nsuid']).first()
            if not mapping:
                mapping = EShopMapping.query.filter_by(igdb_id=item['id']).first()

            # 🌟 決定最終顯示名稱
            # 1. 決定「小字」(原始英文名)
            # 如果 item 裡有 name (IGDB 抓來的)，就用它；
            # 如果 mapping 有英文名，那更好。
            target_english = item.get('name', '')
            
            # 🌟 逐行比對：如果 mapping 的中文名沒寫 Switch 2，英文名就絕對不准有
            if mapping:
                target_english = mapping.english_name if mapping.english_name else item.get('name', '')

                is_map_sw2 = "switch 2" in mapping.game_name.lower() or "switch2" in mapping.game_name.lower()
                if not is_map_sw2:
                    target_english = target_english.replace("Nintendo Switch 2 Edition", "")
                    target_english = target_english.replace("Switch 2", "").replace("Switch2", "")
                    target_english = target_english.rstrip(' –-').strip()
                
            else:
                # 如果連 Mapping 都沒英文名，則執行基礎平台判定去污 (備援)
                platforms = item.get('platforms', [])
                p_ids = [p.get('id') if isinstance(p, dict) else p for p in platforms]
                if 508 not in p_ids:
                    target_english = target_english.replace("Nintendo Switch 2 Edition", "").replace("Switch 2", "").strip()
                    target_english = target_english.rstrip(' –-')

            # 2. 決定「大字」(本地中文名)
            # 優先序：Mapping 字典 > 傳入的 chinese_name > IGDB 原始名
            target_chinese = item.get('chinese_name') or item['name']
            if mapping and mapping.game_name:
                target_chinese = mapping.game_name

            # 🌟 [新增]：在存檔前執行最後一次清洗 
            target_chinese = self.clean_game_name(target_chinese)

            game = Game(
                id=item['id'],
                name=target_english,    # 小字：英文
                chinese_name=target_chinese, # 小字：英文
                cover_url=item['cover_url'],
                summary=item.get('summary')
            )
            db.session.add(game)
            db.session.flush()

        # 2. 自動綁定 Mapping 功能 (保留原邏輯)
        if item.get('nsuid'):
            mapping = EShopMapping.query.filter_by(nsuid=item['nsuid']).first()
            if mapping and mapping.igdb_id is None:
                mapping.igdb_id = game.id
                print(f"🔗 自動綁定: {mapping.game_name} -> IGDB ID: {game.id}")

        # 3. 處理平台 ID (保留原邏輯)
        platform_name = 'Switch'
        nsuid_to_save = item.get('nsuid')

        if nsuid_to_save:
            existing_platform = GamePlatformID.query.filter_by(
                game_id=game.id, 
                platform=platform_name
            ).first()

            if not existing_platform:
                new_platform_id = GamePlatformID(
                    game_id=game.id,
                    platform='Switch',
                    external_id=item.get('nsuid')
                )
                db.session.add(new_platform_id)
                # 🌟 修正 ：立即 commit，防止後續 PTT 錯誤導致 rollback
                db.session.commit() 
                print(f"✅ [Platform Saved] ID: {nsuid_to_save}")
            elif nsuid_to_save and not existing_platform.external_id:
                existing_platform.external_id = nsuid_to_save
                db.session.commit()
                print(f"✅ [Platform Updated] ID: {nsuid_to_save}")

        igdb_platforms = item.get('platforms', [])
        for p_info in igdb_platforms:
            p_name = p_info.get('name', '') if isinstance(p_info, dict) else ""
            
            # 只針對 PS 系列進行補齊
            if any(k in p_name for k in ['PlayStation 4', 'PlayStation 5', 'PS4', 'PS5']):
                exists_ps = GamePlatformID.query.filter_by(
                    game_id=game.id, 
                    platform=p_name
                ).first()
                
                if not exists_ps:
                    new_ps = GamePlatformID(game_id=game.id, platform=p_name)
                    db.session.add(new_ps)
        
        # 最後補一個統一 commit，確保 PS 標籤與可能的其他更動存入
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
                        # 🌟 新增：根據 PTT 標題動態決定平台標籤
                        post_title = r['title'].upper()
                        p_tag = 'Switch' # 預設值
                        if '[PS5' in post_title:
                            p_tag = 'PlayStation 5'
                        elif '[PS4' in post_title:
                            p_tag = 'PlayStation 4'
                        elif '[NS' in post_title:
                            p_tag = 'Switch'

                        new_price = MarketPrice(
                            game_id=game.id,
                            source='PTT',
                            platform=p_tag,
                            title=r['title'],
                            price=r['price'],
                            source_url=r['url']
                        )
                        db.session.add(new_price)
                db.session.commit()

    # services/main_service.py

    def get_single_game_market_data(self, game_id, nsuid=None, name=None, force_refresh=False):
        
        # 1. 如果不是強制刷新，先檢查資料庫（第二點：快取優先）
        if not force_refresh:
            # 🌟 統一使用 UTC 時間進行比較
            cache_limit = datetime.utcnow() - timedelta(hours=36) 
            has_any_price = MarketPrice.query.filter(
                MarketPrice.game_id == game_id,
                MarketPrice.created_at >= cache_limit
            ).first()
            
            if has_any_price:
                print(f"📦 [Cache Hit] 遊戲 {game_id} 命中快取 (UTC 判定)")
                return self._get_cached_market_data(game_id)

        # 2. 執行即時查價邏輯（第三點：強制更新 或 快取失效）
        print(f"🚀 [Live Fetch] 正在為遊戲 {game_id} 執行即時查價...")
        game = Game.query.get(game_id)
        if not game:
            return {"error": "Game not found"}

        # --- 以下是原本的爬蟲呼叫邏輯 ---
        
        try:
            
            search_query = name # 預設值
            
            if name:
            
                # A. 優先查字典 (EShopMapping)
                mapping = EShopMapping.query.filter(
                        or_(EShopMapping.english_name == name,
                            EShopMapping.game_name == name,
                            EShopMapping.english_name.like(f"{name}%"))
                    ).first()
                
                if mapping:
                    search_query = mapping.game_name
                    if not nsuid: nsuid = mapping.nsuid

                    # 🌟 【新增回填邏輯 1】：如果字典有這筆資料，但還沒關聯 IGDB ID，現在立刻回填
                    if game_id and mapping.igdb_id is None:
                        mapping.igdb_id = game_id
                        db.session.commit()
                        print(f"🔗 [回填成功] 字典 {mapping.game_name} 已綁定 IGDB ID: {game_id}")
                    
                    print(f"🌍 [Match] 成功對應字典: {search_query}")
                # B. 字典沒中，使用剛才 ensure_game_exists 抓回來的中文名
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
                    
            if game_id:
                # 調用 ensure_game_exists
                self.ensure_game_exists(game_id, name_fallback=search_query, nsuid=nsuid)

                # 🌟 【新增回填邏輯 2】：確保 GamePlatformID 表也有這個 NSUID 關聯
                if nsuid:
                    existing_platform = GamePlatformID.query.filter_by(
                        game_id=game_id, 
                        platform='Switch'
                    ).first()
                    
                    if not existing_platform:
                        new_platform = GamePlatformID(
                            game_id=game_id,
                            platform='Switch',
                            external_id=nsuid
                        )
                        db.session.add(new_platform)
                        db.session.commit()
                        print(f"✅ [Platform Saved] 查價時補完 NSUID 關聯: {nsuid}")
            
            
            # ---------------------------------------------------------
            

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
            if nsuid and game_id:  # 🌟 加上 game_id 判斷
                try:
                    print(f"📡 [eShop] 使用 NSUID 查價: {nsuid}")
                    self.eshop.get_price_twd(game_id, nsuid)
                    rec = MarketPrice.query.filter_by(game_id=game_id, title=f"eShop_{nsuid}").first()
                    results['ns_digital'] = rec.price if rec else "--"
                    db.session.commit()
                except Exception as e:
                    print(f"📡 eShop 抓取失敗，但繼續執行後續: {e}")
                    db.session.rollback()
            else:
                print(f"⚠️ [Skip eShop] 無有效 GameID 或 NSUID，僅執行 API 查詢但不存檔")
            

            # 4. --- PTT 分平台區域 ---
            if game_id: # 🌟 確保有實體遊戲 ID 才能執行 PTT 搜尋與存檔
                ptt_keyword, filter_tag = self._get_ptt_search_strategy(search_query)
        
                print(f"🕵️ [PTT] 最終策略 - 關鍵字: {ptt_keyword} | 過濾器: {filter_tag}")
                
                

                # --- 第一次執行：獲取 PS 價格 ---
                try:
                    ptt_results_ps = self.ptt.search_game_prices(ptt_keyword, "PS", filter_tag=filter_tag)
                    if ptt_results_ps:
                        now_utc = datetime.utcnow()
                        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

                        for r in ptt_results_ps:
                            # 🌟 核心：檢查今天是否已經存過這篇「特定文章 (URL)」
                            exists = MarketPrice.query.filter(
                                MarketPrice.game_id == game_id,
                                MarketPrice.source == 'PTT',
                                MarketPrice.source_url == r['url'], # 用 URL 判定唯一性
                                MarketPrice.created_at >= today_start
                            ).first()

                            if not exists:
                                # 根據標題決定平台標籤
                                post_title = r['title'].upper()
                                p_tag = 'PlayStation 5' if '[PS' in post_title else 'Switch'
                                
                                new_price = MarketPrice(
                                    game_id=game_id,
                                    source='PTT',
                                    platform=p_tag,
                                    title=r['title'],
                                    price=r['price'],
                                    source_url=r['url'],
                                    created_at=now_utc
                                )
                                db.session.add(new_price)
                                print(f"✅ [PTT Multi-Save] 存入文章: {r['title'][:10]}... NT$ {r['price']}")
                            else:
                                # 如果今天存過同一篇，更新價格 (可能賣家改價)
                                exists.price = r['price']
                                exists.created_at = now_utc
                                
                        db.session.commit()
                except Exception as e:
                    print(f"⚠️ PTT PS 搜尋逾時跳過: {e}")

                # --- 第二次執行：獲取 NS 價格 ---
                try:
                    ptt_results_ns = self.ptt.search_game_prices(ptt_keyword, "NS", filter_tag=filter_tag)
                    if ptt_results_ns:
                        now_utc = datetime.utcnow()
                        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

                        for r in ptt_results_ns:
                            # 🌟 核心：檢查今天是否已經存過這篇「特定文章 (URL)」
                            exists = MarketPrice.query.filter(
                                MarketPrice.game_id == game_id,
                                MarketPrice.source == 'PTT',
                                MarketPrice.source_url == r['url'], # 用 URL 判定唯一性
                                MarketPrice.created_at >= today_start
                            ).first()

                            if not exists:
                                # 根據標題決定平台標籤
                                post_title = r['title'].upper()
                                p_tag = 'PlayStation 5' if '[PS' in post_title else 'Switch'
                                
                                new_price = MarketPrice(
                                    game_id=game_id,
                                    source='PTT',
                                    platform=p_tag,
                                    title=r['title'],
                                    price=r['price'],
                                    source_url=r['url'],
                                    created_at=now_utc
                                )
                                db.session.add(new_price)
                                print(f"✅ [PTT Multi-Save] 存入文章: {r['title'][:10]}... NT$ {r['price']}")
                            else:
                                # 如果今天存過同一篇，更新價格 (可能賣家改價)
                                exists.price = r['price']
                                exists.created_at = now_utc
                                
                        db.session.commit()
                except Exception as e:
                    print(f"⚠️ PTT NS 搜尋逾時跳過: {e}")
                
            else:
                # 如果沒 ID，依然可以印出訊息記錄，但不執行資料庫操作
                print(f"⚠️ [Skip PTT] {search_query} 無有效 GameID，跳過 PTT 存檔邏輯")
            
            db.session.commit()
            return self._get_cached_market_data(game_id)
        
        except Exception as e:
            db.session.rollback()
            return {'status': 'error', 'message': str(e)}
        

    def _get_cached_market_data(self, game_id):
        """私有方法：從資料庫抓取資料並格式化（相容新舊需求）"""
        # 抓取該遊戲所有的價格紀錄，按時間由新到舊
        all_prices = MarketPrice.query.filter_by(game_id=game_id).order_by(MarketPrice.created_at.desc()).all()
        
        # 建立一個相容舊格式的字典
        formatted = {
            'status': 'success',
            'ps_digital': "--",
            'ps_ptt': "--",
            'ns_digital': "--",
            'ns_ptt': "--",
            'history': [] # 🌟 新增：給圖表用的完整清單
        }

        for p in all_prices:
            # 1. 填入最新的價格 (只填第一次遇到的來源)
            if p.source == 'PS_Store' and formatted['ps_digital'] == "--":
                formatted['ps_digital'] = p.price
            elif p.source == 'PTT' and 'PlayStation' in (p.platform or '') and formatted['ps_ptt'] == "--":
                formatted['ps_ptt'] = p.price
            elif p.source == 'eShop' and formatted['ns_digital'] == "--":
                formatted['ns_digital'] = p.price
            elif p.source == 'PTT' and 'Switch' in (p.platform or '') and formatted['ns_ptt'] == "--":
                formatted['ns_ptt'] = p.price

            # --- 🌟 修改重點：格式化歷史紀錄 (轉為 UTC+8) ---
            local_time = p.created_at + timedelta(hours=8)
                
            # 2. 填入歷史紀錄
            formatted['history'].append({
                'source': p.source,
                'platform': p.platform,
                'price': p.price,
                'title': p.title or "",            # 🌟 放入標題
                'source_url': p.source_url or "",  # 🌟 放入原文網址
                'date': local_time.strftime('%Y-%m-%d %H:%M') # 🌟 轉為台灣時間字串
            })

        return formatted
    
    def get_cached_only_data(self, game_id):
        """只從資料庫拿資料，絕對不觸發網路爬蟲"""
        latest_price = MarketPrice.query.filter_by(game_id=game_id).first()
        if not latest_price:
            return {} # 或者回傳預設的空值結構
        return self._get_cached_market_data(game_id)

    def _save_to_market_price(self, game_id, source, title, price, url):
        """輔助存檔，確保不重複紀錄"""
        # 🌟 修正：如果沒有 game_id，直接跳過存檔，避免資料庫報錯
        if not game_id:
            print(f"⚠️ [Skip Save] 無有效 GameID，跳過 {source} 價格存檔")
            return

        # 🌟 定義 2 小時的時間門檻
        now_utc = datetime.utcnow()
        two_hours_ago = now_utc - timedelta(hours=2)

        existing = MarketPrice.query.filter(
            MarketPrice.game_id == game_id,
            MarketPrice.source == source,
            MarketPrice.title == title,
            MarketPrice.created_at >= two_hours_ago # 🌟 檢查 2 小時內是否有紀錄
        ).order_by(MarketPrice.created_at.desc()).first()
        
        if not existing:
            # 2 小時內沒存過，建立新紀錄
            p_tag = 'PlayStation 5' if source == 'PS_Store' else 'Switch'
            new_price = MarketPrice(
                game_id=game_id,
                source=source,
                platform=p_tag,
                title=title,
                price=price,
                source_url=url,
                created_at=now_utc
            )
            db.session.add(new_price)
            print(f"✅ [Price Saved] {source} 價格已入庫: NT$ {price}")
        else:
            existing.price = price
            existing.created_at = now_utc # 更新時間戳記
            print(f"🔄 [Price Updated] {source} 2小時內已有紀錄，僅更新時間與價格")

        db.session.commit() 
            
        
    # 在 main_service.py 的 MainManager 類別中新增
    def find_and_store_single_game(self, name, nsuid):
        try:
            # 1. 取得 Mapping 權威資料
            mapping = EShopMapping.query.filter_by(nsuid=nsuid).first()

            # 1. 判定目標模式
            is_targeting_switch2 = "switch 2" in name.lower() or "switch2" in name.lower()
            
            # 2. 獲取初始搜尋詞
            search_target = mapping.english_name if mapping and mapping.english_name else name
            
            # 🌟 關鍵修正：搜尋詞隔離
            if not is_targeting_switch2:
                # 如果目標是原版，強制移除搜尋詞中的 Switch 2 贅字，防止搜到 Switch 2 版
                if mapping and mapping.english_name:
                    search_target = mapping.english_name
                # 強制移除所有可能導致 IGDB 轉向 Switch 2 的字眼
                search_target = search_target.replace("Nintendo Switch 2 Edition", "").replace("Switch 2", "")
            
            search_target = re.split(r'[:：\-－–—]', search_target)[0].strip()
            
            search_query = self.clean_game_name(search_target)
            print(f"🎯 [IGDB Search] 使用英文名搜尋: '{search_query}'")

            igdb_results = self.igdb.search_game(search_query)
            if not igdb_results: return None

            best_match = None
            clean_target_name = name.replace(" ", "").lower()

            for item in igdb_results:
                try:
                    # A. 平台過濾 (Switch 2 ID = 508)
                    platforms = item.get('platforms') or []
                    p_ids = [p.get('id') if isinstance(p, dict) else p for p in platforms]
                    item_name_raw = item.get('name', '')
                    item_name_clean = item_name_raw.lower().replace(" ", "").replace("'", "") # 🌟 多移除單引號

                    # 🛑 [平台攔截]
                    if not is_targeting_switch2:
                        # 目標不是 Switch 2，但結果是，直接踢掉
                        if 508 in p_ids or "switch2" in item_name_clean: continue
                    else:
                        # 目標是 Switch 2，但結果不是，也踢掉
                        if 508 not in p_ids and "switch2" not in item_name_clean: continue

                    # B. 名稱驗證 (確保搜到的是正確的遊戲)
                    alt_names = item.get('alternative_names', [])
                    chinese_names = [n.get('name', '').replace(" ", "").lower() for n in alt_names if isinstance(n, dict)]

                    # 🌟 [修正比對邏輯] - 整合你的 B 段與 C 段邏輯
                    # 1. 優先判定：精準比對中文名 (你原本最信任的邏輯)
                    is_match = clean_target_name in item_name_clean or any(clean_target_name in cn for cn in chinese_names)
                    
                    # 2. 🌟 補強判定：如果中文沒對上 (例如巫師、路易吉)，則比對搜尋用的英文
                    if not is_match:
                        search_query_clean = search_query.lower().replace(" ", "").replace("'", "")
                        # 如果搜尋詞 (Luigi's Mansion 3) 跟 IGDB 結果 (luigismansion3) 對上了，就放行
                        if search_query_clean in item_name_clean or item_name_clean in search_query_clean:
                            is_match = True
                            print(f"💡 [Heuristic Match] 中文別名未中，但搜尋詞 '{search_query}' 匹配成功")

                    # 3. 🌟 Switch 2 特殊模糊匹配 (你原本寫好的)
                    if not is_match and is_targeting_switch2:
                        core_name = name.lower().replace("nintendoswitch2edition", "").replace("switch2", "").strip()
                        if core_name in item_name_clean or "switch2" in item_name_clean:
                            is_match = True
                            print(f"⚠️ [Loose Match] 為 Switch 2 啟用模糊匹配成功: {item_name_raw}")

                    if is_match:
                        best_match = item
                        break

                except Exception:
                    continue

            # 🌟 2. 核心修改：只抓平台與 ID，其餘套用 Mapping
            if best_match:
                igdb_id = best_match['id'] # 取得 IGDB 的 ID
                
                # --- 🌟 關鍵修正開始：主鍵衝突檢查 ---
                existing_game = Game.query.get(igdb_id)
                if existing_game:
                    print(f"♻️ [Existing] 遊戲 ID {igdb_id} 已存在，直接執行關聯流程")
                    game = existing_game
                else:
                    # 原本的儲存邏輯，封裝進 Try 防止單筆崩潰
                    try:
                        igdb_raw_name = best_match.get('name', '')
                
                
                        if mapping:
                            # 強制鎖定：名稱、簡介等全部使用 Mapping 或現有 Game 資料
                            # 我們只把 IGDB 的 id, cover, platforms 傳給儲存邏輯
                            best_match['nsuid'] = nsuid

                            best_match['chinese_name'] = mapping.game_name  
                            best_match['name'] = mapping.english_name if mapping.english_name else igdb_raw_name

                            if mapping and not mapping.english_name:
                                # 只有當我們不是在找 Switch 2 遊戲時，才把 IGDB 的名字存入 Mapping
                                if not is_targeting_switch2:
                                    # 存入前先洗乾淨
                                    clean_name = igdb_raw_name.replace("Nintendo Switch 2 Edition", "").replace("Switch 2", "").strip()
                                    mapping.english_name = clean_name
                                    

                        # 執行儲存
                        game = self.store_game_logic(best_match)
                    except Exception as save_err:
                        db.session.rollback() # 🌟 儲存失敗務必回滾
                        print(f"🔥 [Save Error] 存檔失敗: {save_err}")
                        return None

                # 🌟 重要：回填 Mapping 的 ID
                if mapping:
                    if not mapping.igdb_id:
                        mapping.igdb_id = game.id

                    try:
                        db.session.commit() 
                        print(f"🔗 [Link Success] {mapping.game_name} 已綁定 IGDB:{game.id} 與 NSUID:{nsuid}")
                    except Exception as commit_err:
                        db.session.rollback() # 🌟 防止 Session 被鎖死
                        print(f"🔥 [Commit Error] Mapping 更新失敗: {commit_err}")
                
                return game
                
            
            # 🌟 [修正]：如果執行到這裡，代表 best_match 為 None (搜尋無結果)
            print(f"⚠️ [IGDB NotFound] 搜尋無結果，嘗試為 {name} 建立本地基準紀錄")
            if mapping:
                print(f"⚠️ [IGDB NotFound] 執行虛擬綁定流程: {name}")
                # 建立一個簡單的類別，模擬 Game 物件的行為
                class ShadowGame:
                    def __init__(self, m):
                        self.id = None  # ID 設為 None，讓後續查價知道這是無 ID 模式
                        self.name = m.english_name or name
                        self.chinese_name = m.game_name
                        self.cover_url = m.icon_url
                return ShadowGame(mapping)
            
            return None

        except Exception as e:
            print(f"🔥 [Fatal Error] {e}")
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
        
        # 3. 移除括號內的內容 (原本的)
        name = re.sub(r'\(.*?\)', '', name)

        # 刪除常見的 PTT 搜尋地雷符號，但不刪除文字與空格
        name = re.sub(r'[!！?？+＋™®ⓒ@#$%\^&*()_=+\[\]{}|\\;\'\",.<>/?]', '', name)

        # 1. 移除特殊符號，但保留中文字與英數字
        clean = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', name)
        
        # 🌟 關鍵修正：先切斷副標題 (遇到冒號或連字號就切斷)
        #name = re.split(r'[:：\-－]', name)[0]
        
        # 🌟 關鍵修正：要把「中間」的空格也殺掉，不能只用 strip()
        # 同時處理半形空格 " " 和全形空格 "　"
        #name = name.replace(" ", "").replace("　", "")
        
        # 確保回傳的是最乾淨的連體字，例如 "巫師3"
        return name.strip()
    
    def ensure_game_exists(self, game_id, name_fallback="Unknown Game", nsuid=None):
        """
        確保 games 表中一定有這款遊戲，若無則從 IGDB 補完。
        """
        
        # 1. 檢查本地資料庫是否已存在該 ID
        game = db.session.get(Game, game_id)
        
        if not game:
            print(f"📡 [Sync] 偵測到 ID {game_id} 尚未建立主表資料，執行背景同步...")
            try:
                # 2. 透過 IGDB API 獲取完整遊戲資訊
                game_data = self.igdb.get_game_by_id(game_id)
                
                if game_data:
                    if nsuid: 
                        game_data['nsuid'] = nsuid # 🌟 傳遞 nsuid
                    # 3. 調用你現有的 store_game_logic 將其存入 games 表
                    game = self.store_game_logic(game_data)
                    print(f"✅ 已成功補完 Game ID {game_id} 的主表紀錄")
                else:
                    # 4. 如果 IGDB 沒回應，建一個基礎紀錄防止外鍵報錯
                    game = Game(id=game_id, name=name_fallback, chinese_name=name_fallback)
                    db.session.add(game)
                    db.session.commit()
                    print(f"⚠️ IGDB 查無此 ID，已建立基礎紀錄: {game_id}")
            except Exception as e:
                db.session.rollback()
                print(f"❌ 補完遊戲資料時發生錯誤: {e}")
                
        return game
    

    def get_igdb_trending_ids(self, limit=1000):
        """
        🌟 分頁修正版：克服 IGDB 單次 500 筆的限制
        """
        all_ids = []
        page_size = 500  # IGDB 的硬上限
        
        # 計算需要跑幾次迴圈 (例如 1000/500 = 2 次)
        for i in range(0, limit, page_size):
            offset = i
            current_limit = min(page_size, limit - offset)
            
            # 建立分頁查詢語法
            query = (
                f"fields id; "
                f"where (platforms = (130, 167, 48)) & total_rating_count > 0; "
                f"sort total_rating_count desc; "
                f"limit {current_limit}; "
                f"offset {offset};"
            )
            
            try:
                print(f"📡 執行第 {i//page_size + 1} 頁查詢 (Offset: {offset})...")
                results = self.igdb.get_games_by_custom_query(query)
                
                if isinstance(results, list):
                    page_ids = [g['id'] for g in results]
                    all_ids.extend(page_ids)
                    print(f"✅ 本頁成功抓取 {len(page_ids)} 筆")
                else:
                    print(f"❌ 分頁查詢失敗: {results}")
                    break
                    
            except Exception as e:
                print(f"❌ 執行異常: {e}")
                break
                
        print(f"📊 最終累計獲取熱門 ID 共: {len(all_ids)} 筆")
        return all_ids
    

    def _get_ptt_search_strategy(self, search_query):
        """
        🌟 PTT 雙軌搜尋策略：產出『精準關鍵字』與『過濾標籤』
        """
        import re
        
        # 1. 判斷語言與基礎清洗
        clean_query = self.clean_game_name(search_query)
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in clean_query)

        # 2. 核心：雙軌搜尋策略
        parts = re.split(r'[:：\-－/]', clean_query)
        main_title = parts[0].strip()
        sub_title = parts[1].strip() if len(parts) > 1 else ""

        # 初始化輸出
        ptt_keyword = main_title
        filter_tag = None

        if has_chinese:
            # 💡 中文邏輯：判斷主標是否太短 (如: 魔物獵人, 光與影)
            if 0 < len(main_title) <= 2 and sub_title:
                # 策略 A：主標太短，改搜副標，並拿主標當過濾器
                ptt_keyword = sub_title
                filter_tag = main_title[:3] 
            else:
                # 策略 B：主標夠長，合併搜尋以求精準 (如: 魔物獵人世界)
                ptt_keyword = main_title
            
            
            # 清洗中文空格
            ptt_keyword = ptt_keyword.replace(" ", "").replace("　", "")

            ptt_keyword = ptt_keyword.replace("遠徵", "遠征")
        else:
            # 💡 英文邏輯：保留空格，取前兩個單字
            words = clean_query.split()
            if len(words) > 2:
                ptt_keyword = " ".join(words[:2])
                filter_tag = words[2]
            else:
                ptt_keyword = clean_query
                filter_tag = words[0] if words else None

        # 3. 處理 Switch 2 特殊取代
        ptt_keyword = ptt_keyword.replace("NintendoSwitch2Edition", " Switch 2").replace("Switch2Edition", " Switch 2")
        
        # 確保關鍵字不為空
        if not ptt_keyword:
            ptt_keyword = clean_query

        ptt_keyword = ptt_keyword.replace(":", "").replace("：", "").replace("-", "").replace("－", "")

        return ptt_keyword, filter_tag
        
# --- 測試代碼 (當你直接執行此檔案時才會跑) ---
if __name__ == "__main__":
    from app import app
    with app.app_context():
        manager = MainManager()
        
        print("🚀 [測試啟動] 正在嘗試從 IGDB 獲取 1000 筆跨平台熱門遊戲...")
        
        # 🌟 直接呼叫你的目標方法
        trending_ids = manager.get_igdb_trending_ids(limit=1000)
        
        print("-" * 50)
        if trending_ids and len(trending_ids) > 0:
            print(f"✅ 測試成功！")
            print(f"📊 實際抓取筆數: {len(trending_ids)}")
            print(f"🆔 前 10 筆 ID 範例: {trending_ids[:10]}")
            
            # 隨機抽查一筆，看看能不能轉成中文名稱 (確保 ensure_game_exists 也正常)
            test_id = trending_ids[0]
            print(f"🔍 正在測試 ID {test_id} 的認親邏輯...")
            game = manager.ensure_game_exists(test_id)
            if game:
                print(f"🎮 成功對應遊戲: {game.chinese_name} ({game.name})")
        else:
            print("❌ 測試失敗：回傳清單為空。請檢查 IGDB 語法或 total_rating_count 欄位。")
        print("-" * 50)