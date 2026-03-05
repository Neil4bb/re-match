import requests
from bs4 import BeautifulSoup
import time # 增加延遲
import re

class PttAdapter:
    def __init__(self):
        self.url = "https://www.ptt.cc/bbs/Gamesale/index.html"
        # 更加擬真的瀏覽器標頭
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.ptt.cc/bbs/index.html',
            'Cookie': 'over18=1' # PTT 有些版會檢查是否滿 18 歲，雖然 Gamesale 不一定強制，但帶著保險
        }
        # 使用 Session 維持連線
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def fetch_latest_posts(self):
        try:
            # 增加一點隨機延遲，避免被秒擋
            time.sleep(1) 
            response = self.session.get(self.url, timeout=10)
            
            if response.status_code != 200:
                print(f"無法連上 PTT！狀態碼: {response.status_code}")
                return []

            soup = BeautifulSoup(response.text, 'lxml')
            titles = soup.select('.r-ent')
            post_data = []

            for item in titles:
                title_div = item.select_one('.title')
                if not title_div:
                    continue
                
                title_text = title_div.text.strip() # .strip() 可以去掉換行符號
                
                
                if "售" in title_text and "徵" not in title_text:
                    post_data.append(title_text)
            
            return post_data

        except Exception as e:
            print(f"發生連線錯誤: {e}")
            return []
        
    def extract_price(self, title):
        """從標題中利用正規表示法抓取 3-5 位數的價格"""
        # 1. 移除掉 PS5, NS2, 3DS 等干擾數字
        # 我們先把 [ ] 裡面的內容暫時拿掉，避免 Regex 抓錯
        clean_title = re.sub(r'\[.*?\]', '', title)

        # 2. 尋找 3 到 5 位數的數字
        # r'\d{3,5}' 的意思是：尋找連續出現 3 到 5 次的數字
        match = re.search(r'\d{3,5}', clean_title)
        
        if match:
            return int(match.group())
        return None

if __name__ == "__main__":
    ptt = PttAdapter()
    posts = ptt.fetch_latest_posts()
    if posts:
        print(f"--- 成功抓取 {len(posts)} 筆資料 ---")
        for p in posts:
            price = ptt.extract_price(p)
            print(f"標題: {p}")
            print(f" => 偵測價格: {price if price else '未偵測到'}")
    else:
        print("依然沒抓到，請確認程式中的 '售' 字是否與網頁上的字元編碼一致。")