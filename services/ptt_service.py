import requests
from bs4 import BeautifulSoup
import time 
import re
from datetime import datetime, timedelta

class PttAdapter:
    def __init__(self):
        self.base_url = "https://www.ptt.cc"
        self.search_url = "https://www.ptt.cc/bbs/Gamesale/search"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Cookie': 'over18=1' 
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def search_game_prices(self, game_name, platform, limit=3, target_game=None):
        """
        搜尋 PTT 貼文列表，並點進內文進行深度獵殺
        """
        print(f"🚩 [PTT進入] 接收到平台參數: {platform}")

        if target_game is None:
            target_game = game_name

        # 關鍵字清洗：移除特殊符號以增加搜尋命中率
        search_query = re.split(r'[:：！!/／]', game_name)[0].strip()
        params = {'q': search_query} 
        
        try:
            time.sleep(1.2) # 稍微增加延遲避免被 PTT 封鎖
            response = self.session.get(self.search_url, params=params, timeout=10)
            if response.status_code != 200: return []

            soup = BeautifulSoup(response.text, 'lxml')
            posts = soup.select('.r-ent')
            valid_results = []
            # 設定一個月的效期
            one_month_ago = datetime.now() - timedelta(days=30)

            for item in posts:
                # 1. 日期篩選邏輯
                date_str = item.select_one('.date').text.strip()
                try:
                    current_year = datetime.now().year
                    post_date = datetime.strptime(f"{current_year}/{date_str}", "%Y/%m/%d")
                    if post_date > datetime.now(): 
                        post_date = post_date.replace(year=current_year - 1)
                    if post_date < one_month_ago: continue 
                except: continue

                # 2. 標題初步過濾
                title_link = item.select_one('.title a')
                if not title_link: continue
                title_text = title_link.text.strip()

                if platform.upper() not in title_text.upper():
                    continue

                if "售" not in title_text or "徵" in title_text: continue

                # 3. 點進內文精準獵殺價格
                article_url = self.base_url + title_link['href']
                price = self.get_price_from_content(article_url, target_game)
                
                if price:
                    valid_results.append({
                        'price': price,
                        'date': date_str,
                        'title': title_text
                    })
                    print(f"✅ 內文抓取成功: {title_text[:15]}... 價格: {price}")
                
                if len(valid_results) >= limit: break
                time.sleep(0.6) # 內文點擊間隔
            
            return valid_results
        except Exception as e:
            print(f"❌ PTT 搜尋 {search_query} 失敗: {e}")
            return []

    def get_price_from_content(self, url, target_game):
        """
        深入文章內文，對齊「物品名稱」與「售價」的順序
        """
        try:
            res = self.session.get(url, timeout=10)
            if res.status_code != 200: return None
            
            content_soup = BeautifulSoup(res.text, 'lxml')
            main_content = content_soup.select_one('#main-content')
            if not main_content: return None
            
            # 清除 Meta 雜訊（作者、看板、標題、時間），防止 Regex 誤抓作者 ID 裡的數字
            for meta in main_content.select('.article-metaline, .article-metaline-right'):
                meta.decompose()
            
            text = main_content.text

            # 透過 Regex 劃分區塊
            name_match = re.search(r'【物品名稱】：(.*?)【', text, re.S)
            price_match = re.search(r'【售\s+價】：(.*?)【', text, re.S)
            
            if name_match and price_match:
                names = name_match.group(1).strip().split('\n')
                prices = price_match.group(1).strip().split('\n')
                
                # 取得目標遊戲核心關鍵字（前 4 字）進行匹配
                target_core = re.split(r'[:：！!/／]', target_game)[0].strip()[:4].lower()
                
                target_index = -1
                for i, name in enumerate(names):
                    if target_core in name.lower():
                        target_index = i
                        break
                
                # 若找到索引，則抓取售價區塊對應行的數字
                if target_index != -1 and target_index < len(prices):
                    price_line = prices[target_index]
                    # 搜尋該行中的 3~4 位數字
                    found = re.search(r'\d{3,4}', price_line)
                    if found:
                        val = int(found.group())
                        # 過濾掉年份 (2025/2026) 與過低價格
                        if 100 < val < 5000 and val not in [2025, 2026]:
                            return val

            # 備用方案：若結構化匹配失敗，嘗試全文搜尋（排除常見年份）
            all_nums = re.findall(r'\d{3,4}', text)
            for n_str in all_nums:
                n = int(n_str)
                if 250 < n < 3500 and n not in [2025, 2026]:
                    return n
        except:
            return None
        return None