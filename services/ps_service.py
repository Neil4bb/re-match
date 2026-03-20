import requests
import re
import json
from urllib.parse import quote

class PSStoreService:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-TW,zh;q=0.9'
        }

    def _find_products_recursive(self, data, results):
        """同步測試版邏輯：遞迴搜尋 JSON 結構中的正式版遊戲"""
        if isinstance(data, dict):
            classification = data.get('storeDisplayClassification') or data.get('localizedStoreDisplayClassification')
            # 嚴格對齊測試版分類
            if classification in ['FULL_GAME', '正式版遊戲']:
                name = data.get('name')
                price_data = data.get('price', {})
                price_str = price_data.get('discountedPrice') or price_data.get('basePrice')
                
                if name and price_str:
                    price_val = int(re.sub(r'[^\d]', '', str(price_str)))
                    results.append({
                        'name': name,
                        'price': price_val,
                        'id': data.get('id')
                    })
            for v in data.values():
                self._find_products_recursive(v, results)
        elif isinstance(data, list):
            for item in data:
                self._find_products_recursive(item, results)

    def _perform_ps_search(self, query_str, search_terms):
        """同步測試版邏輯：執行單次搜尋並進行關鍵字比對"""
        url = f"https://store.playstation.com/zh-hant-tw/search/{quote(query_str)}"
        try:
            res = requests.get(url, headers=self.headers, timeout=15)
            # 使用測試版同款 Regex 抓取 NEXT_DATA
            json_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', res.text)
            if not json_match: return None

            all_products = []
            self._find_products_recursive(json.loads(json_match.group(1)), all_products)

            unique_matches = []
            seen_ids = set()
            for p in all_products:
                if p['id'] not in seen_ids:
                    p_name_lower = p['name'].lower()
                    # 只要名稱包含任一關鍵字就算命中 (同步測試版)
                    if any(term in p_name_lower for term in search_terms):
                        unique_matches.append(p)
                        seen_ids.add(p['id'])
            
            # 返回最便宜的符合項
            return sorted(unique_matches, key=lambda x: x['price'])[0] if unique_matches else None
        except Exception as e:
            print(f"❌ PS 單次搜尋失敗 ({query_target}): {e}")
            return None

    def get_game_price(self, en_name, cn_name=None):
        """
        同步測試版邏輯：雙階段搜尋實施 (verify_ps_dual_search)
        """
        search_terms = []
        query_target = ""
        
        # 1. 中文關鍵字提取邏輯 (同步測試版)
        if cn_name:
            clean_cn = re.sub(r'[《》]', '', cn_name)
            core_cn = re.split(r'[:：\-－+＋]', clean_cn)[0].strip()
            if core_cn:
                search_terms.append(core_cn.lower())
                query_target = core_cn
                
        # 2. 英文關鍵字提取邏輯 (同步測試版)
        clean_en_full = re.sub(r'[:：\-－+＋《》]', ' ', en_name).lower()
        en_words = clean_en_full.split()
        skip_words = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with'}
        meaningful_en = next((w for w in en_words if w not in skip_words), "")
        if meaningful_en:
            search_terms.append(meaningful_en)
            if not query_target: query_target = meaningful_en

        print(f"🎮 [PS Store] 搜尋目標: {query_target} | 比對清單: {search_terms}")

        # --- 雙階段搜尋實施 ---
        # 第一階段：使用 query_target (中文核心或英文核心)
        result = self._perform_ps_search(query_target, search_terms)
        
        # 第二階段：Fallback 嘗試原始全名搜尋
        if not result:
            print(f"📡 [PS Fallback] 嘗試原始名稱: {en_name}")
            result = self._perform_ps_search(en_name, search_terms)

        if result:
            # 格式化回傳，補上 URL
            result['url'] = f"https://store.playstation.com/zh-hant-tw/product/{result['id']}"
            return result
        return None