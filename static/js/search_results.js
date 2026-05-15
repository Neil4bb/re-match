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
                        // 🌟 核心修正：根據查價結果更新平台屬性
                        // 只要數位或 PTT 有任一邊有價格，就代表該平台可用
                        const hasNS = data.has_ns !== undefined ? data.has_ns : (data.ns_digital !== "--" || data.ns_ptt !== "--");
                        const hasPS = data.has_ps !== undefined ? data.has_ps : (data.ps_digital !== "--" || data.ps_ptt !== "--");
                        
                        wishlistBtn.setAttribute('data-has-ns', hasNS ? 'true' : 'false');
                        wishlistBtn.setAttribute('data-has-ps', hasPS ? 'true' : 'false');
                        
                        // 更新 ID 並綁定新的 handleHeartClick
                        wishlistBtn.id = `wishlist-${data.new_game_id}`;
                        wishlistBtn.setAttribute('onclick', `handleHeartClick(this, '${data.new_game_id}')`);
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
/*function toggleWishlist(btn, gameId) {
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
}*/

// 智慧愛心點擊處理
function handleHeartClick(btn, gameId) {
    if (gameId === 'None' || gameId === 'null') {
        alert("請先點擊「查詢行情」後再加入！");
        return;
    }

    const hasNS = btn.getAttribute('data-has-ns') === 'true';
    const hasPS = btn.getAttribute('data-has-ps') === 'true';

    if (hasNS && hasPS) {
        let popover = bootstrap.Popover.getInstance(btn);
        if (!popover) {
            popover = new bootstrap.Popover(btn, {
                html: true,
                content: () => document.getElementById('platform-menu-html').innerHTML,
                trigger: 'manual',
                placement: 'top',
                container: 'body', // 🌟 解決彈不出窗的關鍵
                sanitize: false    // 🌟 讓紅圓點按鈕能點擊的關鍵
            });

            // 🌟 關鍵：監聽 Bootstrap 的 shown 事件
            btn.addEventListener('shown.bs.popover', function () {
                // 1. 找到 Bootstrap 隨機生成的 Popover 外層容器 ID
                const popoverId = btn.getAttribute('aria-describedby');
                const popoverDom = document.getElementById(popoverId);
                
                if (popoverDom) {
                    // 2. 必須在 popoverDom 裡面找按鈕，不能在 document 找
                    const nsBtn = popoverDom.querySelector('.btn-ns-action');
                    const psBtn = popoverDom.querySelector('.btn-ps-action');

                    if (nsBtn) {
                        nsBtn.onclick = (e) => {
                            e.stopPropagation(); // 防止事件冒泡
                            executeAdd(gameId, 'ns', btn);
                            popover.hide();
                        };
                    }
                    if (psBtn) {
                        psBtn.onclick = (e) => {
                            e.stopPropagation();
                            executeAdd(gameId, 'ps', btn);
                            popover.hide();
                        };
                    }
                }
            });
        }
        popover.toggle();
    } else {
        const platform = hasNS ? 'ns' : 'ps';
        executeAdd(gameId, platform, btn);
    }
}

function executeAdd(gameId, platform, btn) {
    fetch(`/add_to_assets/${gameId}?platform=${platform}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                btn.style.color = "red";
                alert(`已加入 ${platform.toUpperCase()} 願望清單！`);
            }
        });
}