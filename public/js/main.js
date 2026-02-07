/// <reference path="./types.d.ts" />

import { 
    openDebugModal, closeDebugModal, loadDebugInfo, 
    initializeDebugMode, updateDebugModeUI, 
    recordApiCall, copyApiHistory, copyApiEntry 
} from './debug.js';

import { 
    compressImage, capturePhotoFromCamera, 
    readFileAsBase64, setPreviewImage, clearPreviewImage,
    setupImageHandlers
} from './images.js';

import { 
    addChatMessage, renderChatHistory, saveChatHistory, loadChatHistory,
    sendStamp, handleChatAI, showAITypingIndicator, hideAITypingIndicator, handleAddFromBubble 
} from './chat.js';

import { 
    openPromptModal, closePromptModal, saveSystemPrompt, 
    resetSystemPrompt, showDiscardConfirmation, loadPromptForTarget 
} from './prompt.js';

import { 
    loadAvailableModels, openModelModal, renderModelList, 
    createModelItem, selectTempModel, saveModelSelection, closeModelModal,
    updateSessionCost
} from './model.js';

// グローバルスコープに関数を公開（HTMLからの呼び出し用）
window.openDebugModal = openDebugModal;
window.closeDebugModal = closeDebugModal;
window.loadDebugInfo = loadDebugInfo;
window.copyApiHistory = copyApiHistory;
window.copyApiEntry = copyApiEntry;
window.recordApiCall = recordApiCall; // chat.jsなどで使用

window.capturePhotoFromCamera = capturePhotoFromCamera;
window.setPreviewImage = setPreviewImage; // camera.jsから使用されるが、closeボタンからも呼ばれる可能性
window.clearPreviewImage = clearPreviewImage;

window.sendStamp = sendStamp;
window.showAITypingIndicator = showAITypingIndicator;
window.hideAITypingIndicator = hideAITypingIndicator;
window.addChatMessage = addChatMessage; // 複数箇所で使用
window.handleAddFromBubble = handleAddFromBubble; // chat.jsから呼ばれる

window.openPromptModal = openPromptModal;
window.closePromptModal = closePromptModal;
window.saveSystemPrompt = saveSystemPrompt;
window.resetSystemPrompt = resetSystemPrompt;
window.showDiscardConfirmation = showDiscardConfirmation;

window.loadAvailableModels = loadAvailableModels;
window.openModelModal = openModelModal;
window.renderModelList = renderModelList; // リサイズ時などに呼ばれる可能性
window.selectTempModel = selectTempModel;
window.saveModelSelection = saveModelSelection;
window.closeModelModal = closeModelModal;
window.copyModelList = () => import('./debug.js').then(m => m.copyModelList()); // 動的インポートまたはdebug.jsでexport

// --- Global State ---

const App = {
    // Cache configuration
    cache: {
        KEYS: {
            TARGETS: 'memo_ai_targets',
            PAGE_CONTENT_PREFIX: 'memo_ai_content_',
            CHAT_HISTORY: 'memo_ai_chat_history',
            PROMPT_PREFIX: 'memo_ai_prompt_'
        },
        TTL: {
            TARGETS: 5 * 60 * 1000, // 5 minutes (DB list caches slightly longer)
            PAGE_CONTENT: 10 * 60 * 1000 // 10 minutes
        },
        lastTargetRefresh: 0 // Timestamp of last target list refresh
    },
    
    // Application State
    target: {
        id: null,
        type: null, // 'database' | 'page'
        schema: null,
        systemPrompt: null // Custom prompt for this target
    },
    
    chat: {
        history: [], // For UI display
        session: [], // For API context (user/assistant only)
        isComposing: false // For IME handling
    },
    
    image: {
        base64: null,
        mimeType: null
    },
    
    model: {
        allModels: [],      // All models from API
        available: [],      // Recommended models
        textOnly: [],       // Text-only models
        vision: [],         // Vision-capable models
        defaultText: null,
        defaultMultimodal: null,
        current: null,      // Currently selected model ID
        tempSelected: null, // Temporary selection in modal
        showAllModels: false, // UI toggle state
        sessionCost: 0      // Session running cost
    },
    
    debug: {
        enabled: true,      // Frontend debug logging
        serverMode: false,  // Server DEBUG_MODE status
        showModelInfo: true, // Show model info in chat bubbles
        apiHistory: [],      // 直近10件のAPI通信履歴
        lastBackendLogs: null,  // サーバーから取得したバックエンドログ
        lastModelList: null  // For debugging model list
    },
    
    defaultPrompt: `あなたは優秀な秘書です。
ユーザーの入力を元に、Notionに保存するための整理されたドキュメントを作成してください。
以下のルールに従ってください：
1. ユーザーの意図を汲み取り、適切なタイトルと本文を構成する
2. 重要な情報は箇条書きなどを活用して見やすくする
3. タスクが含まれる場合は、ToDoリスト形式にする
4. 丁寧な日本語で出力する`
};

// グローバルに公開（モジュール間共有のため）
window.App = App;

// Initial Setup
// ... (DOMContentLoadedなど、後ほど追加)

// --- Utility Functions ---

function debugLog(...args) {
    if (App.debug.enabled) {
        console.log('[DEBUG]', ...args);
    }
}

// グローバル公開
window.debugLog = debugLog;

function updateStatusArea() {
    const loading = document.getElementById('loadingIndicator');
    const saveStatus = document.getElementById('saveStatus');
    const area = document.querySelector('.status-area');
    
    if (!area) return;

    // Check if loading is visible OR saveStatus has text
    const isLoading = loading && !loading.classList.contains('hidden');
    const hasStatus = saveStatus && saveStatus.textContent.trim() !== '';
    
    if (isLoading || hasStatus) {
        /** @type {HTMLElement} */(area).style.display = 'flex';
    } else {
        /** @type {HTMLElement} */(area).style.display = 'none';
    }
}

function showToast(msg) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 3000);
}
window.showToast = showToast;

function setLoading(isLoading, text = '保存中...') {
    const indicator = document.getElementById('loadingIndicator');
    const label = document.getElementById('loadingText');
    if (isLoading) {
        if (label) label.textContent = text;
        if (indicator) indicator.classList.remove('hidden');
    } else {
        if (indicator) indicator.classList.add('hidden');
    }
    updateStatusArea();
}
window.setLoading = setLoading;

function updateSaveStatus(msg) {
    const status = document.getElementById('saveStatus');
    status.textContent = msg;
    updateStatusArea();
    setTimeout(() => {
        status.textContent = '';
        updateStatusArea();
    }, 3000);
}

// デバッグ用ステート表示（開発用）
function showState() {
    console.log('Current State:', App);
    alert(JSON.stringify(App, null, 2));
}
window.showState = showState;

function updateState(icon, message, details = null) {
    const stateDisplay = document.getElementById('stateDisplay');
    const stateIcon = document.getElementById('stateIcon');
    const stateText = document.getElementById('stateText');
    const stateDetailsContent = document.getElementById('stateDetailsContent');
    
    // UI要素がない場合はログ出力のみ
    if (!stateDisplay || !stateIcon || !stateText) {
        console.log(`[State] ${icon} ${message}`, details);
        return;
    }
    
    stateIcon.textContent = icon;
    stateText.textContent = message;
    stateDisplay.classList.remove('hidden');
    
    // Update details content if provided
    if (stateDetailsContent && details) {
        stateDetailsContent.textContent = JSON.stringify(details, null, 2);
    }
    
    console.log(`[State] ${icon} ${message}`, details);
    
    // Auto-hide after 3 seconds if this is a completion state (✅ or ❌)
    if (icon === '✅' || icon === '❌') {
        setTimeout(() => {
            if (stateDisplay) {
                stateDisplay.classList.add('hidden');
            }
        }, 3000);
    }
}
window.updateState = updateState;

async function fetchWithCache(url, cacheKey, ttl = 60000) {
    const now = Date.now();
    const cached = localStorage.getItem(cacheKey);
    
    if (cached) {
        const { timestamp, data } = JSON.parse(cached);
        if (now - timestamp < ttl) {
            debugLog(`Cache hit for ${url}`);
            return data;
        }
    }
    
    debugLog(`Fetching ${url}`);
    const res = await fetch(url);
    if (!res.ok) {
        recordApiCall(url, 'GET', null, null, `HTTP ${res.status}`, res.status);
        throw new Error(`Fetch failed: ${res.status}`);
    }
    
    const data = await res.json();
    recordApiCall(url, 'GET', null, data, null, res.status);
    localStorage.setItem(cacheKey, JSON.stringify({
        timestamp: now,
        data: data
    }));
    
    return data;
}
window.fetchWithCache = fetchWithCache;


// --- Notion Logic (Targets, Saving, Forms) ---

let _loadTargetsRunning = false;

async function loadTargets(forceRefresh = false) {
    // Prevent concurrent calls that could cause duplicate entries
    if (_loadTargetsRunning) {
        debugLog('[loadTargets] Already running - skipping');
        return;
    }
    _loadTargetsRunning = true;
    
    try {
        let data;
        
        if (forceRefresh) {
            // 強制更新：キャッシュをバイパスしてAPIから直接取得
            localStorage.removeItem(App.cache.KEYS.TARGETS);
            console.log('[loadTargets] Force refresh - fetching from API');
            const res = await fetch('/api/targets');
            if (!res.ok) {
                recordApiCall('/api/targets', 'GET', null, null, `HTTP ${res.status}`, res.status);
                throw new Error(`Fetch failed: ${res.status}`);
            }
            data = await res.json();
            recordApiCall('/api/targets', 'GET', null, data, null, res.status);
            // 取得したデータをキャッシュに保存
            localStorage.setItem(App.cache.KEYS.TARGETS, JSON.stringify({
                timestamp: Date.now(),
                data: data
            }));
            console.log('[loadTargets] Fetched', data.targets.length, 'targets');
        } else {
            data = await fetchWithCache(
                '/api/targets', 
                App.cache.KEYS.TARGETS,
                App.cache.TTL.TARGETS
            );
        }
        
        renderTargetOptions(data.targets);
        
        // Update last refresh timestamp
        App.cache.lastTargetRefresh = Date.now();

        // Enable header buttons after targets load
        /** @type {HTMLButtonElement | null} */
        const settingsBtn = /** @type {any} */(document.getElementById('settingsBtn'));
        /** @type {HTMLButtonElement | null} */
        const viewContentBtn = /** @type {any} */(document.getElementById('viewContentBtn'));
        if (settingsBtn) settingsBtn.disabled = false;
        if (viewContentBtn) viewContentBtn.disabled = false;
    } catch (err) {
        console.error('Failed to load targets:', err);
        showToast('ターゲット読込失敗');
    } finally {
        _loadTargetsRunning = false;
    }
}
window.loadTargets = loadTargets;

// リスト更新関数（UIから呼び出し用）
function refreshTargetList() {
    loadTargets(true);
}
window.refreshTargetList = refreshTargetList;

function renderTargetOptions(targets) {
    /** @type {HTMLSelectElement | null} */
    const selector = /** @type {any} */(document.getElementById('appSelector'));
    if (!selector) return;
    
    // 現在の選択値を保持
    const currentVal = selector.value;
    
    // Clear existing options
    selector.innerHTML = '';

    // 1. "Create New Page" option first
    const newPageOpt = document.createElement('option');
    newPageOpt.value = 'new_page';
    newPageOpt.textContent = '＋ 新規ページ作成...';
    selector.appendChild(newPageOpt);
    
    // Filter out empty titles
    const validTargets = targets.filter(t => t.title && t.title.trim());

    // Use original order from API (validTargets)
    validTargets.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.id;
        // Append type suffix
        const suffix = t.type === 'database' ? ' [DB]' : ' [Page]';
        opt.textContent = t.title + suffix;
        opt.dataset.type = t.type;
        selector.appendChild(opt);
    });
    
    // Default Selection Logic
    let targetToSelect = null;

    // 1. Try to restore current selection
    if (currentVal && currentVal !== 'new_page' && Array.from(selector.options).some(o => o.value === currentVal)) {
        targetToSelect = currentVal;
    } 
    // 2. Try to restore saved selection
    else {
        const savedTargetId = localStorage.getItem('memo_ai_last_target');
        if (savedTargetId && Array.from(selector.options).some(o => o.value === savedTargetId)) {
            targetToSelect = savedTargetId;
        }
    }

    // 3. Default to the first valid target if no selection exists
    if (!targetToSelect && validTargets.length > 0) {
        targetToSelect = validTargets[0].id; // Select the first real page/DB
    }

    // Apply selection
    if (targetToSelect) {
        selector.value = targetToSelect;
        // Trigger change event to update state (skipRefresh=true to prevent loop)
        handleTargetChange(true);
    } else {
        // Fallback if no targets exist at all (only "Create New Page")
        selector.value = 'new_page'; 
    }
    
    // Auto-open new page modal if no valid targets exist (empty list)
    if (validTargets.length === 0) {
        // Use setTimeout to ensure DOM is fully rendered and modal event listeners are ready
        setTimeout(() => {
            debugLog('[renderTargetOptions] No pages found - opening new page modal');
            openNewPageModal();
        }, 100);
    }
}

async function handleTargetChange(skipRefreshOrEvent = false) {
    
    /** @type {HTMLSelectElement | null} */
    const selector = /** @type {any} */(document.getElementById('appSelector'));
    if (!selector) return;
    const selectedOpt = selector.options[selector.selectedIndex];
    const targetId = selector.value;
    
    // 新規ページ作成の場合
    if (targetId === 'new_page') {
        openNewPageModal();
        // 選択を元に戻す（モーダルで処理するため、かつ未選択状態を防ぐ）
        // 以前の選択があれば戻し、なければ何もしない（or 先頭の実在ページ）
        // ここでは単純に handleTargetChange 内での状態更新をスキップして戻る
        const saved = localStorage.getItem('memo_ai_last_target');
        if (saved && Array.from(selector.options).some(o => o.value === saved)) {
            selector.value = saved;
        } else if (selector.options.length > 1) {
            selector.value = selector.options[1].value; // Create New Pageの次
        }
        return;
    }
    
    if (!targetId) {
        // Should not happen with new logic, but keep for safety
        App.target = { id: null, type: null, schema: null, systemPrompt: null };
        return;
    }
    
    const type = selectedOpt.dataset.type;
    App.target.id = targetId;
    App.target.type = type;
    App.target.systemPrompt = null; // Initialize systemPrompt property
    
    // 選択を保存
    localStorage.setItem('memo_ai_last_target', targetId);
    
    // システムプロンプトの読み込み
    const promptKey = `${App.cache.KEYS.PROMPT_PREFIX}${targetId}`;
    const customPrompt = localStorage.getItem(promptKey);
    App.target.systemPrompt = customPrompt || null;
    
    console.log(`Target set: ${type} ${targetId}`, customPrompt ? '(Has custom prompt)' : '(Default prompt)');
    
    // UI更新 (optional elements may not exist)
    const formContainer = document.getElementById('propertiesForm');
    const propsContainer = document.getElementById('propertiesContainer');
    const propsSection = document.getElementById('propertiesSection');
    
    if (type === 'database') {

        // Show properties container for DB
        if (propsContainer) propsContainer.style.display = 'block';
        if (propsSection) propsSection.classList.add('hidden');
        
        // スキーマ取得
        try {
            console.log('[DEBUG] Fetching schema for:', targetId);
            const res = await fetch(`/api/schema/${targetId}`);
            console.log('[DEBUG] Schema response status:', res.status, res.ok);
            if (res.ok) {
                const data = await res.json();
                recordApiCall(`/api/schema/${targetId}`, 'GET', null, data, null, res.status);
                console.log('[DEBUG] Schema API response:', data);
                console.log('[DEBUG] Schema data:', data.schema);
                App.target.schema = data.schema;
                console.log('[DEBUG] formContainer exists:', !!formContainer);
                if (formContainer) renderDynamicForm(formContainer, data.schema);
            } else {
                recordApiCall(`/api/schema/${targetId}`, 'GET', null, null, `HTTP ${res.status}`, res.status);
                console.error('[DEBUG] Schema fetch failed with status:', res.status);
            }
        } catch (e) {
            console.error('Schema fetch error:', e);
        }
    } else {
        App.target.schema = null;
        
        // Hide properties container for Page
        if (propsContainer) propsContainer.style.display = 'none';
    }
    
    // Note: リスト更新はセレクターの click イベントリスナーで行う（5秒スロットリング付き）
    // handleTargetChange 内では実行しない（二重更新防止）
}
window.handleTargetChange = handleTargetChange;

async function fetchAndTruncatePageContent(pageId, type) {
    // 参照ページが有効かチェック
    // 注: ここでの呼び出し元は sendStamp や handleChatAI
    // 既に機能制限でリファレンス機能を削除した場合はnullを返す
    
    try {
        const cacheKey = `${App.cache.KEYS.PAGE_CONTENT_PREFIX}${pageId}`;
        const data = await fetchWithCache(
            `/api/content/${pageId}?type=${type}`, // Backend endpoint needs to support type param
            cacheKey,
            App.cache.TTL.PAGE_CONTENT
        );
        
        // テキストのみ抽出して短くする（トークン節約）
        let text = "";
        if (data.content) {
            text = JSON.stringify(data.content).substring(0, 8000); // 約4000日本語文字
        }
        return text;
    } catch(e) {
        console.error("Failed to fetch page content", e);
        return null; // エラー時はコンテキストなしで続行
    }
}
window.fetchAndTruncatePageContent = fetchAndTruncatePageContent;

// --- Form & Input Logic ---

function renderDynamicForm(container, schema) {
    console.log('[DEBUG] renderDynamicForm called');
    console.log('[DEBUG] container:', container);
    console.log('[DEBUG] schema:', schema);
    
    if (!container) {
        console.error('[DEBUG] No container element found!');
        return;
    }
    container.innerHTML = '';
    
    // **重要**: 逆順で表示 (Reverse Order)
    const entries = Object.entries(schema).reverse();
    console.log('[DEBUG] Schema entries count:', entries.length);
    
    for (const [key, prop] of entries) {
        // Notionが自動管理するシステムプロパティは編集不要なのでスキップ
        if (['created_time', 'last_edited_time', 'created_by', 'last_edited_by'].includes(prop.type)) {
            continue;
        }

        // タイトルプロパティはメイン入力欄を使うのでスキップ
        if (prop.type === 'title') continue;
        
        const wrapper = document.createElement('div');
        wrapper.className = 'prop-field';
        
        const label = document.createElement('label');
        label.className = 'prop-label';
        label.textContent = key;
        wrapper.appendChild(label);
        
        let input;
        
        if (prop.type === 'select' || prop.type === 'multi_select' || prop.type === 'status') {
            input = document.createElement('select');
            input.className = 'prop-input';
            input.dataset.key = key;
            input.dataset.type = prop.type;
            
            // Note: multi_selectでもinput.multiple = trueを設定しない
            // Notionでは複数選択可能だが、UIでは単一選択として扱う
            // （優先度、工数レベルなどと同じ動作）
            
            // 空のオプション (デフォルト)
            const def = document.createElement('option');
            def.value = "";
            def.textContent = "(未選択)";
            input.appendChild(def);
            
            // Notionスキーマに定義されている固定オプションを追加
            // status タイプは prop.status.options、select/multi_select は prop[prop.type].options
            const options = prop.type === 'status' 
                ? (prop.status?.options || [])
                : (prop[prop.type]?.options || []);
            
            options.forEach(o => {
                const opt = document.createElement('option');
                opt.value = o.name;
                opt.textContent = o.name;
                input.appendChild(opt);
            });
            
        } else if (prop.type === 'date') {
            input = document.createElement('input');
            input.type = 'date';
            input.className = 'prop-input';
            input.dataset.key = key;
            input.dataset.type = prop.type;
        } else if (prop.type === 'checkbox') {
            input = document.createElement('input');
            input.type = 'checkbox';
            input.className = 'prop-input';
            input.dataset.key = key;
            input.dataset.type = prop.type;
        } else if (prop.type === 'people' || prop.type === 'relation' || prop.type === 'files') {
            // 現在未対応のプロパティタイプ
            input = document.createElement('input');
            input.type = 'text';
            input.className = 'prop-input';
            input.disabled = true;
            input.placeholder = '(このアプリからは編集できません)';
            input.dataset.key = key;
            input.dataset.type = prop.type;
        } else if (prop.type === 'formula' || prop.type === 'rollup') {
            // 自動計算/参照プロパティ
            input = document.createElement('input');
            input.type = 'text';
            input.className = 'prop-input';
            input.disabled = true;
            input.placeholder = '(自動計算/参照)';
            input.dataset.key = key;
            input.dataset.type = prop.type;
        } else {
            // その他のテキスト系プロパティ (text, title, rich_text, number, url, email, phone_number 等)
            input = document.createElement('input');
            input.type = 'text';
            input.className = 'prop-input';
            input.dataset.key = key;
            input.dataset.type = prop.type;
        }
        
        wrapper.appendChild(input);
        container.appendChild(wrapper);
    }
}

async function saveToDatabase() {
    /** @type {HTMLTextAreaElement | null} */
    const memoInput = /** @type {any} */(document.getElementById('memoInput'));
    if (!memoInput) return;
    const content = memoInput.value;
    
    if (!content && !App.image.base64) {
        showToast('メモまたは画像を入力してください');
        return;
    }
    
    setLoading(true);
    
    // プロパティ収集
    const properties = {};
    const inputs = document.querySelectorAll('#propertiesForm .prop-input');
    
    inputs.forEach(/** @param {HTMLElement} input */ input => {
        const key = input.dataset?.key;
        const type = input.dataset?.type;
        
        if (type === 'select' || type === 'status') {
            if (/** @type {HTMLSelectElement} */(input).value) {
                const propType = type === 'status' ? 'status' : 'select';
                properties[key] = { [propType]: { name: /** @type {HTMLSelectElement} */(input).value } };
            }
        } else if (type === 'multi_select') {
            // UIでは単一選択として扱うが、Notionには配列として送る
            if (/** @type {HTMLSelectElement} */(input).value) {
                properties[key] = { multi_select: [{ name: /** @type {HTMLSelectElement} */(input).value }] };
            }
        } else if (type === 'checkbox') {
            properties[key] = { checkbox: /** @type {HTMLInputElement} */(input).checked };
        } else if (type === 'date') {
            if (/** @type {HTMLInputElement} */(input).value) properties[key] = { date: { start: /** @type {HTMLInputElement} */(input).value } };
        } else if (/** @type {HTMLInputElement} */(input).value) {
            // text, url, email, etc.
            const val = /** @type {HTMLInputElement} */(input).value;
            if (type === 'url') properties[key] = { url: val };
            else if (type === 'email') properties[key] = { email: val };
            else if (type === 'number') properties[key] = { number: Number(val) };
            else properties[key] = { rich_text: [{ text: { content: val } }] };
        }
    });

    const body = {
        target_db_id: App.target.id,
        target_type: 'database',
        text: content,
        properties: properties
    };
    
    try {
        const res = await fetch('/api/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        
        if (!res.ok) throw new Error(await res.text());
        
        const data = await res.json();
        recordApiCall('/api/save', 'POST', body, data, null, res.status);
        
        updateSaveStatus(' 保存しました！');
        showToast('保存しました');
        
        // クリア
        memoInput.value = '';
        clearPreviewImage();
        
        // フォームリセット
        inputs.forEach(/** @param {HTMLElement} input */ input => {
             if (/** @type {HTMLInputElement} */(input).type === 'checkbox') /** @type {HTMLInputElement} */(input).checked = false;
             else if (input.tagName === 'SELECT') /** @type {HTMLSelectElement} */(input).selectedIndex = -1;
             else /** @type {HTMLInputElement} */(input).value = '';
        });
        
    } catch (e) {
        console.error('Save error', e);
        updateSaveStatus(' 保存失敗');
        showToast(`エラー: ${e.message}`);
        recordApiCall('/api/save', 'POST', body, null, e.message, null);
    } finally {
        setLoading(false);
    }
}

async function saveToPage() {
    /** @type {HTMLTextAreaElement | null} */
    const memoInput = /** @type {any} */(document.getElementById('memoInput'));
    if (!memoInput) return;
    const content = memoInput.value;
    
    if (!content && !App.image.base64) {
        showToast('メモまたは画像を入力してください');
        return;
    }
    
    setLoading(true);
    
    const body = {
        target_db_id: App.target.id,
        target_type: 'page',
        text: content,
        properties: {} // Required by backend
    };
    
    try {
        // Pageへの追記は別のエンドポイントまたは同じエンドポイントで分岐
        // ここでは便宜上 /api/save を拡張して利用すると想定、または /api/append
        // 現在の実装に合わせて /api/save を使用（バックエンドが対応している前提）
        // バックエンド側で page_id がある場合は追記モードになる
        
        const res = await fetch('/api/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        
        if (!res.ok) throw new Error(await res.text());
        
        const data = await res.json();
        recordApiCall('/api/save', 'POST', body, data, null, res.status);
        
        updateSaveStatus('✅ 追記しました！');
        showToast('ページに追記しました');
        
        memoInput.value = '';
        clearPreviewImage();
        
    } catch (e) {
        console.error('Append error', e);
        updateSaveStatus(' 追記失敗');
        showToast(`エラー: ${e.message}`);
        recordApiCall('/api/save', 'POST', body, null, e.message, null);
    } finally {
        setLoading(false);
    }
}

async function handleDirectSave() {
    if (!App.target.id) {
        showToast('ターゲットを選択してください');
        return;
    }
    
    if (App.target.type === 'database') {
        await saveToDatabase();
    } else {
        await saveToPage();
    }
}
window.handleDirectSave = handleDirectSave;
window.saveToDatabase = saveToDatabase;  // Export for chat.js bubble add
window.saveToPage = saveToPage;          // Export for chat.js bubble add

// --- Content Viewer (Jump to Notion) ---

function openContentModal() {
    if (!App.target.id) {
        showToast('ターゲットを選択してください');
        return;
    }
    
    // 内蔵ビューワーではなく、ブラウザでNotionページを直接開く
    const notionUrl = `https://www.notion.so/${App.target.id.replace(/-/g, '')}`;
    window.open(notionUrl, '_blank');
    
    showToast('Notionページを開きました');
}
window.openContentModal = openContentModal;

// --- New Page Creation ---


function openNewPageModal() {
    // Show the custom new page modal
    const modal = document.getElementById('newPageModal');
    const input = /** @type {HTMLInputElement} */(document.getElementById('newPageNameInput'));
    const createBtn = document.getElementById('createNewPageBtn');
    const cancelBtn = document.getElementById('cancelNewPageBtn');
    const closeBtn = document.getElementById('closeNewPageModalBtn');
    
    if (!modal || !input || !createBtn || !cancelBtn || !closeBtn) return;
    
    // Clear previous input
    input.value = '';
    
    // Show modal
    modal.classList.remove('hidden');
    input.focus();
    
    // Handle keyboard events
    const onKeydown = (/** @type {KeyboardEvent} */ e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleCreate();
        } else if (e.key === 'Escape') {
            handleCancel();
        }
    };
    
    // Handle create button
    const handleCreate = () => {
        const title = input.value.trim();
        if (title) {
            // Clean up listener BEFORE closing modal
            input.removeEventListener('keydown', onKeydown);
            modal.classList.add('hidden');
            createNewPage(title);
        } else {
            showToast('ページ名を入力してください');
        }
    };
    
    // Handle cancel
    const handleCancel = () => {
        // Clean up listener BEFORE closing modal
        input.removeEventListener('keydown', onKeydown);
        modal.classList.add('hidden');
        // Reset app selector to previous value
        const appSelector = /** @type {HTMLSelectElement} */(document.getElementById('appSelector'));
        if (appSelector) appSelector.value = App.target.id || '';
    };
    
    // Add event listeners with {once: true} to auto-cleanup
    createBtn.addEventListener('click', handleCreate, {once: true});
    cancelBtn.addEventListener('click', handleCancel, {once: true});
    closeBtn.addEventListener('click', handleCancel, {once: true});
    input.addEventListener('keydown', onKeydown);
}
window.openNewPageModal = openNewPageModal;

async function createNewPage(title) {
    setLoading(true, "ページ作成中...");
    try {
        const reqBody = { page_name: title };
        const res = await fetch('/api/pages/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(reqBody)
        });
        
        if (!res.ok) {
            const errText = await res.text();
            recordApiCall('/api/pages/create', 'POST', reqBody, null, errText, res.status);
            throw new Error(errText);
        }
        
        const data = await res.json();
        recordApiCall('/api/pages/create', 'POST', reqBody, data, null, res.status);
        showToast(`ページ「${title}」を作成しました`);
        
        // ターゲットリスト再読み込み（強制更新で最新のリストを取得）
        await loadTargets(true);
        
        // 作成したページを選択（skipRefresh=true でリスト再取得を防止）
        /** @type {HTMLSelectElement | null} */
        const selector = /** @type {any} */(document.getElementById('appSelector'));
        if (selector) {
            selector.value = data.id;
            handleTargetChange(true);
        }
        
    } catch(e) {
        showToast(`作成失敗: ${e.message}`);
    } finally {
        setLoading(false);
    }
}
window.createNewPage = createNewPage;

// --- Super Reload ---
function handleSuperReload() {
    if (confirm('【注意】\n保存されたターゲットリスト、チャット履歴、キャッシュなどを全て削除してリロードします。\n未保存のデータは失われます。\nよろしいですか？')) {
        // ローカルストレージを全クリア
        localStorage.clear();
        
        // キャッシュをクリアしてリロード (reload(true) is deprecated)
        window.location.reload();
    }
}
window.handleSuperReload = handleSuperReload;


// --- Initialization ---

document.addEventListener('DOMContentLoaded', async () => {
    // Media handling (delegated to images module)
    setupImageHandlers();

    // Emoji/Stamp
    const emojiBtn = document.getElementById('emojiBtn');
    const emojiPalette = document.getElementById('emojiPalette');
    
    if (emojiBtn && emojiPalette) {
        emojiBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            emojiPalette.classList.toggle('hidden');
        });
        
        // Close on outside click
        document.addEventListener('click', (e) => {
            if (e.target instanceof Node && !emojiBtn.contains(e.target) && !emojiPalette.contains(e.target)) {
                emojiPalette.classList.add('hidden');
            }
        });
        
        // Stamp selection
        document.querySelectorAll('.emoji-btn').forEach(item => {
            item.addEventListener('click', () => {
                const emoji = item.textContent;
                sendStamp(emoji);
                emojiPalette.classList.add('hidden');
            });
        });
    }
    
    // Memo Input
    const memoInput = document.getElementById('memoInput');
    
    if (memoInput) {
        // Auto-resize
        memoInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });
        
        // IME handling
        memoInput.addEventListener('compositionstart', () => { App.chat.isComposing = true; });
        memoInput.addEventListener('compositionend', () => { App.chat.isComposing = false; });
        
        // Enter to send (Shift+Enter for newline)
        memoInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !App.chat.isComposing) {
                e.preventDefault();
                // ターゲットが設定されていて、かつチャットモードなら送信
                // ここでは便宜上、Ctrl+Enterまたは明示的なボタンでNotion保存
                // EnterのみはチャットAI送信とする（仕様確認要だが既存踏襲）
                
                const text = /** @type {HTMLTextAreaElement} */(memoInput).value.trim();
                if (text || App.image.base64) {
                    handleChatAI(text);
                }
            }
        });
    }
    
    // Settings & Menu
    const settingsBtn = document.getElementById('settingsBtn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', toggleSettingsMenu);
    }
    
    // Close settings on outside click
    document.addEventListener('click', (e) => {
        const menu = document.getElementById('settingsMenu');
        if (e.target instanceof Node && settingsBtn && menu && !settingsBtn.contains(e.target) && !menu.contains(e.target)) {
            menu.classList.add('hidden');
        }
    });

    // Initial Loads
    loadTargets();      // Load Notion targets
    loadChatHistory();  // Load chat history
    
    // AI Info Display Toggle
    /** @type {HTMLInputElement | null} */
    const showInfoToggle = /** @type {any} */(document.getElementById('showModelInfoToggle'));
    if (showInfoToggle) {
        // Restore state
        const savedShowInfo = localStorage.getItem(App.cache.KEYS.SHOW_MODEL_INFO);
        if (savedShowInfo !== null) {
            App.debug.showModelInfo = savedShowInfo === 'true';
        }
        showInfoToggle.checked = App.debug.showModelInfo;
        
        // Add listener
        showInfoToggle.addEventListener('change', (e) => {
            App.debug.showModelInfo = /** @type {HTMLInputElement} */(e.target).checked;
            localStorage.setItem(App.cache.KEYS.SHOW_MODEL_INFO, String(App.debug.showModelInfo));
            renderChatHistory(); // Re-render to show/hide info immediately
        });
    }
    
    // Initialize Debug Mode (async)
    initializeDebugMode(); 
    
    // Initialize Models
    loadAvailableModels();
    
    // Session Clear Button
    const sessionClearBtn = document.getElementById('sessionClearBtn');
    if (sessionClearBtn) {
        sessionClearBtn.addEventListener('click', handleSessionClear);
    }
    
    // View Content Button
    const viewContentBtn = document.getElementById('viewContentBtn');
    if (viewContentBtn) {
        viewContentBtn.addEventListener('click', openContentModal);
    }
});

// UI Event Handlers defined in HTML (onclick) need to be globablly accessible
// Already exposed via window.* assignments at top of file


function toggleSettingsMenu() {
    const menu = document.getElementById('settingsMenu');
    if (menu) menu.classList.toggle('hidden');
}
window.toggleSettingsMenu = toggleSettingsMenu;
// --- Form Fill Function (for AI extracted properties) ---
function fillForm(properties) {
    if (!properties) return;
    
    // Original implementation looked for inputs directly
    const inputs = document.querySelectorAll('#propertiesForm .prop-input');
    
    inputs.forEach(/** @param {HTMLElement} input */ input => {
        const key = input.dataset?.key;
        const type = input.dataset?.type;
        const value = properties[key];

        if (!value) return;
        if (type === 'select' && value?.select?.name) {
            /** @type {HTMLSelectElement} */(input).value = value.select.name;
        } else if (type === 'multi_select' && value?.multi_select) {
            const names = value.multi_select.map(item => item.name);
            Array.from(/** @type {HTMLSelectElement} */(input).options).forEach(opt => {
                opt.selected = names.includes(opt.value);
            });
        } else if (type === 'checkbox' && value?.checkbox !== undefined) {
            /** @type {HTMLInputElement} */(input).checked = value.checkbox;
        } else if (type === 'date' && value?.date?.start) {
            /** @type {HTMLInputElement} */(input).value = value.date.start;
        } else if (value?.rich_text?.[0]?.text?.content) {
            /** @type {HTMLInputElement} */(input).value = value.rich_text[0].text.content;
        } else if (typeof value === 'string') {
            /** @type {HTMLInputElement} */(input).value = value;
        }
    });
}

window.fillForm = fillForm;

// --- Session Clear ---
function handleSessionClear() {
    App.chat.session = [];
    App.chat.history = [];
    renderChatHistory();
    localStorage.removeItem(App.cache.KEYS.CHAT_HISTORY);
    showToast("セッションをクリアしました");
}
window.handleSessionClear = handleSessionClear;


// --- Event Listeners Setup ---
document.addEventListener('DOMContentLoaded', () => {
    const settingsMenu = document.getElementById('settingsMenu');
    
    // Edit Prompt
    const editPromptItem = document.getElementById('editPromptMenuItem');
    if (editPromptItem) {
        editPromptItem.addEventListener('click', () => {
            if (settingsMenu) settingsMenu.classList.add('hidden');
            openPromptModal();
        });
    }
    
    // Model Select
    const modelSelectItem = document.getElementById('modelSelectMenuItem');
    if (modelSelectItem) {
        modelSelectItem.addEventListener('click', () => {
            if (settingsMenu) settingsMenu.classList.add('hidden');
            openModelModal();
        });
    }
    
    // Debug Info
    const debugInfoItem = document.getElementById('debugInfoMenuItem');
    if (debugInfoItem) {
        debugInfoItem.addEventListener('click', () => {
            if (settingsMenu) settingsMenu.classList.add('hidden');
            openDebugModal();
        });
    }
    
    // Super Reload
    const superReloadItem = document.getElementById('superReloadMenuItem');
    if (superReloadItem) {
        superReloadItem.addEventListener('click', () => {
            if (settingsMenu) settingsMenu.classList.add('hidden');
            handleSuperReload();
        });
    }
    
    // Session Clear (if exists)
    const sessionClearBtn = document.getElementById('sessionClearBtn');
    if (sessionClearBtn) {
        sessionClearBtn.addEventListener('click', handleSessionClear);
    }
    
    // View Content Button
    const viewContentBtn = document.getElementById('viewContentBtn');
    if (viewContentBtn) {
        viewContentBtn.addEventListener('click', openContentModal);
    }
    
    // Model modal buttons
    const closeModelBtn = document.getElementById('closeModelModalBtn');
    const cancelModelBtn = document.getElementById('cancelModelBtn');
    const saveModelBtn = document.getElementById('saveModelBtn');
    if (closeModelBtn) closeModelBtn.addEventListener('click', closeModelModal);
    if (cancelModelBtn) cancelModelBtn.addEventListener('click', closeModelModal);
    if (saveModelBtn) saveModelBtn.addEventListener('click', saveModelSelection);
    
    // Debug modal buttons
    const closeDebugModalBtn = document.getElementById('closeDebugModalBtn');
    const closeDebugBtn = document.getElementById('closeDebugBtn');
    const refreshDebugBtn = document.getElementById('refreshDebugBtn');
    if (closeDebugModalBtn) closeDebugModalBtn.addEventListener('click', closeDebugModal);
    if (closeDebugBtn) closeDebugBtn.addEventListener('click', closeDebugModal);
    if (refreshDebugBtn) refreshDebugBtn.addEventListener('click', loadDebugInfo);
    
    // Prompt modal buttons
    // Prompt modal buttons
    const closePromptModalBtn = document.getElementById('closeModalBtn');
    const cancelPromptBtn = document.getElementById('cancelPromptBtn');
    const savePromptBtn = document.getElementById('savePromptBtn');
    const resetPromptBtn = document.getElementById('resetPromptBtn');
    if (closePromptModalBtn) closePromptModalBtn.addEventListener('click', closePromptModal);
    if (cancelPromptBtn) cancelPromptBtn.addEventListener('click', closePromptModal);
    if (savePromptBtn) savePromptBtn.addEventListener('click', saveSystemPrompt);
    if (resetPromptBtn) resetPromptBtn.addEventListener('click', resetSystemPrompt);
    
    // Properties toggle
    const togglePropsBtn = document.getElementById('togglePropsBtn');
    if (togglePropsBtn) {
        togglePropsBtn.addEventListener('click', () => {
            const section = document.getElementById('propertiesSection');
            if (section) {
                section.classList.toggle('hidden');
                togglePropsBtn.textContent = section.classList.contains('hidden') 
                    ? ' 属性を表示' 
                    : ' 属性を隠す';
            }
        });
    }
    
    // Target selector change handler
    /** @type {HTMLSelectElement | null} */
    const appSelector = /** @type {any} */(document.getElementById('appSelector'));
    if (appSelector) {
        // Wrap handleTargetChange to match event listener signature
        appSelector.addEventListener('change', () => handleTargetChange(false));
        
        // Refresh list when selector is clicked/opened (to detect deleted pages)
        // Throttle: Don't refresh if last refresh was within 5 seconds
        appSelector.addEventListener('click', () => {
            const now = Date.now();
            const timeSinceLastRefresh = now - App.cache.lastTargetRefresh;
            const THROTTLE_MS = 5000; // 5 seconds
            
            if (timeSinceLastRefresh < THROTTLE_MS) {
                debugLog(`[appSelector] Clicked but skipping refresh (last refresh was ${Math.round(timeSinceLastRefresh / 1000)}s ago)`);
                return;
            }
            
            debugLog('[appSelector] Clicked - refreshing target list');
            loadTargets(true);
        });
    }
    
    // State display toggle button
    const stateToggle = document.getElementById('stateToggle');
    const stateDetails = document.getElementById('stateDetails');
    if (stateToggle && stateDetails) {
        stateToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            stateDetails.classList.toggle('hidden');
            stateToggle.textContent = stateDetails.classList.contains('hidden') ? '▼' : '▲';
        });
    }
});
