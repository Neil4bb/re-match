// 1. 查價邏輯
// 修改參數接收：傳入被點擊的按鈕元素 (element)
function fetchMarketPrice(gameId, element, event) {
    if (event) event.preventDefault();

    const cardBody = element.closest('.card-body');
    const btn = element;
    const priceInfo = cardBody.querySelector('.price-info-area');
    
    // 🌟 定義四個顯示格子
    const nsDigitalSpan = cardBody.querySelector('.ns-digital');
    const nsPttSpan = cardBody.querySelector('.ns-ptt');
    const psDigitalSpan = cardBody.querySelector('.ps-digital');
    const psPttSpan = cardBody.querySelector('.ps-ptt');

    const nsuid = btn.getAttribute('data-nsuid');
    const name = btn.getAttribute('data-name');

    btn.classList.add('d-none');
    priceInfo.classList.remove('d-none');
    
    // 全部顯示讀取中
    [nsDigitalSpan, nsPttSpan, psDigitalSpan, psPttSpan].forEach(span => {
        span.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    });

    let url = `/api/market/${gameId}?nsuid=${nsuid || ''}&name=${encodeURIComponent(name || '')}`;

    fetch(url)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // 🌟 填入後端 MainManager 回傳的新欄位
                nsDigitalSpan.innerText = data.ns_digital !== "--" ? `NT$ ${data.ns_digital}` : "--";
                nsPttSpan.innerText = data.ns_ptt !== "--" ? `NT$ ${data.ns_ptt}` : "--";
                psDigitalSpan.innerText = data.ps_digital !== "--" ? `NT$ ${data.ps_digital}` : "--";
                psPttSpan.innerText = data.ps_ptt !== "--" ? `NT$ ${data.ps_ptt}` : "--";
                
                // 保留你原本的 ID 綁定邏輯
                if (data.new_game_id && (gameId === 'None' || gameId === 'null' || gameId === 'None')) {
                    btn.setAttribute('onclick', `fetchMarketPrice('${data.new_game_id}', this, event)`);
                    const wishlistBtn = cardBody.querySelector('button[id^="wishlist-"]');
                    if (wishlistBtn) {
                        wishlistBtn.id = `wishlist-${data.new_game_id}`;
                        wishlistBtn.setAttribute('onclick', `toggleWishlist(this, '${data.new_game_id}')`);
                    }
                }
            }
        })
        .catch(err => {
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