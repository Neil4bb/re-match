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
        # 🌟 用來擋掉標題太像的黑名單清單 (包含中文與英文)
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
            
            # 🌟 關鍵優化：將本地中文名稱「去空格」後加入比對
            local_titles.append(m.game_name.replace(" ", "").lower())
            
            # 🌟 關鍵優化：如果字典有英文名，也「去空格」後加入比對
            # 這能有效擋掉像 "The Legend of Zelda" 這種 IGDB 英文結果
            if hasattr(m, 'english_name') and m.english_name:
                local_titles.append(m.english_name.replace(" ", "").lower())

        # 2. 抓取 IGDB 並執行去重
        igdb_items = self.igdb.search_game(query)
        additional_results = []
        
        for item in igdb_items:
            # 判斷 1：ID 是否完全相同
            is_duplicate = (item['id'] in seen_igdb_ids)
            
            # 判斷 2：名稱模糊比對 (處理分身 ID)
            if not is_duplicate:
                # 🌟 將 IGDB 名字也「去空格」處理
                clean_igdb_name = item['name'].replace(" ", "").lower()
                
                for lt in local_titles:
                    # 雙向包含檢查：解決 "P5R" vs "Persona 5 Royal" 或中文 vs 英文包含問題
                    if clean_igdb_name in lt or lt in clean_igdb_name:
                        is_duplicate = True
                        print(f"🚫 [去重成功] 偵測到名稱重複: {item['name']} (與本地 {lt} 衝突)")
                        break

            # 判斷 3：硬編碼黑名單 (保留你原本的判斷)
            if item['id'] == 150080:
                is_duplicate = True

            if not is_duplicate:
                item['is_local'] = False
                additional_results.append(item)

        return local_results + additional_results

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
            
            # ---------------------------------------------------------
            # 🌟 [重點：在此處加入保護邏輯] 🌟
            # 在準備開始存檔之前，確保 game_id 在 games 表中有紀錄
            if game_id:
                # 調用剛才寫好的 ensure_game_exists
                self.ensure_game_exists(game_id, name_fallback=search_query, nsuid=nsuid)
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
            if nsuid:
                print(f"📡 [eShop] 使用 NSUID 查價: {nsuid}")
                self.eshop.get_price_twd(game_id, nsuid)
                rec = MarketPrice.query.filter_by(game_id=game_id, title=f"eShop_{nsuid}").first()
                results['ns_digital'] = rec.price if rec else "--"
            

            # 4. --- PTT 分平台區域 ---
            
            clean_query = self.clean_game_name(search_query)
            ptt_keyword = re.split(r'[:：\-－]', clean_query)[0]
            ptt_keyword = ptt_keyword.replace(" ", "").replace("　", "")
            ptt_keyword = ptt_keyword.replace("NintendoSwitch2Edition", " Switch 2").replace("Switch2Edition", " Switch 2")
            
            print(f"🕵️ [PTT] 最終送往爬蟲的關鍵字: {ptt_keyword}")
            

            # --- 第一次執行：獲取 PS 價格 ---
            ptt_results_ps = self.ptt.search_game_prices(ptt_keyword, "PS")
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
            ptt_results_ns = self.ptt.search_game_prices(ptt_keyword, "NS")
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
                print(f"✅ [Final Match] ID: {best_match['id']} | 平台清單: {[p.get('name') for p in best_match.get('platforms', [])]}")
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
                    # 同步更新 Mapping 表的英文名
                    #if not mapping.english_name:
                    #    mapping.english_name = igdb_original_english

                    # 🌟 重要：執行儲存
                    game = self.store_game_logic(best_match)

                    # 🌟 重要：回填 ID 並強制 Commit
                    if not mapping.igdb_id:
                        mapping.igdb_id = game.id

                    db.session.commit() # 確保 Mapping 與 GamePlatformID 同時入庫
                    print(f"🔗 [Link Success] {mapping.game_name} 已綁定 IGDB:{game.id} 與 NSUID:{nsuid}")
                    return game
                
                
                # store_game_logic 會根據 best_match['platforms'] 自動更新 GamePlatformID 表
                return self.store_game_logic(best_match)
            
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
        from models import Game
        
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