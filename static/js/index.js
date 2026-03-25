
// 1. 全域變數定義
let nextPage = 2;       // 因為第 1 頁已經由 Flask 直接渲染了
let is_loading = false; 
let hasNextPage = true; 
// 從 URL 取得當前平台 (ns 或 ps)
const currentPlatform = new URLSearchParams(window.location.search).get('platform') || 'ns';

// 2. 監聽捲動事件
window.onscroll = function() {
    // 檢查是否接近底部 300px
    if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 300) {
        if (!is_loading && hasNextPage) {
            fetchNextBatch();
        }
    }
};

// 3. 核心抓取函式
function fetchNextBatch() {
    is_loading = true;
    const spinner = document.getElementById('loading-spinner');
    if (spinner) spinner.style.display = 'block';

    fetch(`/api/games?page=${nextPage}&platform=${currentPlatform}`)
        .then(res => res.json())
        .then(data => {
            if (data.games.length > 0) {
                renderGames(data.games);
                nextPage++;
                hasNextPage = data.has_next;
            } else {
                hasNextPage = false;
            }
            is_loading = false;
            if (spinner) spinner.style.display = 'none';
        })
        .catch(err => {
            console.error("載入失敗:", err);
            is_loading = false;
            if (spinner) spinner.style.display = 'none';
        });
}

// 4. 渲染 HTML 函式 (需對齊你原本 index.html 的卡片樣式)
function renderGames(games) {
    const container = document.getElementById('game-container');
    const platform = new URLSearchParams(window.location.search).get('platform') || 'ns';
    const badgeClass = platform === 'ns' ? 'bg-danger' : 'bg-primary';
    const platformName = platform === 'ns' ? 'Nintendo' : 'PlayStation';

    games.forEach(game => {
        // 🌟 這裡必須與 index.html 的 <tr> 結構完全一致
        const row = `
            <tr>
                <td class="ps-4">
                    <div class="d-flex align-items-center">
                        <a href="/game/${game.id}" class="text-decoration-none">
                            <img src="${game.cover_url}" class="rounded shadow-sm me-3" 
                                style="width: 50px; height: 65px; object-fit: cover;" loading="lazy">
                        </a>
                        <div>
                            <div class="fw-bold">
                                <a href="/game/${game.id}" class="text-decoration-none">
                                    ${game.chinese_name || game.name}
                                </a>
                            </div>
                            <span class="badge ${badgeClass} opacity-75" style="font-size: 0.65rem;">
                                ${platformName}
                            </span>
                        </div>
                    </div>
                </td>
                <td class="${game.is_digital_cheaper ? 'text-success fw-bold' : ''}">
                    ${game.digital_price !== 'N/A' && game.digital_price ? 'NT$ ' + game.digital_price : '<span class="text-muted small">-</span>'}
                </td>
                <td class="fw-bold">
                    ${game.retail_price !== 'N/A' && game.retail_price ? 'NT$ ' + game.retail_price : '<span class="text-muted small">-</span>'}
                </td>
                <td>
                    <span class="badge ${game.is_digital_cheaper ? 'bg-success' : 'bg-secondary'}">
                        ${game.suggestion}
                    </span>
                    ${game.diff > 0 ? `<div class="small text-muted mt-1">價差: NT$ ${game.diff}</div>` : ''}
                </td>
                <td class="pe-4">
                    <a href="/add_to_assets/${game.id}?platform=${platform}" 
                    class="btn btn-sm btn-outline-primary btn-track" 
                    data-id="${game.id}">追蹤</a>
                </td>
            </tr>
        `;
        container.insertAdjacentHTML('beforeend', row);
    });
}

document.addEventListener('click', function(e) {
    // 檢查點擊的是否為追蹤按鈕 (我們稍後會在 HTML 加上 btn-track 這個 class)
    if (e.target && e.target.classList.contains('btn-track')) {
        e.preventDefault(); // 🛑 阻止 <a> 標籤跳轉
        
        const btn = e.target;
        
        // 🌟 關鍵修改：直接抓取 href 屬性，這包含了 Flask 渲染的 ?platform=ps
        const url = btn.getAttribute('href');

        // 防止重複發送
        if (btn.disabled) return;
        btn.disabled = true;

        fetch(url, {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                // ✨ 更新按鈕樣式：變色、換字
                btn.classList.remove('btn-outline-primary');
                btn.classList.add('btn-success');
                btn.innerHTML = '✓ 已追蹤';
                btn.disabled = true; // 追蹤後禁用按鈕
            } else {
                alert(data.message || '追蹤失敗');
                btn.disabled = false;
            }
        })
        .catch(err => {
            console.error('追蹤錯誤:', err);
            btn.disabled = false;
        });
    }
});