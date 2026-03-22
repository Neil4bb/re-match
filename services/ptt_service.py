import requests
from bs4 import BeautifulSoup
import time 
import re
from datetime import datetime, timedelta
import random

class PttAdapter:
    def __init__(self):
        self.base_url = "https://www.ptt.cc"
        self.search_url = "https://www.ptt.cc/bbs/Gamesale/search"
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Cookie': 'over18=1',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.ptt.cc/bbs/Gamesale/index.html' # 偽裝來源
        })

    def search_game_prices(self, keyword, platform, limit=3, target_game=None, is_priority=False, filter_tag=None):
        """
        搜尋 PTT 貼文列表，並點進內文進行深度獵殺
        """
        print(f"🚩 [PTT進入] 接收到平台參數: {platform}")

        if target_game is None:
            target_game = keyword

        # 1. 直接使用傳入的 keyword 作為搜尋字串 (因為 MainManager 已經清洗過了)
        search_query = keyword 
        params = {'q': search_query}
        
        try:
            delay = random.uniform(1.5, 3.0) if not is_priority else random.uniform(1.0, 2.0)
            time.sleep(delay)

            self.session.headers.update({'User-Agent': random.choice(self.user_agents)})

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

                # 🌟 [新增] 雙重條件過濾 (filter_tag 驗證)
                # 如果 MainManager 有給過濾標籤，標題必須包含它，才准許點進去耗費流量抓價格
                if filter_tag:
                    if filter_tag.upper() not in title_text.upper():
                        # print(f"⏭️ [Filter] 標題不含 '{filter_tag}'，跳過: {title_text[:15]}...")
                        continue


                # 3. 點進內文精準獵殺價格
                time.sleep(random.uniform(1.0, 2.2))
                article_url = self.base_url + title_link['href']
                
                price = self.get_price_from_content(article_url, target_game)
                
                if price:
                    valid_results.append({
                        'price': price,
                        'date': date_str,
                        'title': title_text,
                        'url': article_url # 補上 URL 方便存入 MarketPrice
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
            # 🌟 [修改 1]：連線異常重試機制，對付 10054 錯誤
            res = None
            for i in range(2):
                try:
                    res = self.session.get(url, timeout=10)
                    if res.status_code == 200:
                        break
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                    if i == 0: # 第一次失敗才等，第二次就放棄
                        print(f"⏳ PTT 連線不穩，5 秒後重試... ({url[-10:]})")
                        time.sleep(5)
                    continue
            
            if not res or res.status_code != 200: return None
            
            content_soup = BeautifulSoup(res.text, 'lxml')
            main_content = content_soup.select_one('#main-content')
            if not main_content: return None
            
            for meta in main_content.select('.article-metaline, .article-metaline-right'):
                meta.decompose()
            
            text = main_content.text

            # 透過 Regex 劃分區塊
            name_match = re.search(r'【物品名稱】\s*[:：]\s*(.*?)(?=【|$)', text, re.S)
            price_match = re.search(r'【售\s+價】\s*[:：]\s*(.*?)(?=【|$)', text, re.S)
            
            if name_match and price_match:
                # 這裡保留你原本的名稱與價格對齊邏輯
                names = name_match.group(1).strip().split('\n')
                prices = price_match.group(1).strip().split('\n')
                
                target_core = re.split(r'[:：！!/／]', target_game)[0].strip()[:4].lower()
                
                target_index = -1
                for i, name in enumerate(names):
                    if target_core in name.lower():
                        target_index = i
                        break
                
                if target_index != -1 and target_index < len(prices):
                    price_line = prices[target_index]
                    found = re.search(r'\d{3,4}', price_line)
                    if found:
                        val = int(found.group())
                        if 100 < val < 5000 and val not in [2025, 2026]:
                            return val

            # 備用方案：若結構化匹配失敗，嘗試全文搜尋（排除常見年份）
            all_nums = re.findall(r'\d{3,4}', text)
            for n_str in all_nums:
                n = int(n_str)
                if 250 < n < 3500 and n not in [2025, 2026]:
                    return n
        except Exception as e:
            print(f"❌ 內文解析出錯: {e}")
            return None
        return None