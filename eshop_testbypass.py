from curl_cffi import requests
import re
import time
import random

def repair_eshop_scraper(game_name):
    # 使用 Session 保持連貫性
    session = requests.Session()
    
    # 1. 設置更完整的瀏覽器標頭
    base_headers = {
        "Authority": "store.nintendo.com.hk",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        # 第一步：首頁預熱 (模擬正常進入)
        print("📡 [修正中] 正在模擬進入首頁...")
        session.get(
            "https://store.nintendo.com.hk/", 
            headers=base_headers, 
            impersonate="chrome120", 
            timeout=15
        )
        
        # 關鍵：模擬人類輸入搜尋詞的時間
        time.sleep(random.uniform(2.0, 4.0))

        # 第二步：模擬搜尋動作
        search_url = "https://store.nintendo.com.hk/eshopsearch/result/"
        
        # 增加搜尋時的標頭
        search_headers = base_headers.copy()
        search_headers.update({
            "Referer": "https://store.nintendo.com.hk/",
            "Sec-Fetch-Site": "same-origin", # 告訴伺服器這是從同網站跳轉的
        })

        print(f"📡 [修正中] 正在發起關鍵字搜尋: {game_name}")
        # 強制使用 http2=True (curl_cffi 預設通常會處理，但我們可以確保它)
        response = session.get(
            search_url, 
            params={"q": game_name}, 
            headers=search_headers, 
            impersonate="chrome120",
            timeout=15
        )

        print(f"📡 最終狀態碼: {response.status_code}")
        
        if response.status_code == 200:
            nsuids = re.findall(r'7001\d{10}', response.text)
            if nsuids:
                print(f"✅ 成功修復！NSUID: {nsuids[0]}")
                return nsuids[0]
            else:
                print("❌ 狀態碼 200 但沒抓到 ID，請檢查 HTML 內容。")
        else:
            print(f"❌ 依然被擋，狀態碼: {response.status_code}")

    except Exception as e:
        print(f"💥 異常: {e}")

if __name__ == "__main__":
    repair_eshop_scraper("薩爾達傳說")