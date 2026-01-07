
// キャッシュ設定
const CACHE_TTL = 180000; // 3分
const TARGETS_CACHE_KEY = 'memo_ai_targets';
const SCHEMA_CACHE_PREFIX = 'memo_ai_schema_';
const DRAFT_KEY = 'memo_ai_draft';
const LAST_TARGET_KEY = 'memo_ai_last_target';
const CHAT_HISTORY_KEY = 'memo_ai_chat_history';
const LOCAL_PROMPT_PREFIX = 'memo_ai_prompt_';
const SHOW_MODEL_INFO_KEY = 'memo_ai_show_model_info';

const DEFAULT_SYSTEM_PROMPT = `優秀な秘書として、ユーザーのタスクを明確にする手伝いをすること。
明確な実行できる タスク名に言い換えて。先頭に的確な絵文字を追加して
画像の場合は、そこから何をしようとしているのか推定して、タスクにして。`;

// グローバル状態
let chatHistory = [];  // チャット履歴: [{type, message, properties, timestamp}]
let chatSession = []; // {role: 'user'|'model'|'assistant', content: string}
let currentTargetId = null;
let currentTargetName = '';
let currentTargetType = 'database';
let currentSchema = null;
let currentPreviewData = null;  // プレビューデータ（タグサジェスト用）
let currentSystemPrompt = null; // サーバーからロードしたプロンプト
let isComposing = false; // IME変換中フラグ
// Image Input State
let currentImageBase64 = null;
let currentImageMimeType = null;

// Model & Cost State
let availableModels = [];
let textOnlyModels = [];
let visionModels = [];
let defaultTextModel = null;
let defaultMultimodalModel = null;
let currentModel = null;
let tempSelectedModel = null;
let sessionCost = 0.0;
let showModelInfo = true;

document.addEventListener('DOMContentLoaded', () => {
    // DOM要素の取得
    const appSelector = document.getElementById('appSelector');
    const memoInput = document.getElementById('memoInput');
    const sessionClearBtn = document.getElementById('sessionClearBtn');
    const viewContentBtn = document.getElementById('viewContentBtn');
    const settingsBtn = document.getElementById('settingsBtn');
    const settingsMenu = document.getElementById('settingsMenu');
    
    // --- Image Input Elements ---
    const addMediaBtn = document.getElementById('addMediaBtn');
    const mediaMenu = document.getElementById('mediaMenu');
    const cameraBtn = document.getElementById('cameraBtn');
    const galleryBtn = document.getElementById('galleryBtn');
    const cameraInput = document.getElementById('cameraInput');
    const imageInput = document.getElementById('imageInput');
    const removeImageBtn = document.getElementById('removeImageBtn');
    
    // Media Menu Toggle
    if (addMediaBtn) {
        addMediaBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            mediaMenu.classList.toggle('hidden');
        });
        
        // Close menu when clicking outside
        document.addEventListener('click', (e) => {
            if (mediaMenu && !mediaMenu.contains(e.target) && e.target !== addMediaBtn) {
                mediaMenu.classList.add('hidden');
            }
        });

        // Camera/Gallery Trigger
        if (cameraBtn) cameraBtn.addEventListener('click', () => {
            cameraInput.click();
            mediaMenu.classList.add('hidden');
        });
        
        if (galleryBtn) galleryBtn.addEventListener('click', () => {
            imageInput.click();
            mediaMenu.classList.add('hidden');
        });

        // File Input Handlers
        const handleFileSelect = async (e) => {
            const file = e.target.files[0];
            if (!file) {
                console.log('[Image Upload] No file selected');
                return;
            }
            
            console.log('[Image Upload] File selected:', file.name, file.size, 'bytes', file.type);
            
            try {
                updateState('📷', '画像を圧縮中...', { step: 'compressing' });
                showToast("画像を処理中...");
                
                // Compress image before setting preview
                const { base64, mimeType } = await compressImage(file);
                console.log('[Image Upload] Image compressed, new size:', base64.length, 'chars');
                
                setPreviewImage(base64, mimeType);
                updateState('✅', '画像準備完了', { step: 'ready' });
                showToast("画像を読み込みました");
                setTimeout(() => {
                    const stateDisplay = document.getElementById('stateDisplay');
                    if (stateDisplay) stateDisplay.classList.add('hidden');
                }, 2000);
                
                // Reset input so same file can be selected again
                e.target.value = ''; 
            } catch (err) {
                console.error('[Image Upload] Error:', err);
                showToast("画像の読み込みに失敗しました: " + err.message);
            }
        };
        
        if (cameraInput) cameraInput.addEventListener('change', handleFileSelect);
        if (imageInput) imageInput.addEventListener('change', handleFileSelect);
        
        // Remove Image
        if (removeImageBtn) removeImageBtn.addEventListener('click', () => {
            console.log('[Image Upload] Removing image preview');
            clearPreviewImage();
        });
    }
    
    // 1. 下書き読み込み
    const savedDraft = localStorage.getItem(DRAFT_KEY);
    if (savedDraft) {
        memoInput.value = savedDraft;
        memoInput.dispatchEvent(new Event('input'));
    }
    
    // 2. テキストエリアの自動リサイズ
    memoInput.addEventListener('input', () => {
        memoInput.style.height = 'auto';
        memoInput.style.height = Math.min(memoInput.scrollHeight, 120) + 'px';
        
        // 下書き保存
        localStorage.setItem(DRAFT_KEY, memoInput.value);
        updateSaveStatus("下書き保存中...");
    });
    
    // 3. IME対応
    memoInput.addEventListener('compositionstart', () => {
        isComposing = true;
    });
    
    memoInput.addEventListener('compositionend', () => {
        isComposing = false;
    });
    
    // 4. Enterキーハンドラ
    memoInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
            e.preventDefault();
            handleChatAI();
        }
    });
    
    // 5. チャット履歴読み込み
    loadChatHistory();
    
    // 6. ターゲット読み込み
    loadTargets(appSelector);
    
    // 7. Load Models
    loadAvailableModels();
    
    // 7.5 Load Settings
    const savedShowInfo = localStorage.getItem(SHOW_MODEL_INFO_KEY);
    if (savedShowInfo !== null) {
        showModelInfo = savedShowInfo === 'true';
    }
    const showInfoToggle = document.getElementById('showModelInfoToggle');
    if (showInfoToggle) {
        showInfoToggle.checked = showModelInfo;
        showInfoToggle.addEventListener('change', (e) => {
            showModelInfo = e.target.checked;
            localStorage.setItem(SHOW_MODEL_INFO_KEY, showModelInfo);
            renderChatHistory(); // Re-render to show/hide info
        });
    }
    
    // 8. Settings Menu Logic
    if (settingsBtn) {
        settingsBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleSettingsMenu();
        });
    }
    
    document.addEventListener('click', (e) => {
        if (settingsMenu && !settingsMenu.classList.contains('hidden') && !settingsMenu.contains(e.target) && e.target !== settingsBtn) {
            settingsMenu.classList.add('hidden');
        }
    });

    const editPromptItem = document.getElementById('editPromptMenuItem');
    if (editPromptItem) {
        editPromptItem.addEventListener('click', () => {
            settingsMenu.classList.add('hidden');
            openPromptModal();
        });
    }
    
    const modelSelectItem = document.getElementById('modelSelectMenuItem');
    if (modelSelectItem) {
        modelSelectItem.addEventListener('click', () => {
            settingsMenu.classList.add('hidden');
            openModelModal();
        });
    }
    
    // Model Modal Close
    const closeModelBtn = document.getElementById('closeModelModalBtn');
    const cancelModelBtn = document.getElementById('cancelModelBtn');
    const saveModelBtn = document.getElementById('saveModelBtn');
    if (closeModelBtn) closeModelBtn.addEventListener('click', closeModelModal);
    if (cancelModelBtn) cancelModelBtn.addEventListener('click', closeModelModal);
    if (saveModelBtn) saveModelBtn.addEventListener('click', saveModelSelection);
    
    // 9. イベントリスナー登録 (Existing)
    appSelector.addEventListener('change', (e) => {
        const value = e.target.value;
        if (value === '__NEW_PAGE__') {
            openNewPageModal();
            // 前の選択に戻す
            const lastSelected = localStorage.getItem(LAST_TARGET_KEY);
            if (lastSelected) {
                e.target.value = lastSelected;
            }
        } else {
            handleTargetChange(value);
        }
    });
    if (sessionClearBtn) sessionClearBtn.addEventListener('click', handleSessionClear);
    if (viewContentBtn) viewContentBtn.addEventListener('click', openContentModal);
    
    // Send Button
    const sendBtn = document.getElementById('sendBtn');
    if (sendBtn) sendBtn.addEventListener('click', () => {
        console.log('[Send Button] Clicked');
        handleChatAI();
    });
    
    // 10. プロパティセクション折りたたみ
    const togglePropsBtn = document.getElementById('togglePropsBtn');
    if (togglePropsBtn) {
        togglePropsBtn.addEventListener('click', () => {
            const section = document.getElementById('propertiesSection');
            section.classList.toggle('hidden');
            togglePropsBtn.textContent = section.classList.contains('hidden') 
                ? '▼ 属性を表示' 
                : '▲ 属性を隠す';
        });
    }
});

// --- Image Utility ---

/**
 * Compress image using Canvas API
 * Reduces file size significantly while maintaining quality for AI analysis
 */
function compressImage(file, maxDimension = 600, quality = 0.7) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        
        reader.onload = (e) => {
            const img = new Image();
            
            img.onload = () => {
                // Calculate new dimensions
                let width = img.width;
                let height = img.height;
                
                if (width > maxDimension || height > maxDimension) {
                    if (width > height) {
                        height = Math.round((height * maxDimension) / width);
                        width = maxDimension;
                    } else {
                        width = Math.round((width * maxDimension) / height);
                        height = maxDimension;
                    }
                }
                
                console.log(`[Image Compress] Original: ${img.width}x${img.height}, Compressed: ${width}x${height}`);
                
                // Create canvas and compress
                const canvas = document.createElement('canvas');
                canvas.width = width;
                canvas.height = height;
                
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);
                
                // Convert to JPEG base64
                const dataUrl = canvas.toDataURL('image/jpeg', quality);
                const matches = dataUrl.match(/^data:(.+);base64,(.+)$/);
                
                if (matches && matches.length === 3) {
                    resolve({
                        mimeType: matches[1],
                        base64: matches[2],
                        dataUrl: dataUrl
                    });
                } else {
                    reject(new Error('Failed to compress image'));
                }
            };
            
            img.onerror = () => reject(new Error('Failed to load image'));
            img.src = e.target.result;
        };
        
        reader.onerror = () => reject(new Error('Failed to read file'));
        reader.readAsDataURL(file);
    });
}

function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = reader.result; // data:image/jpeg;base64,...
            // Extract core base64 and mime type
            const matches = result.match(/^data:(.+);base64,(.+)$/);
            if (matches && matches.length === 3) {
                resolve({
                    mimeType: matches[1],
                    base64: matches[2],
                    dataUrl: result
                });
            } else {
                reject(new Error("Invalid format"));
            }
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

function setPreviewImage(base64, mimeType) {
    console.log('[Preview] Setting preview image, mime:', mimeType, 'size:', base64.length, 'chars');
    currentImageBase64 = base64;
    currentImageMimeType = mimeType;
    
    const previewArea = document.getElementById('imagePreviewArea');
    const previewImg = document.getElementById('previewImg');
    
    previewImg.src = `data:${mimeType};base64,${base64}`;
    previewArea.classList.remove('hidden');
    console.log('[Preview] Preview area shown');
}

function clearPreviewImage() {
    console.log('[Preview] Clearing preview image');
    currentImageBase64 = null;
    currentImageMimeType = null;
    
    const previewArea = document.getElementById('imagePreviewArea');
    const previewImg = document.getElementById('previewImg');
    
    previewImg.src = '';
    previewArea.classList.add('hidden');
}

// --- チャット履歴管理 ---

function addChatMessage(type, message, properties = null, modelInfo = null) {
    const entry = {
        type: type,  // 'user' | 'ai' | 'system'
        message: message,
        properties: properties,
        timestamp: Date.now(),
        modelInfo: modelInfo
    };
    
    chatHistory.push(entry);
    renderChatHistory();
    saveChatHistory();
}

function renderChatHistory() {
    const container = document.getElementById('chatHistory');
    container.innerHTML = '';
    
    chatHistory.forEach((entry, index) => {
        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${entry.type}`;
        
        // メッセージ内容
        bubble.innerHTML = entry.message.replace(/\n/g, '<br>');
        
        // ユーザーまたはAIメッセージにホバーボタンを追加
        if (entry.type === 'user' || entry.type === 'ai') {
            const addBtn = document.createElement('button');
            addBtn.className = 'bubble-add-btn';
            addBtn.textContent = 'Notionに追加';
            addBtn.onclick = (e) => {
                e.stopPropagation();
                handleAddFromBubble(entry);
            };
            bubble.appendChild(addBtn);
        }
        
        // AIのモデル情報表示
        if (entry.type === 'ai' && showModelInfo && entry.modelInfo) {
            const infoDiv = document.createElement('div');
            infoDiv.className = 'model-info-text';
            const { model, usage, cost } = entry.modelInfo;
            
            // Try to find model info to get provider prefix
            const modelInfo = availableModels.find(m => m.id === model);
            const modelDisplay = modelInfo 
                ? `[${modelInfo.provider}] ${modelInfo.name}`
                : model;
            
            let infoText = `Model: ${modelDisplay}`;
            if (cost) infoText += ` | Cost: $${parseFloat(cost).toFixed(5)}`;
            // usage is object {prompt_tokens, completion_tokens, total_tokens}
            if (usage && usage.total_tokens) infoText += ` | Tokens: ${usage.total_tokens}`;
            
            infoDiv.textContent = infoText;
            bubble.appendChild(infoDiv);
        }
        
        container.appendChild(bubble);
    });
    
    // 最下部にスクロール
    container.scrollTop = container.scrollHeight;
}

function saveChatHistory() {
    // 最新50件のみ保存
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatHistory.slice(-50)));
}

function loadChatHistory() {
    const saved = localStorage.getItem(CHAT_HISTORY_KEY);
    if (saved) {
        try {
            chatHistory = JSON.parse(saved);
            renderChatHistory();
            
            // Rebuild chatSession for API context
            chatSession = chatHistory
                .filter(entry => ['user', 'ai'].includes(entry.type))
                .map(entry => ({
                    role: entry.type === 'user' ? 'user' : 'assistant',
                    content: entry.message.replace(/<br>/g, '\n') // Restore newlines for context
                }));
            
            // If the last message was from user and we are reloading, 
            // we might want to ensure we don't double-send or anything, 
            // but for now just restoring context is enough.
            
        } catch(e) {
            console.error("History parse error", e);
        }
    }
}

function applyRefinedText(text) {
    // "整形案:\n" プレフィックスを削除
    const cleanText = text.replace(/^整形案:\n/, '');
    document.getElementById('memoInput').value = cleanText;
    document.getElementById('memoInput').dispatchEvent(new Event('input'));
    showToast("テキストを更新しました");
}

// --- セッション管理 ---

async function handleChatAI() {
    console.log('[handleChatAI] Function called');
    const memoInput = document.getElementById('memoInput');
    const text = memoInput.value.trim();
    
    console.log('[handleChatAI] Text:', text ? `"${text}"` : '(empty)');
    console.log('[handleChatAI] Has image:', !!currentImageBase64);
    console.log('[handleChatAI] Target ID:', currentTargetId);
    
    if (!text && !currentImageBase64) {
        console.log('[handleChatAI] Early return: no text and no image');
        showToast("テキストまたは画像を入力してください");
        return;
    }
    
    if (!currentTargetId) {
        console.log('[handleChatAI] Early return: no target selected');
        showToast("ターゲットを選択してください");
        return;
    }
    
    console.log('[handleChatAI] Validation passed, preparing message');
    updateState('📝', 'メッセージを準備中...', { step: 'preparing' });
    
    // 1. Prepare User Message
    let displayMessage = text;
    if (currentImageBase64) {
        const imgTag = `<br><img src="data:${currentImageMimeType};base64,${currentImageBase64}" style="max-width:100px; border-radius:4px;">`;
        displayMessage = (text ? text + "<br>" : "") + "[画像送信]" + imgTag;
    }
    
    addChatMessage('user', displayMessage);
    if (text) chatSession.push({role: 'user', content: text});
    
    // CRITICAL: Copy image data BEFORE clearing
    const imageToSend = currentImageBase64;
    const mimeToSend = currentImageMimeType;
    
    console.log('[handleChatAI] Image data copied:', imageToSend ? `${imageToSend.length} chars` : 'null');
    
    // Clear Input
    memoInput.value = '';
    memoInput.dispatchEvent(new Event('input'));
    
    // Clear preview AFTER copying data
    clearPreviewImage();
    
    // 2. Determine Model (Visual Indication)
    const hasImage = !!imageToSend;
    let modelToUse = currentModel;
    if (!modelToUse) {
        modelToUse = hasImage ? defaultMultimodalModel : defaultTextModel;
    }
    
    // Get model display name with provider prefix
    const modelInfo = availableModels.find(m => m.id === modelToUse);
    const modelDisplay = modelInfo 
        ? `[${modelInfo.provider}] ${modelInfo.name}`
        : (modelToUse || 'Auto');

    // 3. Show State
    updateState('🔄', `AI分析中... (${modelDisplay})`, {
        model: modelToUse,
        hasImage: hasImage,
        autoSelected: !currentModel,
        step: 'analyzing'
    });
    
    try {
        const systemPrompt = currentSystemPrompt || DEFAULT_SYSTEM_PROMPT;
        
        // Page Reference (from Settings Menu)
        const referenceToggle = document.getElementById('referencePageToggle');
        let referenceContext = '';
        if (referenceToggle && referenceToggle.checked && currentTargetId) {
            referenceContext = await fetchAndTruncatePageContent(currentTargetId, currentTargetType);
        }

        const payload = {
            text: text,
            target_id: currentTargetId,
            system_prompt: systemPrompt,
            session_history: chatSession.slice(0, -1).slice(-10),
            reference_context: referenceContext,
            image_data: imageToSend,
            image_mime_type: mimeToSend,
            model: currentModel // Send explicit selection or null (auto)
        };
        
        updateState('📡', 'サーバーに送信中...', { step: 'uploading' });
        console.log('[handleChatAI] Sending request to /api/chat');
        console.log('[handleChatAI] Payload:', {
            ...payload,
            image_data: payload.image_data ? `(${payload.image_data.length} chars)` : null
        });
        
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        
        console.log('[handleChatAI] Response status:', res.status);
        updateState('📥', 'レスポンスを処理中...', { step: 'processing_response' });
        
        if (!res.ok) {
            const errorData = await res.json().catch(() => ({ detail: "解析中にエラーが発生しました" }));
            throw new Error(errorData.detail?.message || JSON.stringify(errorData));
        }
        
        const data = await res.json();
        
        // Update Cost
        if (data.cost) {
            updateSessionCost(data.cost);
        }
        
        // Update State with provider prefix
        const completedModelInfo = availableModels.find(m => m.id === data.model);
        const completedDisplay = completedModelInfo 
            ? `[${completedModelInfo.provider}] ${completedModelInfo.name}`
            : data.model;
        
        updateState('✅', `Completed (${completedDisplay})`, { 
            usage: data.usage,
            cost: data.cost
        });
        
        // Add AI Message
        if (data.message) {
            const modelInfo = {
                model: data.model,
                usage: data.usage,
                cost: data.cost
            };
            addChatMessage('ai', data.message, null, modelInfo);
            chatSession.push({role: 'assistant', content: data.message});
        }
        
        if (data.properties) {
            fillForm(data.properties);
        }
        
    } catch(e) {
        console.error('[handleChatAI] Error:', e);
        updateState('❌', 'Error', { error: e.message });
        addChatMessage('system', "エラー: " + e.message);
        showToast("エラー: " + e.message);
    }
    
    console.log('[handleChatAI] Function completed');
}

function handleSessionClear() {
    chatSession = [];
    chatHistory = [];
    renderChatHistory();
    localStorage.removeItem(CHAT_HISTORY_KEY);
    showToast("セッションをクリアしました");
}

// --- バブルからの追加機能 ---

async function handleAddFromBubble(entry) {
    if (!currentTargetId) {
        showToast('ターゲットを選択してください');
        return;
    }
    
    const content = entry.message.replace(/<br>/g, '\n').replace(/整形案:\n/, '');
    
    if (currentTargetType === 'database') {
        // データベースの場合は属性設定モーダルを表示
        // 簡易実装: 直接保存（将来的にはモーダルで属性設定可能に）
        await saveToDatabase(content);
    } else {
        // ページの場合は直接追加
        await saveToPage(content);
    }
}

async function saveToDatabase(content) {
    setLoading(true, '保存中...');
    
    try {
        // フォームから属性を取得
        const properties = {};
        const inputs = document.querySelectorAll('#propertiesForm .prop-input');
        
        inputs.forEach(input => {
            const key = input.dataset.key;
            const type = input.dataset.type;
            let val = null;
            
            if (type === 'title') val = { title: [{ text: { content: content.substring(0, 100) } }] };
            else if (type === 'rich_text') val = { rich_text: [{ text: { content: input.value || content } }] };
            else if (type === 'select') val = input.value ? { select: { name: input.value } } : null;
            else if (type === 'multi_select') {
                const selected = Array.from(input.selectedOptions).map(o => ({ name: o.value }));
                val = selected.length > 0 ? { multi_select: selected } : null;
            }
            else if (type === 'date') val = input.value ? { date: { start: input.value } } : null;
            else if (type === 'checkbox') val = { checkbox: input.checked };
            
            if (val) properties[key] = val;
        });
        
        const res = await fetch('/api/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                target_db_id: currentTargetId,
                target_type: 'database',
                text: content,
                properties: properties
            })
        });
        
        if (!res.ok) throw new Error('保存に失敗しました');
        
        showToast('✅ Notionに追加しました');
    } catch(e) {
        showToast('エラー: ' + e.message);
    } finally {
        setLoading(false);
    }
}

async function saveToPage(content) {
    setLoading(true, '保存中...');
    
    try {
        const res = await fetch('/api/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                target_db_id: currentTargetId,
                target_type: 'page',
                text: content,
                properties: {}
            })
        });
        
        if (!res.ok) throw new Error('保存に失敗しました');
        
        showToast('✅ Notionに追加しました');
    } catch(e) {
        showToast('エラー: ' + e.message);
    } finally {
        setLoading(false);
    }
}

// --- ページ参照機能 ---

async function fetchAndTruncatePageContent(targetId, targetType) {
    try {
        const endpoint = targetType === 'database' 
            ? `/api/content/database/${targetId}`
            : `/api/content/page/${targetId}`;
        
        const res = await fetch(endpoint);
        if (!res.ok) throw new Error('コンテンツ取得失敗');
        
        const data = await res.json();
        let content = '';
        
        if (data.type === 'database') {
            // DBの場合: 最新10行まで、各カラムを100文字まで
            const rows = data.rows.slice(0, 10);
            rows.forEach((row, idx) => {
                Object.entries(row).forEach(([key, value]) => {
                    if (key !== 'id') {
                        const truncated = String(value).substring(0, 100);
                        if (truncated) content += `${key}: ${truncated}\n`;
                    }
                });
                if (idx < rows.length - 1) content += '---\n';
            });
        } else {
            // ページの場合: 各ブロックを500文字まで
            data.blocks.forEach(block => {
                const truncated = block.content.substring(0, 500);
                if (truncated) content += truncated + '\n';
            });
        }
        
        // 全体を2000文字に制限
        content = content.substring(0, 2000);
        
        if (!content.trim()) return '';
        
        return `<参考 既存の情報>\n${content}\n</参考 既存の情報>`;
    } catch(e) {
        console.error('Failed to fetch reference content:', e);
        return '';
    }
}

// --- プロパティUI ---

function renderDynamicForm(container, schema) {
    container.innerHTML = '';
    
    // **重要**: 逆順で表示
    const entries = Object.entries(schema).reverse();
    
    for (const [name, prop] of entries) {
        // システムプロパティはスキップ
        if (['created_time', 'last_edited_time', 'created_by', 'last_edited_by'].includes(prop.type)) {
            continue;
        }
        
        const wrapper = document.createElement('div');
        wrapper.className = 'prop-field';
        
        const label = document.createElement('label');
        label.className = 'prop-label';
        label.textContent = name;
        wrapper.appendChild(label);
        
        let input;
        
        if (prop.type === 'select' || prop.type === 'multi_select') {
            input = document.createElement('select');
            input.className = 'prop-input';
            input.dataset.key = name;
            input.dataset.type = prop.type;
            
            if (prop.type === 'multi_select') {
                input.multiple = true;
            }
            
            // 空のオプション
            const def = document.createElement('option');
            def.value = "";
            def.textContent = "(未選択)";
            input.appendChild(def);
            
            // スキーマのオプション
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
            input.dataset.key = name;
            input.dataset.type = prop.type;
        } else if (prop.type === 'checkbox') {
            input = document.createElement('input');
            input.type = 'checkbox';
            input.className = 'prop-input';
            input.dataset.key = name;
            input.dataset.type = prop.type;
        } else {
            // text, title, rich_text, number, url, etc.
            input = document.createElement('input');
            input.type = 'text';
            input.className = 'prop-input';
            input.dataset.key = name;
            input.dataset.type = prop.type;
        }
        
        wrapper.appendChild(input);
        container.appendChild(wrapper);
    }
    
    // 動的タグサジェストを更新
    updateDynamicSelectOptions();
}

function updateDynamicSelectOptions() {
    if (!currentPreviewData || !currentPreviewData.rows) return;
    
    // 全てのselect/multi_select要素を取得
    const selects = document.querySelectorAll('#propertiesForm select');
    
    selects.forEach(select => {
        const propName = select.dataset.key;
        const propType = select.dataset.type;
        
        if (!propName || (propType !== 'select' && propType !== 'multi_select')) return;
        
        // プレビューデータから既存の値を抽出
        const existingValues = new Set();
        currentPreviewData.rows.forEach(row => {
            const value = row[propName];
            if (value && value.trim()) {
                // カンマ区切りの値を分割（multi_select用）
                if (value.includes(',')) {
                    value.split(',').forEach(v => existingValues.add(v.trim()));
                } else {
                    existingValues.add(value.trim());
                }
            }
        });
        
        // スキーマのオプションを取得
        const schemaOptions = new Set();
        Array.from(select.options).forEach(opt => {
            if (opt.value) schemaOptions.add(opt.value);
        });
        
        // データから抽出した値をオプションに追加
        existingValues.forEach(value => {
            if (!schemaOptions.has(value)) {
                const opt = document.createElement('option');
                opt.value = value;
                opt.textContent = value + ' (データから)';
                select.appendChild(opt);
            }
        });
    });
}

function fillForm(properties) {
    const inputs = document.querySelectorAll('#propertiesForm .prop-input');
    
    inputs.forEach(input => {
        const key = input.dataset.key;
        const type = input.dataset.type;
        
        if (!properties[key]) return; // No data for this field
        
        const prop = properties[key];
        
        try {
            if (type === 'title' && prop.title && prop.title[0]) {
                input.value = prop.title[0].text.content;
            } else if (type === 'rich_text' && prop.rich_text && prop.rich_text[0]) {
                input.value = prop.rich_text[0].text.content;
            } else if (type === 'select' && prop.select) {
                input.value = prop.select.name;
            } else if (type === 'multi_select' && prop.multi_select) {
                // For multi-select, set all matching options as selected
                const names = prop.multi_select.map(item => item.name);
                Array.from(input.options).forEach(opt => {
                    opt.selected = names.includes(opt.value);
                });
            } else if (type === 'date' && prop.date) {
                input.value = prop.date.start.split('T')[0]; // Extract date part only
            } else if (type === 'checkbox') {
                input.checked = prop.checkbox || false;
            }
        } catch(e) {
            console.warn(`Failed to fill field ${key}:`, e);
        }
    });
}



function renderDatabaseTable(data, container) {
    if (!container) container = document.getElementById('contentModalPreview');
    container.innerHTML = '';
    
    if (!data.columns || data.columns.length === 0) {
        container.innerHTML = '<p class="placeholder-text">(履歴なし)</p>';
        return;
    }
    
    // Sort columns to put "Title" or "Name" first if possible
    const sortedCols = [...data.columns].sort((a, b) => {
        const aLow = a.toLowerCase();
        const bLow = b.toLowerCase();
        if (aLow === 'title' || aLow === 'name') return -1;
        if (bLow === 'title' || bLow === 'name') return 1;
        return 0;
    });

    let html = '<div class="notion-table-wrapper"><table class="notion-table"><thead><tr>';
    sortedCols.forEach(col => html += `<th>${col}</th>`);
    html += '</tr></thead><tbody>';
    
    data.rows.forEach(row => {
        html += '<tr>';
        sortedCols.forEach(col => html += `<td>${row[col] || ''}</td>`);
        html += '</tr>';
    });
    
    html += '</tbody></table></div>';
    container.innerHTML = html;
}

function renderPageBlocks(blocks, container) {
    if (!container) container = document.getElementById('contentModalPreview');
    container.innerHTML = '';
    
    if (!blocks || blocks.length === 0) {
        container.innerHTML = '<p class="placeholder-text">(内容なし)</p>';
        return;
    }
    
    blocks.forEach(block => {
        const div = document.createElement('div');
        div.className = `notion-block notion-${block.type}`;
        div.textContent = block.content;
        container.appendChild(div);
    });
}

// --- ユーティリティ & キャッシュ & サーバー通信 ---

async function fetchWithCache(url, key) {
    const cached = localStorage.getItem(key);
    if (cached) {
        try {
            const entry = JSON.parse(cached);
            if (Date.now() - entry.timestamp < CACHE_TTL) {
                console.log(`[Cache Hit] ${key}`);
                return entry.data;
            }
        } catch(e) { console.error("Cache parse error", e); }
    }
    
    console.log(`[Cache Miss] Fetching ${url}`);
    
    try {
        const res = await fetch(url);
        
        if (!res.ok) {
            const errorBody = await res.text().catch(() => 'レスポンス本文を読み取れませんでした');
            throw new Error(`HTTPエラー ${res.status}: ${errorBody.substring(0, 100)}`);
        }
        
        const data = await res.json();
        
        localStorage.setItem(key, JSON.stringify({
            timestamp: Date.now(),
            data: data
        }));
        return data;
        
    } catch(e) {
        console.error('[Fetch Error]', { url, error: e });
        throw e;
    }
}

async function loadTargets(selector) {
    selector.innerHTML = '<option disabled selected>読み込み中...</option>';
    try {
        const data = await fetchWithCache('/api/targets', TARGETS_CACHE_KEY);
        renderTargetOptions(selector, data.targets);
    } catch(e) {
        console.error(e);
        showToast("ターゲット読み込み失敗: " + e.message);
        selector.innerHTML = '<option disabled selected>エラー</option>';
    }
}

function renderTargetOptions(selector, targets) {
    selector.innerHTML = '';
    const lastSelected = localStorage.getItem(LAST_TARGET_KEY);
    
    // 新規作成オプションを追加
    const newPageOpt = document.createElement('option');
    newPageOpt.value = '__NEW_PAGE__';
    newPageOpt.textContent = '➕ 新規作成';
    newPageOpt.dataset.type = 'new';
    selector.appendChild(newPageOpt);
    
    if (!targets || targets.length === 0) {
        const opt = document.createElement('option');
        opt.textContent = "ターゲットが見つかりません";
        selector.appendChild(opt);
        return;
    }

    targets.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = `[${t.type === 'database' ? 'DB' : 'Page'}] ${t.title}`;
        opt.dataset.type = t.type;
        if (t.id === lastSelected) opt.selected = true;
        selector.appendChild(opt);
    });
    
    // Trigger initial change to render form
    if (selector.value && selector.value !== '__NEW_PAGE__') handleTargetChange(selector.value);
}

async function handleTargetChange(targetId) {
    if (!targetId) return;
    currentTargetId = targetId;
    localStorage.setItem(LAST_TARGET_KEY, targetId);
    
    const formContainer = document.getElementById('propertiesForm');
    formContainer.innerHTML = '<div class="spinner-small"></div> 読み込み中...';
    
    const selector = document.getElementById('appSelector');
    const selectedOption = selector.options[selector.selectedIndex];
    currentTargetType = selectedOption ? selectedOption.dataset.type : 'database';
    currentTargetName = selectedOption ? selectedOption.textContent : '';
    
    // システムプロンプト編集ボタンと内容ボタンを有効化
    const settingsBtn = document.getElementById('settingsBtn');
    const viewContentBtn = document.getElementById('viewContentBtn');
    if (settingsBtn) settingsBtn.disabled = false;
    if (viewContentBtn) viewContentBtn.disabled = false;
    
    try {
        const data = await fetchWithCache(`/api/schema/${targetId}`, SCHEMA_CACHE_PREFIX + targetId);
        currentSchema = data.schema;
        
        // Form generation
        renderDynamicForm(formContainer, currentSchema);
        
        // Show properties only for databases
        const propsSection = document.getElementById('propertiesSection');
        const propsContainer = document.getElementById('propertiesContainer');
        if (currentTargetType === 'database') {
            // データベースの場合は属性セクションを表示（デフォルトで閉じた状態）
            if (propsContainer) propsContainer.style.display = 'block';
            if (propsSection) propsSection.classList.add('hidden');
        } else {
            // ページの場合は属性セクション全体を非表示
            if (propsContainer) propsContainer.style.display = 'none';
        }
        
        // Initialize prompt
        try {
            // localStorageから取得
            const promptKey = `${LOCAL_PROMPT_PREFIX}${targetId}`;
            currentSystemPrompt = localStorage.getItem(promptKey) || null;
            
            // 古いサーバーAPIコードは削除
        } catch (e) {
            console.error("Prompt load failed:", e);
            currentSystemPrompt = null;
        }

    } catch(e) {
        console.error('[handleTargetChange Error]', e);
        formContainer.innerHTML = `<p class="error">スキーマ読み込み失敗: ${e.message}</p>`;
        showToast("スキーマ読み込みエラー");
    }
}

async function handleDirectSave() {
    if (!currentTargetId) return showToast("ターゲットを選択してください");
    
    setLoading(true, "保存中...");
    
    const text = document.getElementById('memoInput').value;
    
    const properties = {};
    const inputs = document.querySelectorAll('#propertiesForm .prop-input');
    
    inputs.forEach(input => {
        const key = input.dataset.key;
        const type = input.dataset.type;
        let val = null;
        
        if (type === 'title') val = { title: [{ text: { content: input.value } }] };
        else if (type === 'rich_text') val = { rich_text: [{ text: { content: input.value } }] };
        else if (type === 'select') val = input.value ? { select: { name: input.value } } : null;
        else if (type === 'multi_select') {
            const selected = Array.from(input.selectedOptions).map(o => ({ name: o.value }));
            val = selected.length > 0 ? { multi_select: selected } : null;
        }
        else if (type === 'date') val = input.value ? { date: { start: input.value } } : null;
        else if (type === 'checkbox') val = { checkbox: input.checked };
        
        if (val) properties[key] = val;
    });
    
    try {
        const res = await fetch('/api/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                target_db_id: currentTargetId,
                target_type: currentTargetType,
                text: text,
                properties: properties
            })
        });
        
        if (!res.ok) {
            const errorData = await res.json().catch(() => ({ detail: "保存中にエラーが発生しました" }));
            let detail = errorData.detail;
            
            if (typeof detail === 'object') {
                detail = JSON.stringify(detail, null, 2);
            }
            
            const errMsg = `[保存エラー ${res.status}]\n${detail || '詳細はサーバーログを確認してください'}`;
            throw new Error(errMsg);
        }
        
        addChatMessage('system', "Notionに保存しました！");
        showToast("保存完了");
        
        document.getElementById('memoInput').value = "";
        document.getElementById('memoInput').dispatchEvent(new Event('input'));
        localStorage.removeItem(DRAFT_KEY);
        
    } catch(e) {
        showToast("エラー: " + e.message);
    } finally {
        setLoading(false);
    }
}

function setLoading(isLoading, text) {
    const ind = document.getElementById('loadingIndicator');
    const loadingText = document.getElementById('loadingText');
    
    if (isLoading) {
        ind.classList.remove('hidden');
        if (loadingText && text) loadingText.textContent = text;
    } else {
        ind.classList.add('hidden');
    }
}

function updateSaveStatus(text) {
    const status = document.getElementById('saveStatus');
    if (status) {
        status.textContent = text;
        if (text) {
            setTimeout(() => {
                if (status.textContent === text) status.textContent = "";
            }, 3000);
        }
    }
}

function showToast(msg) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 3000);
}

// --- SystemPrompt編集機能 ---

function openPromptModal() {
    if (!currentTargetId) {
        showToast('ターゲットを選択してください');
        return;
    }
    
    const modal = document.getElementById('promptModal');
    const targetNameSpan = document.getElementById('modalTargetName');
    const textarea = document.getElementById('promptTextarea');
    const saveBtn = document.getElementById('savePromptBtn');
    
    // ターゲット名を表示
    targetNameSpan.textContent = currentTargetName;
    
    // 現在のサーバー保存値を使用
    const currentPrompt = currentSystemPrompt;
    
    // 値がなければデフォルトを表示
    textarea.value = currentPrompt !== null && currentPrompt !== undefined ? currentPrompt : DEFAULT_SYSTEM_PROMPT;
    textarea.disabled = false;
    saveBtn.disabled = false;
    
    // モーダルを表示
    modal.classList.remove('hidden');
}

function closePromptModal() {
    const modal = document.getElementById('promptModal');
    modal.classList.add('hidden');
}

async function saveSystemPrompt() {
    if (!currentTargetId) return;

    const textarea = document.getElementById('promptTextarea');
    const saveBtn = document.getElementById('savePromptBtn');
    const newPrompt = textarea.value.trim();
    
    saveBtn.disabled = true;
    
    try {
        // localStorageに保存
        const promptKey = `${LOCAL_PROMPT_PREFIX}${currentTargetId}`;
        
        if (newPrompt) {
             localStorage.setItem(promptKey, newPrompt);
        } else {
             // 空の場合は削除（デフォルトに戻す）
             localStorage.removeItem(promptKey);
        }
        
        currentSystemPrompt = newPrompt || null; // null if empty
        
        closePromptModal();
        showToast('✅ システムプロンプトを保存しました');
    } catch (e) {
        console.error('Failed to save prompt:', e);
        showToast('❌ 保存に失敗しました');
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = '保存';
    }
}

// イベントリスナー登録
document.addEventListener('DOMContentLoaded', () => {
    // 既存のDOMContentLoadedとは別に実行される
    const editPromptBtn = document.getElementById('editPromptBtn');
    const closeModalBtn = document.getElementById('closeModalBtn');
    const cancelPromptBtn = document.getElementById('cancelPromptBtn');
    const savePromptBtn = document.getElementById('savePromptBtn');
    const promptModal = document.getElementById('promptModal');

    if (editPromptBtn) editPromptBtn.addEventListener('click', openPromptModal);
    if (closeModalBtn) closeModalBtn.addEventListener('click', closePromptModal);
    if (cancelPromptBtn) cancelPromptBtn.addEventListener('click', closePromptModal);
    if (savePromptBtn) savePromptBtn.addEventListener('click', saveSystemPrompt);

    // モーダル外クリックで閉じる
    if (promptModal) {
        promptModal.addEventListener('click', (e) => {
            if (e.target.id === 'promptModal') {
                closePromptModal();
            }
        });
    }

    // ESCキーで閉じる
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const promptModal = document.getElementById('promptModal');
            const newPageModal = document.getElementById('newPageModal');
            const contentModal = document.getElementById('contentModal');
            
            if (promptModal && !promptModal.classList.contains('hidden')) {
                closePromptModal();
            } else if (newPageModal && !newPageModal.classList.contains('hidden')) {
                closeNewPageModal();
            } else if (contentModal && !contentModal.classList.contains('hidden')) {
                closeContentModal();
            }
        }
    });
    
    // 新規ページモーダルのイベントリスナー
    const closeNewPageModalBtn = document.getElementById('closeNewPageModalBtn');
    const cancelNewPageBtn = document.getElementById('cancelNewPageBtn');
    const createNewPageBtn = document.getElementById('createNewPageBtn');
    const newPageModal = document.getElementById('newPageModal');
    
    if (closeNewPageModalBtn) closeNewPageModalBtn.addEventListener('click', closeNewPageModal);
    if (cancelNewPageBtn) cancelNewPageBtn.addEventListener('click', closeNewPageModal);
    if (createNewPageBtn) createNewPageBtn.addEventListener('click', createNewPage);
    
    if (newPageModal) {
        newPageModal.addEventListener('click', (e) => {
            if (e.target.id === 'newPageModal') {
                closeNewPageModal();
            }
        });
    }
    
    // ページ内容モーダルのイベントリスナー
    const closeContentModalBtn = document.getElementById('closeContentModalBtn');
    const contentModal = document.getElementById('contentModal');
    
    if (closeContentModalBtn) closeContentModalBtn.addEventListener('click', closeContentModal);
    
    if (contentModal) {
        contentModal.addEventListener('click', (e) => {
            if (e.target.id === 'contentModal') {
                closeContentModal();
            }
        });
    }
});

// --- 新規ページ作成機能 ---

function openNewPageModal() {
    const modal = document.getElementById('newPageModal');
    const input = document.getElementById('newPageNameInput');
    
    if (input) input.value = '';
    if (modal) modal.classList.remove('hidden');
}

function closeNewPageModal() {
    const modal = document.getElementById('newPageModal');
    if (modal) modal.classList.add('hidden');
}

async function createNewPage() {
    const input = document.getElementById('newPageNameInput');
    const pageName = input.value.trim();
    
    if (!pageName) {
        showToast('ページ名を入力してください');
        return;
    }
    
    setLoading(true, '新規ページ作成中...');
    
    try {
        const res = await fetch('/api/pages/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ page_name: pageName })
        });
        
        if (!res.ok) {
            const errorData = await res.json().catch(() => ({ detail: "ページ作成中にエラーが発生しました" }));
            throw new Error(errorData.detail || 'ページ作成に失敗しました');
        }
        
        const newPage = await res.json();
        
        showToast('✅ ページを作成しました');
        closeNewPageModal();
        
        // キャッシュをクリアしてターゲットリストをリロード
        localStorage.removeItem(TARGETS_CACHE_KEY);
        const appSelector = document.getElementById('appSelector');
        await loadTargets(appSelector);
        
        // 新規作成したページを選択
        if (newPage.id) {
            appSelector.value = newPage.id;
            await handleTargetChange(newPage.id);
        }
        
    } catch(e) {
        showToast('エラー: ' + e.message);
    } finally {
        setLoading(false);
    }
}

// --- ページ内容モーダル機能 ---

function openContentModal() {
    if (!currentTargetId) {
        showToast('ターゲットを選択してください');
        return;
    }
    
    const modal = document.getElementById('contentModal');
    
    // タイトルをNotionリンクに変更
    const titleEl = document.getElementById('contentModalTitle');
    if (titleEl && currentTargetId) {
        const notionUrl = `https://www.notion.so/${currentTargetId.replace(/-/g, '')}`;
        titleEl.innerHTML = `<a href="${notionUrl}" target="_blank" style="text-decoration: none; color: inherit; display: flex; align-items: center; gap: 8px;">📄 ${currentTargetName} <span style="font-size: 0.8em; opacity: 0.7;">🔗</span></a>`;
    }

    if (modal) modal.classList.remove('hidden');
    
    // コンテンツを読み込んで表示
    fetchAndDisplayContentInModal(currentTargetId, currentTargetType);
}

function closeContentModal() {
    const modal = document.getElementById('contentModal');
    if (modal) modal.classList.add('hidden');
}

async function fetchAndDisplayContentInModal(targetId, targetType) {
    const container = document.getElementById('contentModalPreview');
    if (!container) return;
    
    // Clear previous
    container.innerHTML = '<div class="spinner-small"></div> 読み込み中...';
    
    try {
        const endpoint = targetType === 'database' 
            ? `/api/content/database/${targetId}`
            : `/api/content/page/${targetId}`;
        
        const res = await fetch(endpoint);
        
        if (!res.ok) {
            throw new Error('コンテンツの取得に失敗しました');
        }
        
        currentPreviewData = null;
        const data = await res.json();
        
        if (data.type === 'database') {
            currentPreviewData = data;  // タグサジェスト用に保存
            renderDatabaseTable(data, container);
            container.classList.add('database-view');
            updateDynamicSelectOptions();  // タグサジェストを更新
        } else {
            renderPageBlocks(data.blocks, container);
            container.classList.remove('database-view');
        }
    } catch(e) {
        container.innerHTML = '<p class="error">プレビューを取得できませんでした</p>';
    }
}

// --- New Features (Settings, Models, State) ---

function toggleSettingsMenu() {
    const menu = document.getElementById('settingsMenu');
    menu.classList.toggle('hidden');
}

async function loadAvailableModels() {
    try {
        const res = await fetch('/api/models');
        if (!res.ok) throw new Error('Failed to load models');
        
        const data = await res.json();
        
        // Categorize models
        availableModels = data.all || [];
        textOnlyModels = data.text_only || [];
        visionModels = data.vision_capable || [];
        defaultTextModel = data.defaults?.text;
        defaultMultimodalModel = data.defaults?.multimodal;
        
        // Load user's last selection or use default (null for auto)
        currentModel = localStorage.getItem('memo_ai_selected_model') || null;
        
        // Validate that the stored model is still available
        if (currentModel) {
            const isValid = availableModels.some(m => m.id === currentModel);
            if (!isValid) {
                console.warn(`Stored model '${currentModel}' is no longer available. Resetting to Auto.`);
                currentModel = null;
                localStorage.removeItem('memo_ai_selected_model');
                showToast('保存されたモデルが無効なため、自動選択にリセットしました');
            }
        }
        
        console.log("Models loaded:", availableModels.length);
    } catch (err) {
        console.error('Failed to load models:', err);
        showToast('モデルリストの読み込みに失敗しました');
    }
}

function openModelModal() {
    const modal = document.getElementById('modelModal');
    
    // Initialize temp state with current committed state
    tempSelectedModel = currentModel;
    
    renderModelList();
    modal.classList.remove('hidden');
}

function renderModelList() {
    const modelList = document.getElementById('modelList');
    modelList.innerHTML = '';
    
    // Resolve full model info for defaults
    const textModelInfo = availableModels.find(m => m.id === defaultTextModel);
    const visionModelInfo = availableModels.find(m => m.id === defaultMultimodalModel);
    
    const textDisplay = textModelInfo 
        ? `[${textModelInfo.provider}] ${textModelInfo.name}`
        : (defaultTextModel || 'Unknown');
    const visionDisplay = visionModelInfo 
        ? `[${visionModelInfo.provider}] ${visionModelInfo.name}`
        : (defaultMultimodalModel || 'Unknown');

    // Auto Option (Recommended)
    const autoItem = document.createElement('div');
    autoItem.className = 'model-item';
    if (tempSelectedModel === null) autoItem.classList.add('selected');
    autoItem.innerHTML = `
        <div class="model-info">
            <div class="model-name">✨ 自動選択 (推奨)</div>
            <div class="model-provider" style="display: flex; flex-direction: column; gap: 4px; margin-top: 4px;">
                <div style="font-size: 0.9em;">📝 テキスト: <span style="font-weight: 500;">${textDisplay}</span></div>
                <div style="font-size: 0.9em;">🖼️ 画像: <span style="font-weight: 500;">${visionDisplay}</span></div>
            </div>
        </div>
        <span class="model-check">${tempSelectedModel === null ? '✓' : ''}</span>
    `;
    autoItem.onclick = () => selectTempModel(null);
    modelList.appendChild(autoItem);

    // Separator
    const separator = document.createElement('div');
    separator.style.borderBottom = '1px solid var(--border-color)';
    separator.style.margin = '8px 0';
    modelList.appendChild(separator);

    // Single Unified List
    availableModels.forEach(model => {
        modelList.appendChild(createModelItem(model));
    });
}

function createModelItem(model) {
    const item = document.createElement('div');
    item.className = 'model-item';
    
    const isSelected = model.id === tempSelectedModel;
    if (isSelected) item.classList.add('selected');
    
    // Vision Indicator
    const visionIcon = model.supports_vision ? ' 📷' : '';
    
    // Format: [Provider] model-name [📷]
    const displayName = `[${model.provider}] ${model.name}${visionIcon}`;
    
    const rateLimitBadge = model.rate_limit_note 
        ? `<div class="model-badge warning">⚠️ ${model.rate_limit_note}</div>` 
        : '';
        
    item.innerHTML = `
        <div class="model-info">
            <div class="model-name">${displayName}</div>
            ${rateLimitBadge}
        </div>
        <span class="model-check">${isSelected ? '✓' : ''}</span>
    `;
    
    item.onclick = () => selectTempModel(model.id);
    return item;
}

function selectTempModel(modelId) {
    tempSelectedModel = modelId;
    renderModelList();
}

function saveModelSelection() {
    currentModel = tempSelectedModel;
    
    if (currentModel) {
        localStorage.setItem('memo_ai_selected_model', currentModel);
    } else {
        localStorage.removeItem('memo_ai_selected_model');
    }
    
    showToast('モデル設定を保存しました');
    closeModelModal();
}

function closeModelModal() {
    document.getElementById('modelModal').classList.add('hidden');
}

function updateSessionCost(cost) {
    sessionCost += cost;
    const display = document.getElementById('sessionCost');
    if (display) {
        display.textContent = '$' + sessionCost.toFixed(5);
    }
}

// State Display Logic
let currentState = null;

function showState(icon, text, details = null) {
    const stateDisplay = document.getElementById('stateDisplay');
    const stateIcon = document.getElementById('stateIcon');
    const stateText = document.getElementById('stateText');
    const stateDetailsContent = document.getElementById('stateDetailsContent');
    const stateDetails = document.getElementById('stateDetails');
    
    stateIcon.textContent = icon;
    stateText.textContent = text;
    
    if (details) {
        stateDetailsContent.textContent = JSON.stringify(details, null, 2);
    } else {
        stateDetailsContent.textContent = "";
    }
    
    stateDisplay.classList.remove('hidden');
    stateDetails.classList.add('hidden'); // Default collapsed
    
    // Toggle handler
    const toggle = document.getElementById('stateToggle');
    toggle.onclick = (e) => {
        e.stopPropagation();
        stateDetails.classList.toggle('hidden');
    };
}

function updateState(icon, text, details = null) {
    showState(icon, text, details);
    
    // If success/completed, hide after delay
    if (icon === '✅') {
        setTimeout(() => {
            document.getElementById('stateDisplay').classList.add('hidden');
        }, 5000);
    }
}
