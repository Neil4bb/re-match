// 1. 查價邏輯
function fetchMarketPrice(gameId) {
    const btn = document.getElementById(`btn-query-${gameId}`);
    const priceInfo = document.getElementById(`price-info-${gameId}`);
    const eshopSpan = document.getElementById(`eshop-${gameId}`);
    const pttSpan = document.getElementById(`ptt-${gameId}`);

    // 顯示價格區塊並進入讀取狀態
    btn.classList.add('d-none');
    priceInfo.classList.remove('d-none');
    eshopSpan.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    pttSpan.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

    fetch(`/api/market/${gameId}`)
        .then(response => {
            if (!response.ok) throw new Error('API 無法回應');
            return response.json();
        })
        .then(data => {
            eshopSpan.innerText = data.eshop_price ? `NT$ ${data.eshop_price}` : "查無價格";
            pttSpan.innerText = data.ptt_price ? `NT$ ${data.ptt_price}` : "暫無行情";
        })
        .catch(err => {
            console.error('查價失敗:', err);
            btn.classList.remove('d-none');
            btn.innerText = "❌ 重試";
            priceInfo.classList.add('d-none');
        });
}

// 2. 愛心追蹤邏輯
function toggleWishlist(btn, gameId) {
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