import time
import random
import os
import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from app import app
from extensions import db
from models import EShopMapping
from services.eshop_service import EShopService

# 設定執行參數
INTERVAL_MINUTES = 12
BATCH_LIMIT = 5

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('apscheduler')

def fetch_nsuid_task():
    service = EShopService()
    print(f"\n⏰ [背景任務啟動] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    with app.app_context():
        # 抓取尚未配對 NSUID 的遊戲
        pending_list = EShopMapping.query.filter(
            EShopMapping.nsuid == None
        ).limit(BATCH_LIMIT).all()
        
        if not pending_list:
            print("📭 目前暫無需要填補的遊戲資料。")
            return

        for mapping in pending_list:
            print(f"🔍 正在抓取: {mapping.game_name}")
            
            # 執行 eShop 搜尋
            result = service.search_nsuid(mapping.game_name)
            
            if result and isinstance(result, dict):
                mapping.nsuid = result.get('nsuid')
                mapping.eshop_name = result.get('eshop_name')
                print(f"✅ 成功填補: {mapping.eshop_name} ({mapping.nsuid})")
            else:
                # 沒抓到則更新時間戳記，避免排序永遠卡在同一批失敗的資料
                mapping.last_updated = db.func.now()
                print(f"❌ 搜尋無果: {mapping.game_name}")
            
            db.session.commit()
            
            # 每一筆遊戲之間的隨機等待，模擬真人行為
            wait_time = random.uniform(10.0, 20.0)
            print(f"😴 冷卻 {wait_time:.1f} 秒...")
            time.sleep(wait_time)
            
    print(f"🏁 任務結束，等待下一次執行（12 分鐘後）")

if __name__ == "__main__":
    os.environ['PYTHONPATH'] = '.'
    scheduler = BlockingScheduler()
    
    # 容器啟動後立刻跑第一次
    scheduler.add_job(
        fetch_nsuid_task, 
        'interval', 
        minutes=INTERVAL_MINUTES, 
        next_run_time=datetime.now()
    )
    
    print(f"🚀 背景服務啟動：每 {INTERVAL_MINUTES} 分鐘抓取 {BATCH_LIMIT} 筆...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 服務已停止")