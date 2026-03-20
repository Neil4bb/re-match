import requests
import re
import json
from urllib.parse import quote

def find_products_recursive(data, results):
    """遞迴搜尋 JSON 結構中的所有商品"""
    if isinstance(data, dict):
        classification = data.get('storeDisplayClassification') or data.get('localizedStoreDisplayClassification')
        # 標籤驗證：截圖顯示本體為 PS5/PS4 正式版遊戲
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
            find_products_recursive(v, results)
    elif isinstance(data, list):
        for item in data:
            find_products_recursive(item, results)

def perform_ps_search(query_str, search_terms):
    """執行單次搜尋並進行比對"""
    url = f"https://store.playstation.com/zh-hant-tw/search/{quote(query_str)}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        json_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', res.text)
        if not json_match: return None

        all_products = []
        find_products_recursive(json.loads(json_match.group(1)), all_products)

        unique_matches = []
        seen_ids = set()
        for p in all_products:
            if p['id'] not in seen_ids:
                # 只要名稱包含任一關鍵字就算命中
                p_name_lower = p['name'].lower()
                if any(term in p_name_lower for term in search_terms):
                    unique_matches.append(p)
                    seen_ids.add(p['id'])
        
        # 返回最便宜的符合項 (通常是標準版)
        return sorted(unique_matches, key=lambda x: x['price'])[0] if unique_matches else None
    except:
        return None

def verify_ps_dual_search(game_name, chinese_name=None):
    # --- 1. 核心關鍵字提取 (優化版) ---
    search_terms = []
    
    # 決定發給 Sony 的搜尋字串
    query_target = ""
    
    if chinese_name:
        # 移除書名號，提取核心名稱作為搜尋目標與比對關鍵字
        clean_cn = re.sub(r'[《》]', '', chinese_name)
        core_cn = re.split(r'[:：\-－+＋]', clean_cn)[0].strip()
        if core_cn:
            search_terms.append(core_cn.lower())
            query_target = core_cn # 搜尋目標優先設為中文核心
            
    # 英文核心處理
    clean_en_full = re.sub(r'[:：\-－+＋《》]', ' ', game_name).lower()
    en_words = clean_en_full.split()
    skip_words = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with'}
    meaningful_en = next((w for w in en_words if w not in skip_words), "")
    if meaningful_en:
        search_terms.append(meaningful_en)
        if not query_target: query_target = meaningful_en

    print(f"\n🔎 準備搜尋。搜尋目標: {query_target} | 比對清單: {search_terms}")

    # --- 2. 雙階段搜尋實施 ---
    result = perform_ps_search(query_target, search_terms)
    
    # 如果中文/主標題搜尋失敗，嘗試原始全名搜尋
    if not result:
        print(f"📡 [Fallback] 嘗試使用原始名稱搜尋: {game_name}")
        result = perform_ps_search(game_name, search_terms)

    # 最終輸出
    if result:
        print(f"🎯 [Success] 判定結果: {result['name']}")
        print(f"💰 價格: NT$ {result['price']}")
        print(f"🔗 ID: {result['id']}")
        return result
    else:
        print(f"❌ [Fail] 無法找到匹配項目。")
        return None

if __name__ == "__main__":
    # 測試 Witcher
    verify_ps_dual_search("The Witcher 3: Wild Hunt", "《巫師 3：狂獵》")
    # 測試 Sekiro
    verify_ps_dual_search("Sekiro: Shadows Die Twice", "隻狼：暗影雙死")