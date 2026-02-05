
import { 
    openDebugModal, closeDebugModal, loadDebugInfo, 
    initializeDebugMode, updateDebugModeUI, 
    recordApiCall, copyLastApiCall 
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
window.copyLastApiCall = copyLastApiCall;
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
        }
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
        lastApiCall: null,   // Last API call details
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
        area.style.display = 'flex';
    } else {
        area.style.display = 'none';
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
    const stateMessage = document.getElementById('stateMessage');
    
    // UI要素がない場合はログ出力のみ
    if (!stateDisplay || !stateIcon || !stateMessage) {
        console.log(`[State] ${icon} ${message}`, details);
        return;
    }
    
    stateIcon.textContent = icon;
    stateMessage.textContent = message;
    stateDisplay.classList.remove('hidden');
    
    console.log(`[State] ${icon} ${message}`, details);
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
    if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);
    
    const data = await res.json();
    localStorage.setItem(cacheKey, JSON.stringify({
        timestamp: now,
        data: data
    }));
    
    return data;
}
window.fetchWithCache = fetchWithCache;


// --- Notion Logic (Targets, Saving, Forms) ---

async function loadTargets() {
    try {
        const data = await fetchWithCache(
            '/api/targets', 
            App.cache.KEYS.TARGETS,
            App.cache.TTL.TARGETS
        );
        renderTargetOptions(data.targets);

        // Enable header buttons after targets load
        const settingsBtn = document.getElementById('settingsBtn');
        const viewContentBtn = document.getElementById('viewContentBtn');
        if (settingsBtn) settingsBtn.disabled = false;
        if (viewContentBtn) viewContentBtn.disabled = false;
    } catch (err) {
        console.error('Failed to load targets:', err);
        showToast('ターゲット読込失敗');
    }
}
window.loadTargets = loadTargets;

function renderTargetOptions(targets) {
    const selector = document.getElementById('appSelector');
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
        // Trigger change event to update state
        handleTargetChange();
    } else {
        // Fallback if no targets exist at all (only "Create New Page")
        selector.value = 'new_page'; 
    }
}

async function handleTargetChange() {
    const selector = document.getElementById('appSelector');
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
        App.target = { id: null, type: null, schema: null };
        const imgTrigger = document.getElementById('imgUploadTrigger');
        const addControls = document.getElementById('additionalControls');
        if (imgTrigger) imgTrigger.classList.add('hidden');
        if (addControls) addControls.classList.add('hidden');
        return;
    }
    
    const type = selectedOpt.dataset.type;
    App.target.id = targetId;
    App.target.type = type;
    
    // 選択を保存
    localStorage.setItem('memo_ai_last_target', targetId);
    
    // システムプロンプトの読み込み
    const promptKey = `${App.cache.KEYS.PROMPT_PREFIX}${targetId}`;
    const customPrompt = localStorage.getItem(promptKey);
    App.target.systemPrompt = customPrompt || null;
    
    console.log(`Target set: ${type} ${targetId}`, customPrompt ? '(Has custom prompt)' : '(Default prompt)');
    
    // UI更新 (optional elements may not exist)
    const directSaveBtn = document.getElementById('directSaveBtn');
    const formContainer = document.getElementById('propertiesForm');
    const propsContainer = document.getElementById('propertiesContainer');
    const propsSection = document.getElementById('propertiesSection');
    
    if (type === 'database') {
        if (directSaveBtn) {
            directSaveBtn.innerHTML = '<span>保存 (DB)</span>';
            directSaveBtn.title = 'データベースに保存';
        }

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
                console.log('[DEBUG] Schema API response:', data);
                console.log('[DEBUG] Schema data:', data.schema);
                App.target.schema = data.schema;
                console.log('[DEBUG] formContainer exists:', !!formContainer);
                if (formContainer) renderDynamicForm(formContainer, data.schema);
            } else {
                console.error('[DEBUG] Schema fetch failed with status:', res.status);
            }
        } catch (e) {
            console.error('Schema fetch error:', e);
        }
    } else {
        if (directSaveBtn) {
            directSaveBtn.innerHTML = '<span>追記 (Page)</span>';
            directSaveBtn.title = 'ページ末尾に追記';
        }
        
        App.target.schema = null;
        
        // Hide properties container for Page
        if (propsContainer) propsContainer.style.display = 'none';
    }
    
    // コントロール表示 (optional elements)
    const imgTrigger = document.getElementById('imgUploadTrigger');
    const addControls = document.getElementById('additionalControls');
    const refContainer = document.getElementById('referencePageContainer');
    if (imgTrigger) imgTrigger.classList.remove('hidden');
    if (addControls) addControls.classList.remove('hidden');
    if (refContainer) refContainer.style.display = 'block';
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
        
        if (prop.type === 'select' || prop.type === 'multi_select') {
            input = document.createElement('select');
            input.className = 'prop-input';
            input.dataset.key = key;
            input.dataset.type = prop.type;
            
            if (prop.type === 'multi_select') {
                input.multiple = true;
            }
            
            // 空のオプション (デフォルト)
            const def = document.createElement('option');
            def.value = "";
            def.textContent = "(未選択)";
            input.appendChild(def);
            
            // Notionスキーマに定義されている固定オプションを追加
            (prop[prop.type].options || []).forEach(o => {
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
        } else {
            // その他のテキスト系プロパティ (text, title, rich_text, number, url 等)
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
    const memoInput = document.getElementById('memoInput');
    const content = memoInput.value;
    
    if (!content && !App.image.base64) {
        showToast('メモまたは画像を入力してください');
        return;
    }
    
    setLoading(true);
    
    // プロパティ収集
    const properties = {};
    const inputs = document.querySelectorAll('#propertiesForm .prop-input');
    
    inputs.forEach(input => {
        const key = input.dataset.key;
        const type = input.dataset.type;
        
        if (type === 'select') {
            if (input.value) properties[key] = { select: { name: input.value } };
        } else if (type === 'multi_select') {
            const selected = Array.from(input.selectedOptions).map(o => ({ name: o.value }));
            if (selected.length) properties[key] = { multi_select: selected };
        } else if (type === 'checkbox') {
            properties[key] = { checkbox: input.checked };
        } else if (type === 'date') {
            if (input.value) properties[key] = { date: { start: input.value } };
        } else if (input.value) {
            // text, url, email, etc.
            if (type === 'url') properties[key] = { url: input.value };
            else if (type === 'email') properties[key] = { email: input.value };
            else if (type === 'number') properties[key] = { number: Number(input.value) };
            else properties[key] = { rich_text: [{ text: { content: input.value } }] };
        }
    });

    const body = {
        database_id: App.target.id,
        content: content,
        properties: properties,
        image_data: App.image.base64 ? {
            base64: App.image.base64,
            mime_type: App.image.mimeType
        } : null
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
        inputs.forEach(input => {
             if (input.type === 'checkbox') input.checked = false;
             else if (input.tagName === 'SELECT') input.selectedIndex = -1;
             else input.value = '';
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
    const memoInput = document.getElementById('memoInput');
    const content = memoInput.value;
    
    if (!content && !App.image.base64) {
        showToast('メモまたは画像を入力してください');
        return;
    }
    
    setLoading(true);
    
    const body = {
        page_id: App.target.id,
        content: content,
        image_data: App.image.base64 ? {
            base64: App.image.base64,
            mime_type: App.image.mimeType
        } : null
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

// --- New Page Creation ---

function openNewPageModal() {
    // 新規作成モーダル（未実装ならプレースホルダー）
    const appSelector = document.getElementById('appSelector');
    
    const title = prompt("新しいページのタイトルを入力してください:");
    if (title) {
        createNewPage(title);
    } else {
        // キャンセル時は選択を戻す
        appSelector.value = App.target.id || '';
    }
}
window.openNewPageModal = openNewPageModal;

async function createNewPage(title) {
    setLoading(true, "ページ作成中...");
    try {
        const res = await fetch('/api/pages/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: title })
        });
        
        if (!res.ok) throw new Error(await res.text());
        
        const data = await res.json();
        showToast(`ページ「${title}」を作成しました`);
        
        // ターゲットリスト再読み込み
        localStorage.removeItem(App.cache.KEYS.TARGETS);
        await loadTargets();
        
        // 作成したページを選択
        const selector = document.getElementById('appSelector');
        selector.value = data.id;
        handleTargetChange();
        
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
        
        // キャッシュバスター付きでリロード
        window.location.reload(true);
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
            if (!emojiBtn.contains(e.target) && !emojiPalette.contains(e.target)) {
                emojiPalette.classList.add('hidden');
            }
        });
        
        // Stamp selection
        document.querySelectorAll('.emoji-item').forEach(item => {
            item.addEventListener('click', () => {
                const emoji = item.textContent;
                sendStamp(emoji);
                emojiPalette.classList.add('hidden');
            });
        });
    }
    
    // Memo Input
    const memoInput = document.getElementById('memoInput');
    const sendBtn = document.getElementById('sendBtn'); // チャット送信ボタンがあれば
    
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
                
                const text = memoInput.value.trim();
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
        if (settingsBtn && menu && !settingsBtn.contains(e.target) && !menu.contains(e.target)) {
            menu.classList.add('hidden');
        }
    });

    // Initial Loads
    loadTargets();      // Load Notion targets
    loadChatHistory();  // Load chat history
    
    // AI Info Display Toggle
    const showInfoToggle = document.getElementById('showModelInfoToggle');
    if (showInfoToggle) {
        // Restore state
        const savedShowInfo = localStorage.getItem(App.cache.KEYS.SHOW_MODEL_INFO);
        if (savedShowInfo !== null) {
            App.debug.showModelInfo = savedShowInfo === 'true';
        }
        showInfoToggle.checked = App.debug.showModelInfo;
        
        // Add listener
        showInfoToggle.addEventListener('change', (e) => {
            App.debug.showModelInfo = e.target.checked;
            localStorage.setItem(App.cache.KEYS.SHOW_MODEL_INFO, App.debug.showModelInfo);
            renderChatHistory(); // Re-render to show/hide info immediately
        });
    }
    
    // Initialize Debug Mode (async)
    initializeDebugMode(); 
    
    // Initialize Models
    loadAvailableModels();
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
    
    inputs.forEach(input => {
        const key = input.dataset.key;
        const type = input.dataset.type;
        const value = properties[key];

        if (!value) return;
        if (type === 'select' && value?.select?.name) {
            input.value = value.select.name;
        } else if (type === 'multi_select' && value?.multi_select) {
            const names = value.multi_select.map(item => item.name);
            Array.from(input.options).forEach(opt => {
                opt.selected = names.includes(opt.value);
            });
        } else if (type === 'checkbox' && value?.checkbox !== undefined) {
            input.checked = value.checkbox;
        } else if (type === 'date' && value?.date?.start) {
            input.value = value.date.start;
        } else if (value?.rich_text?.[0]?.text?.content) {
            input.value = value.rich_text[0].text.content;
        } else if (typeof value === 'string') {
            input.value = value;
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
        viewContentBtn.addEventListener('click', async () => {
            if (!App.target.id) {
                showToast('ターゲットを選択してください');
                return;
            }
            showToast('ページ内容を読み込み中...');
            try {
                const res = await fetch(`/api/content/${App.target.id}?type=${App.target.type}`);
                if (!res.ok) throw new Error('取得失敗');
                const data = await res.json();
                const content = JSON.stringify(data.content || data, null, 2).substring(0, 2000);
                alert('ページ内容 (一部):\n\n' + content);
            } catch (err) {
                showToast('内容取得エラー: ' + err.message);
            }
        });
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
    const appSelector = document.getElementById('appSelector');
    if (appSelector) {
        appSelector.addEventListener('change', handleTargetChange);
    }
});
