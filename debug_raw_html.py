import requests
import re

def final_nsuid_hunt(keyword_zh):
    # 這是目前香港官網「所有軟體」的清單入口
    url = "https://www.nintendo.com.hk/software/switch/index.html"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    print(f"--- 正在執行最後的 NSUID 獵殺: {keyword_zh} ---")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        print(f"狀態碼: {response.status_code}")
        
        if response.status_code == 200:
            html = response.text
            # 強力提取所有 7001 開頭的 14 位數
            all_uids = re.findall(r'7001\d{10}', html)
            
            if all_uids:
                unique_uids = list(set(all_uids))
                print(f"✅ 成功！在列表頁發現 {len(unique_uids)} 個 NSUID。")
                print(f"前 5 個範例: {unique_uids[:5]}")
                
                # 檢查關鍵字是否在同一行 (簡單過濾)
                if keyword_zh in html:
                    print(f"🎯 頁面中包含關鍵字 '{keyword_zh}'，理論上可以對齊！")
                return True
            else:
                print("❌ 頁面讀取成功，但裡面依然沒有 7001 數字。")
        else:
            print("❌ 連列表頁都 404，這不科學。")
            
    except Exception as e:
        print(f"💥 獵殺失敗: {e}")
    return False

if __name__ == "__main__":
    # 這次我們用最精準的中文關鍵字測試
    final_nsuid_hunt("巫師")