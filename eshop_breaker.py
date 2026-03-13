import requests
import re

def test_hk_eshop_v3(game_name):
    # 改回正式搜尋網址，這是你在 .har 檔中看到的真實路徑
    url = "https://store.nintendo.com.hk/eshopsearch/result/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1"
    }

    params = {"q": game_name}

    try:
        print(f"📡 正在請求搜尋頁面: {game_name}")
        # 使用 Session 可以維持 Cookie，比較不容易被擋
        session = requests.Session()
        response = session.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"❌ 失敗，狀態碼: {response.status_code}")
            return

        # 直接從回傳的完整網頁 HTML 中抓取 NSUID
        html_content = response.text
        
        # 尋找 7001 開頭的 14 位數字
        nsuids = re.findall(r'7001\d{10}', html_content)
        
        if nsuids:
            # 去重並過濾
            nsuids = list(dict.fromkeys(nsuids))
            print(f"✅ 成功獲取 NSUIDs: {nsuids}")
            
            # 嘗試抓取產品圖片連結
            images = re.findall(r'https://[^"]+product[^"]+\.jpg', html_content)
            if images:
                print(f"📸 發現圖片: {images[0]}")
        else:
            print("⚠️ 頁面載入成功，但裡面沒看到 NSUID。這可能是因為頁面需要 JS 渲染。")
            
    except Exception as e:
        print(f"💥 發生錯誤: {e}")

if __name__ == "__main__":
    test_hk_eshop_v3("Persona 5")