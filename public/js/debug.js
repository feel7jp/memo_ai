// ========== DEBUG MODULE ==========
// デバッグモーダルとAPI記録機能

/**
 * バックエンドログ（Notion + LLM）を統合してタイムスタンプ降順にソート
 * @param {Object} backendLogs - { notion: [...], llm: [...] }
 * @returns {Array} 統合・ソート済みログ配列
 */
function _mergeAndSortLogs(backendLogs) {
    const notionLogs = (backendLogs.notion || []).map(e => ({...e, _type: 'notion'}));
    const llmLogs = (backendLogs.llm || []).map(e => ({...e, _type: 'llm'}));
    return [...notionLogs, ...llmLogs].sort((a, b) =>
        (b.timestamp || '').localeCompare(a.timestamp || '')
    );
}

/**
 * デバッグログヘルパー
 */
export function debugLog(...args) {
    if (window.App && window.App.debug && window.App.debug.enabled) {
        console.log('[DEBUG]', ...args);
    }
}

/**
 * デバッグモーダルを開く
 */
export function openDebugModal() {
    const modal = document.getElementById('debugModal');
    modal.classList.remove('hidden');
    loadDebugInfo();
}

/**
 * デバッグモーダルを閉じる
 */
export function closeDebugModal() {
    const modal = document.getElementById('debugModal');
    modal.classList.add('hidden');
}

/**
 * デバッグ情報を読み込んで表示
 */
export async function loadDebugInfo() {
    const content = document.getElementById('debugInfoContent');
    if (!content) return;

    content.innerHTML = '<div class="loading-indicator"><div class="spinner"></div><span>読み込み中...</span></div>';

    try {
        const res = await fetch('/api/debug5075378');
        if (!res.ok) {
            throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }

        /** @type {ConfigApiResponse} */
        const data = await res.json();
        renderDebugInfo(data);
    } catch (err) {
        const errorMessage = /** @type {Error} */(err).message;
        content.innerHTML = `
            <div class="debug-error">
                <h3>❌ デバッグ情報の取得に失敗</h3>
                <p>${errorMessage}</p>
                <p class="debug-hint">
                    💡 ヒント: サーバーが起動しているか確認してください
                </p>
            </div>
        `;
    }
}


/**
 * デバッグ情報をHTMLとしてレンダリング（シンプル版）
 */
function renderDebugInfo(data) {
    const content = document.getElementById('debugInfoContent');
    if (!content) return;

    let html = `<div class="debug-timestamp">取得時刻: ${data.timestamp || 'N/A'}</div>`;

    // CORS設定
    if (data.cors) {
        html += '<div class="debug-section">';
        html += '<h3>🔐 CORS設定</h3><div class="debug-grid">';
        html += `<div class="debug-item"><span class="debug-label">許可オリジン:</span><code class="debug-value">${data.cors.allowed_origins.join(', ')}</code></div>`;
        html += `<div class="debug-item"><span class="debug-label">制限モード:</span><span class="debug-value">${data.cors.is_restricted ? '✅ はい' : '❌ いいえ (全許可)'}</span></div>`;
        if (data.cors.detected_platform) {
            html += `<div class="debug-item"><span class="debug-label">検出プラットフォーム:</span><span class="debug-value">${data.cors.detected_platform}</span></div>`;
        }
        html += '</div></div>';
    }

    // --- API通信履歴（Notion + LLM をタイムスタンプ順に統合） ---
    if (data.backend_logs) {
        window.App.debug.lastBackendLogs = data.backend_logs;

        // Notion と LLM のログを統合し、タイムスタンプ降順でソート
        const allLogs = _mergeAndSortLogs(data.backend_logs);

        // ログデータを保存（コピー機能用）
        window.App.debug.lastAllLogs = allLogs;

        html += '<div class="debug-section">';
        html += '<h3>📡 API通信 <button id="btnCopyAllApiHistory" class="btn-copy-debug">📋 全履歴コピー</button></h3>';

        if (allLogs.length === 0) {
            html += '<p class="debug-hint">まだAPI通信がありません。</p>';
        } else {
            allLogs.forEach((entry, i) => {
                const isNotion = entry._type === 'notion';
                const typeIcon = isNotion ? '🔗' : '🤖';
                const typeLabel = isNotion ? 'Notion' : 'LLM';

                // エラーメッセージの抽出と表示準備
                let errorSummary = '';
                if (entry.error) {
                    // エラーメッセージから重要な部分を抽出
                    let errorMsg = entry.error;

                    // HTTPステータスコードとメッセージを抽出
                    const httpMatch = errorMsg.match(/HTTP (\d+):/);
                    if (httpMatch) {
                        errorSummary = ` <span style="color:#ff4d4f; font-size:0.85em;">(${httpMatch[1]})</span>`;
                    }

                    // "404 Not Found" や "400 Bad Request" などを抽出
                    const statusMatch = errorMsg.match(/(\d{3})\s+([\w\s]+)'/);
                    if (statusMatch) {
                        errorSummary = ` <span style="color:#ff4d4f; font-size:0.85em;">(${statusMatch[1]} ${statusMatch[2]})</span>`;
                    }
                }

                const statusBadge = entry.error
                    ? `<span style="color:#ff4d4f">❌${errorSummary}</span>`
                    : `<span style="color:#52c41a">✅${isNotion ? ' ' + entry.status : ''}</span>`;

                // LLMの場合、モデル選択の透明性情報を取得
                let modelInfo = '';
                let fallbackWarning = '';
                if (!isNotion && entry.response && entry.response.model_selection) {
                    const ms = entry.response.model_selection;
                    if (ms.fallback_occurred) {
                        fallbackWarning = `<span style="color:#ff9800; font-weight:bold; margin-left:4px;">⚠️ フォールバック</span>`;
                        modelInfo = `<div style="font-size:0.85em; color:#888; margin-top:2px;">リクエスト: <code style="color:#ff9800;">${ms.requested}</code> → 使用: <code style="color:#52c41a;">${ms.used}</code></div>`;
                    } else if (ms.requested === 'auto') {
                        modelInfo = `<div style="font-size:0.85em; color:#888; margin-top:2px;">自動選択: <code>${ms.used}</code></div>`;
                    }
                }

                const label = isNotion
                    ? `${entry.method} ${entry.endpoint}`
                    : entry.model;

                // Notionのページタイトルがあれば表示に追加（クライアント側で抽出）
                let titleInfo = '';
                if (isNotion && entry.response) {
                    let targetItem = null;
                    let count = 0;

                    // リスト形式の場合
                    if (entry.response.results && Array.isArray(entry.response.results)) {
                        if (entry.response.results.length > 0) {
                            targetItem = entry.response.results[0];
                            count = entry.response.results.length;
                        }
                    }
                    // 単一ページ形式の場合
                    else if (entry.response.object === 'page' || entry.response.properties) {
                        targetItem = entry.response;
                    }

                    if (targetItem && targetItem.properties) {
                        // titleプロパティを探す
                        for (const prop of Object.values(targetItem.properties)) {
                            if (prop.type === 'title' && prop.title && prop.title.length > 0) {
                                const titleText = prop.title.map(t => t.plain_text).join('');
                                if (titleText) {
                                    titleInfo = ` <span style="color:#aaa; font-size:0.9em;">(${titleText}${count > 1 ? ` +${count-1}...` : ''})</span>`;
                                }
                                break;
                            }
                        }
                    }
                }

                const extra = [];
                if (entry.duration_ms != null) extra.push(`${entry.duration_ms}ms`);
                if (entry.cost) extra.push(`$${parseFloat(entry.cost).toFixed(5)}`);
                const time = entry.timestamp?.split('T')[1]?.split('.')[0] || '';

                const entryJson = JSON.stringify(entry, null, 2).replace(/</g, '&lt;');
                html += `<details ${i === 0 ? 'open' : ''} style="margin-bottom:4px;">`;
                html += `<summary style="cursor:pointer; padding:6px 8px; background:var(--bg-secondary); border-radius:4px; font-size:0.85em; display:flex; justify-content:space-between; align-items:center;">`;
                html += `<span>${typeIcon} <strong>${typeLabel}</strong> ${statusBadge} <code>${label}</code>${fallbackWarning}${titleInfo}`;
                if (extra.length) html += ` ${extra.join(' ')}`;
                html += ` <span style="color:#888; font-size:0.85em;">${time}</span></span>`;
                html += `<button class="btn-copy-debug" style="margin-left:auto; font-size:0.75em; padding:2px 6px;" data-entry-index="${i}" onclick="event.stopPropagation();">📋</button>`;
                html += `</summary>`;
                if (modelInfo) html += modelInfo;
                html += `<pre class="debug-code" style="margin:4px 0; font-size:0.8em; white-space:pre-wrap; word-break:break-all;">${entryJson}</pre>`;
                html += `</details>`;
            });
        }
        html += '</div>';
    }

    // 環境情報
    html += '<div class="debug-section"><h3>⚙️ 環境情報</h3><div class="debug-grid">';
    for (const [key, value] of Object.entries(data.environment || {})) {
        html += `<div class="debug-item"><span class="debug-label">${key}:</span><span class="debug-value">${value}</span></div>`;
    }
    html += '</div></div>';

    // 環境変数
    if (data.env_vars) {
        html += '<div class="debug-section"><h3>🔐 環境変数</h3><div class="debug-grid">';
        for (const [key, value] of Object.entries(data.env_vars)) {
            html += `<div class="debug-item"><span class="debug-label">${key}:</span><code class="debug-value">${value || 'null'}</code></div>`;
        }
        html += '</div></div>';
    }

    // モデル情報
    if (data.models) {
        // デバッグ用に保存（コピー機能用）
        window.App.debug.lastModelList = data.models.raw_list;

        html += '<div class="debug-section">';
        html += `<h3>📋 モデル一覧 (${data.models.recommended_count} 推奨 / ${data.models.total_count} 全モデル) <button class="btn-copy-debug" onclick="window.copyModelList()">📋 コピー</button></h3>`;
        html += '<details style="margin-bottom:4px;">';
        html += '<summary style="cursor:pointer; padding:6px 8px; background:var(--bg-secondary); border-radius:4px; font-size:0.85em;">全モデル生データを表示...</summary>';
        html += `<pre class="debug-code" style="margin:4px 0; font-size:0.8em; white-space:pre-wrap; word-break:break-all;">${JSON.stringify(data.models.raw_list, null, 2).replace(/</g, '&lt;')}</pre>`;
        html += '</details>';
        html += '</div>';
    }

    content.innerHTML = html;

    // イベント委譲: コピーボタンのクリックを処理
    content.querySelectorAll('.btn-copy-debug[data-entry-index]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const index = parseInt(btn.getAttribute('data-entry-index'), 10);
            copyApiEntry(index);
        });
    });

    // 全履歴コピーボタンのイベントリスナー
    const btnCopyAll = document.getElementById('btnCopyAllApiHistory');
    if (btnCopyAll) {
        btnCopyAll.addEventListener('click', (e) => {
            e.stopPropagation();
            copyApiHistory();
        });
    }
}

/**
 * クリップボードにテキストをコピー (Fallback付き)
 */
async function copyToClipboard(text) {
    if (!text) return false;

    try {
        // 1. Try modern Clipboard API
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
            return true;
        }
        throw new Error('Clipboard API unavailable');
    } catch (err) {
        // 2. Fallback to execCommand
        try {
            const textArea = document.createElement("textarea");
            textArea.value = text;

            // Avoid scrolling to bottom
            textArea.style.top = "0";
            textArea.style.left = "0";
            textArea.style.position = "fixed";
            textArea.style.opacity = "0";

            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();

            const successful = document.execCommand('copy');
            document.body.removeChild(textArea);

            if (successful) return true;
            throw new Error('execCommand failed');
        } catch (fallbackErr) {
            console.error('Copy failed (both methods):', err, fallbackErr);
            return false;
        }
    }
}

/**
 * モデルリストの生データをコピー
 */
export async function copyModelList() {
    if (!window.App.debug.lastModelList) {
        if (window.showToast) window.showToast('コピーするデータがありません');
        return;
    }

    const success = await copyToClipboard(JSON.stringify(window.App.debug.lastModelList, null, 2));

    if (success) {
        if (window.showToast) window.showToast('モデルデータをコピーしました');
    } else {
        if (window.showToast) window.showToast('コピー失敗: セキュアコンテキスト(HTTPS/localhost)が必要です');
    }
}

/**
 * API通信を記録する（履歴は最大10件）
 */
const MAX_API_HISTORY = 10;

// レスポンス/リクエストの重いデータを省略するシリアライザ
function sanitizeForLog(obj) {
    if (!obj) return obj;
    return JSON.parse(JSON.stringify(obj, (key, value) => {
        // 画像データの省略
        if ((key === 'image_data' || key === 'base64') && typeof value === 'string' && value.length > 200) {
            return `[Image: ${value.length} chars]`;
        }
        // children配列の省略
        if (key === 'children' && Array.isArray(value)) {
            return `[${value.length} blocks]`;
        }
        // 長い文字列の截断
        if (typeof value === 'string' && value.length > 2000) {
            return value.substring(0, 2000) + '... [truncated]';
        }
        return value;
    }));
}

export function recordApiCall(endpoint, method, request, response, error = null, status = null) {
    const entry = {
        timestamp: new Date().toISOString(),
        endpoint, method, status, error,
        request: request ? sanitizeForLog(request) : null,
        response: response ? sanitizeForLog(response) : null,
    };
    window.App.debug.apiHistory.push(entry);
    // リングバッファ: 古いものを削除
    while (window.App.debug.apiHistory.length > MAX_API_HISTORY) {
        window.App.debug.apiHistory.shift();
    }
}

/**
 * API通信履歴をクリップボードにコピー
 */
export async function copyApiHistory() {
    // ログを統合してソート（表示順に合わせる）
    const backendLogs = window.App.debug.lastBackendLogs || {};
    const allLogs = _mergeAndSortLogs(backendLogs);

    const debugData = {
        memo_ai_debug: {
            timestamp: new Date().toISOString(),
            logs: allLogs
        }
    };

    const success = await copyToClipboard(JSON.stringify(debugData, null, 2));
    if (success) {
        if (window.showToast) window.showToast('コピーしました');
    } else {
        if (window.showToast) window.showToast('コピー失敗');
    }
}

/**
 * 個別のAPI通信エントリをコピー
 */
export async function copyApiEntry(index) {
    if (!window.App.debug.lastAllLogs || !window.App.debug.lastAllLogs[index]) {
        if (window.showToast) window.showToast('コピーするデータがありません');
        return;
    }

    const entry = window.App.debug.lastAllLogs[index];
    const jsonString = JSON.stringify(entry, null, 2);

    const success = await copyToClipboard(jsonString);
    if (success) {
        if (window.showToast) window.showToast('コピーしました');
    } else {
        if (window.showToast) window.showToast('コピー失敗');
    }
}

/**
 * DEBUG_MODE状態を取得してUI制御を初期化
 */
export async function initializeDebugMode() {
    try {
        const res = await fetch('/api/config');
        if (!res.ok) {
            console.warn('[DEBUG_MODE] Failed to fetch config, assuming debug_mode=false');
            return;
        }

        /** @type {ConfigApiResponse} */
        const data = await res.json();
        window.App.debug.serverMode = data.debug_mode || false;

        // デフォルトシステムプロンプトを更新
        if (data.default_system_prompt) {
            window.App.defaultPrompt = data.default_system_prompt;
            debugLog('[CONFIG] App.defaultPrompt loaded from backend');
        }

        debugLog('[DEBUG_MODE] Server debug_mode:', window.App.debug.serverMode);

        // UI要素の表示制御
        updateDebugModeUI();

    } catch (err) {
        console.error('[DEBUG_MODE] Error fetching config:', err);
        window.App.debug.serverMode = false;
        updateDebugModeUI();
    }
}

/**
 * DEBUG_MODE状態に応じてUI要素の表示を制御
 */
export function updateDebugModeUI() {
    // モデル選択メニューの表示制御
    const modelSelectMenuItem = document.getElementById('modelSelectMenuItem');
    if (modelSelectMenuItem) {
        if (window.App.debug.serverMode) {
            // DEBUG_MODE有効: モデル選択を表示
            modelSelectMenuItem.style.display = '';
        } else {
            // DEBUG_MODE無効: モデル選択を非表示
            modelSelectMenuItem.style.display = 'none';
            // 現在のモデル選択をクリア（自動選択に戻す）
            window.App.model.current = null;
            localStorage.removeItem('memo_ai_selected_model');
        }
    }

    // デバッグメニューの表示制御
    const debugInfoItem = document.getElementById('debugInfoMenuItem');
    if (debugInfoItem) {
        debugInfoItem.style.display = window.App.debug.serverMode ? '' : 'none';
    }

    debugLog('[DEBUG_MODE] UI updated. Model selection:', window.App.debug.serverMode ? 'enabled' : 'disabled');
}
