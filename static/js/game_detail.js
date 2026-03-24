// static/js/game_detail.js

function refreshPrice(gameId) {
    const btn = document.getElementById('refresh-btn');
    if (!btn) return;
    
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm spinner-border-width-2 me-1"></span> 更新中...';

    fetch(`/api/game/${gameId}/refresh`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                location.reload();
            } else {
                alert('更新失敗: ' + data.message);
                btn.disabled = false;
                btn.innerHTML = '即時更新行情';
            }
        });
}

function createGameChart(canvasId, label, chartData, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !chartData || !chartData.labels || !chartData.labels.length) return; 

    const ctx = canvas.getContext('2d');
    
    // 🌟 1. 計算 Y 軸動態上下限 (Buffer logic)
    // 將所有有效價格合併為一個陣列
    const allPrices = [
        ...chartData.digital_values,
        ...chartData.ptt_values
    ].filter(v => v !== null && v !== undefined && !isNaN(v)); // 過濾掉 N/A 資料

    let yMin = 0; // 預設下限為 0
    let yMax = 2000; // 預設上限 (防止完全沒資料時圖表崩潰)

    if (allPrices.length > 0) {
        const maxPrice = Math.max(...allPrices);
        const minPrice = Math.min(...allPrices);
        
        yMax = maxPrice + 200; // 🌟 上限 = 最高點 + 200
        yMin = Math.max(0, minPrice - 200); // 🌟 下限 = 最低點 - 200 (且不小於 0)
    }

    // 🌟 2. 重新初始化圖表物件
    // 如果該畫布已有圖表，先銷毀它以免疊圖
    let existingChart = Chart.getChart(canvasId);
    if (existingChart) { existingChart.destroy(); }

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: '官方數位版',
                    data: chartData.digital_values,
                    borderColor: color, // NS 用紅色, PS 用藍色
                    backgroundColor: color,
                    tension: 0.2,
                    spanGaps: true,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    borderWidth: 2,
                    fill: false // 不填充背景色
                },
                {
                    label: 'PTT 二手價',
                    data: chartData.ptt_values,
                    borderColor: '#6c757d', // 統一灰色
                    // 🌟 3. 移除 borderDash (虛線改實線)
                    borderDash: [], // 空陣列即為實線
                    backgroundColor: '#6c757d',
                    tension: 0.2,
                    spanGaps: true,
                    pointRadius: 4,
                    borderWidth: 2,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                // 在圖表區塊周圍增加內距，確保 Tooltip 或圓點不會被切到
                padding: { top: 10, bottom: 10, left: 5, right: 5 }
            },
            scales: {
                x: {
                    grid: { display: false } // 隱藏 X 軸網格線，視覺更乾淨
                },
                y: {
                    // 🌟 4. 設定動態計算出的上下限
                    min: yMin,
                    max: yMax,
                    beginAtZero: false, 
                    ticks: {
                        // 格式化 Y 軸文字：NT$ 1,200
                        callback: function(value) {
                            return 'NT$ ' + value.toLocaleString();
                        }
                    }
                }
            },
            plugins: { 
                title: { display: true, text: label, font: { size: 16 } },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) { label += ': '; }
                            if (context.parsed.y !== null) {
                                label += 'NT$ ' + context.parsed.y.toLocaleString();
                            } else {
                                label += 'N/A';
                            }
                            return label;
                        }
                    }
                }
            }
        }
    });
}

// 初始化兩張圖
document.addEventListener('DOMContentLoaded', function() {
    // 從 game_detail.html 底部拿到的資料
    if (typeof nsChartData !== 'undefined') {
        createGameChart('nsChart', 'Nintendo Switch 價格趨勢', nsChartData, '#dc3545');
    }
    if (typeof psChartData !== 'undefined') {
        createGameChart('psChart', 'PlayStation 價格趨勢', psChartData, '#007bff');
    }
});