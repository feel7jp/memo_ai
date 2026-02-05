// ========== DEBUG MODULE ==========
// デバッグモーダルとAPI記録機能

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
        
        const data = await res.json();
        renderDebugInfo(data);
    } catch (err) {
        content.innerHTML = `
            <div class="debug-error">
                <h3>❌ デバッグ情報の取得に失敗</h3>
                <p>${err.message}</p>
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
    
    // 最新API通信
    html += '<div class="debug-section">';
    html += '<h3>📡 最新API通信 <button class="btn-copy-debug" onclick="window.copyLastApiCall()">📋 コピー</button></h3>';
    if (window.App.debug.lastApiCall) {
        html += `<pre class="debug-code">${JSON.stringify(window.App.debug.lastApiCall, null, 2).replace(/</g, '&lt;')}</pre>`;
    } else {
        html += '<p class="debug-hint">まだAPI通信がありません。</p>';
    }
    html += '</div>';
    
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
        html += '<details style="margin-top: 8px;">';
        html += '<summary style="cursor: pointer; padding: 8px; background: var(--bg-secondary); border-radius: 4px;">全モデル生データを表示...</summary>';
        html += `<pre class="debug-code" style="max-height: 400px; overflow: auto; margin-top: 8px;">${JSON.stringify(data.models.raw_list, null, 2).replace(/</g, '&lt;')}</pre>`;
        html += '</details>';
        html += '</div>';
    }
    
    content.innerHTML = html;
}

/**
 * モデルリストの生データをコピー
 */
export function copyModelList() {
    if (!window.App.debug.lastModelList) { 
        if (window.showToast) window.showToast('コピーするデータがありません'); 
        return; 
    }
    navigator.clipboard.writeText(JSON.stringify(window.App.debug.lastModelList, null, 2))
        .then(() => window.showToast && window.showToast('モデルデータをコピーしました'))
        .catch(() => window.showToast && window.showToast('コピー失敗'));
}

/**
 * API通信を記録（シンプル版）
 */
export function recordApiCall(endpoint, method, request, response, error = null, status = null) {
    window.App.debug.lastApiCall = {
        timestamp: new Date().toISOString(),
        endpoint, method, status, error,
        request: JSON.parse(JSON.stringify(request, (k, v) => 
            (k === 'image_data' && typeof v === 'string') ? `[Image: ${v.length} chars]` : v
        )),
        response: JSON.parse(JSON.stringify(response, (k, v) => 
            (k === 'image_data' && typeof v === 'string') ? `[Image: ${v.length} chars]` : v
        ))
    };
}

/**
 * 最新API通信をコピー
 */
export function copyLastApiCall() {
    if (!window.App.debug.lastApiCall) { 
        if (window.showToast) window.showToast('コピーする履歴がありません'); 
        return; 
    }
    navigator.clipboard.writeText(`=== Memo AI Debug ===\n${JSON.stringify(window.App.debug.lastApiCall, null, 2)}`)
        .then(() => window.showToast && window.showToast('コピーしました'))
        .catch(() => window.showToast && window.showToast('コピー失敗'));
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
        
        const data = await res.json();
        window.App.debug.serverMode = data.debug_mode || false;
        
        // デフォルトシステムプロンプトを更新
        if (data.default_system_prompt) {
            window.App.defaultPrompt = data.default_system_prompt;
            if (window.App.debug.enabled) console.log('[CONFIG] App.defaultPrompt loaded from backend');
        }
        
        if (window.App.debug.enabled) console.log('[DEBUG_MODE] Server debug_mode:', window.App.debug.serverMode);
        
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
        if (window.App.debug.serverMode) {
            debugInfoItem.style.display = '';
        } else {
            debugInfoItem.style.display = 'none';
        }
    }
    
    if (window.App.debug.enabled) console.log('[DEBUG_MODE] UI updated. Model selection:', window.App.debug.serverMode ? 'enabled' : 'disabled');
}
