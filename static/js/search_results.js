// 1. 查價邏輯
// 修改參數接收：傳入被點擊的按鈕元素 (element)
function fetchMarketPrice(gameId, element, event) {
    // 阻止傳統按鈕行為 (如果有的話)
    if (event) event.preventDefault();

    // 1. 【核心修正】精準尋找 UI 元素 (不再依賴 ID)
    // 先找到這張遊戲卡片的根元素
    const cardBody = element.closest('.card-body');
    
    // 從 cardBody 裡面往下尋找讀取/價格區域
    const btn = element;
    const priceInfo = cardBody.querySelector('.price-info-area');
    const eshopSpan = cardBody.querySelector('.eshop-price');
    const pttSpan = cardBody.querySelector('.ptt-price');

    // 2. 獲取 data 屬性裡的資訊
    const nsuid = btn.getAttribute('data-nsuid');
    const name = btn.getAttribute('data-name');

    // 顯示讀取狀態 (精準操作這張卡片的 UI)
    btn.classList.add('d-none');
    priceInfo.classList.remove('d-none');
    eshopSpan.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    pttSpan.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

    // 3. 構建正確的 URL
    let url = `/api/market/${gameId}?nsuid=${nsuid || ''}&name=${encodeURIComponent(name || '')}`;

    fetch(url)
        .then(response => {
            if (!response.ok) throw new Error('API 無法回應');
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                eshopSpan.innerText = data.eshop_price ? `NT$ ${data.eshop_price}` : "查無價格";
                pttSpan.innerText = data.ptt_price ? `NT$ ${data.ptt_price}` : "暫無行情";
                
                if (data.new_game_id && (gameId === 'None' || gameId === 'null')) {
                    console.log(`✅ 成功綁定新 ID: ${data.new_game_id}`);
                    
                    // 1. 更新查價按鈕 (下次點擊重試時用正確 ID)
                    btn.setAttribute('onclick', `fetchMarketPrice('${data.new_game_id}', this, event)`);
                    
                    // 2. 更新愛心按鈕：尋找同一個卡片內的愛心按鈕
                    const wishlistBtn = cardBody.querySelector('button[id^="wishlist-"]');
                    if (wishlistBtn) {
                        wishlistBtn.id = `wishlist-${data.new_game_id}`;
                        // 重新綁定 onclick 事件，傳入新的 ID
                        wishlistBtn.setAttribute('onclick', `toggleWishlist(this, '${data.new_game_id}')`);
                    }
                }

            } else {
                throw new Error(data.message);
            }
        })
        .catch(err => {
            console.error('查價失敗:', err);
            // 精準重置這張卡片的按鈕
            btn.classList.remove('d-none');
            btn.innerText = "❌ 重試";
            priceInfo.classList.add('d-none');
        });
}

// 2. 愛心追蹤邏輯
function toggleWishlist(btn, gameId) {
    // 【防呆】如果 ID 還是 None，說明還沒查過價
    if (gameId === 'None' || gameId === 'null') {
        alert("請先點擊「查詢行情」獲取遊戲資訊後再加入願望清單！");
        return;
    }

    // 使用 POST 發送，符合後端 add_to_assets 的安全改動
    fetch(`/add_to_assets/${gameId}`, { method: 'POST' })
        .then(response => {
            if (response.ok) {
                // 成功後將愛心變紅
                btn.style.color = "red";
                // 點擊後禁用按鈕防止重複點擊
                btn.onclick = null; 
                btn.style.cursor = "default";
            } else {
                alert("加入失敗，請稍後再試");
            }
        })
        .catch(err => console.error('加入願望清單失敗:', err));
}