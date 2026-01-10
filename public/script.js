
// --- キャッシュ設定 (Cache Settings) ---
// リクエスト数を削減し、レスポンス速度を向上させるためにブラウザの localStorage を利用します。
const CACHE_TTL = 180000; // 3分 (ミリ秒): キャッシュの有効期限
const TARGETS_CACHE_KEY = 'memo_ai_targets';
const SCHEMA_CACHE_PREFIX = 'memo_ai_schema_';
const DRAFT_KEY = 'memo_ai_draft';               // 入力中の下書き保存用キー
const LAST_TARGET_KEY = 'memo_ai_last_target';   // 最後に選択したターゲットID
const CHAT_HISTORY_KEY = 'memo_ai_chat_history'; // チャット履歴
const LOCAL_PROMPT_PREFIX = 'memo_ai_prompt_';   // システムプロンプト（ターゲット毎）
const SHOW_MODEL_INFO_KEY = 'memo_ai_show_model_info';
const REFERENCE_PAGE_KEY = 'memo_ai_reference_page'; // 「ページを参照」チェックボックスの状態

// デフォルトのシステムプロンプト
// AIの基本的な役割定義。ターゲットごとに上書き可能です。
const DEFAULT_SYSTEM_PROMPT = `優秀な秘書として、ユーザーのタスクを明確にする手伝いをすること。
明確な実行できる タスク名に言い換えて。先頭に的確な絵文字を追加して
画像の場合は、そこから何をしようとしているのか推定して、タスクにして。
会話的な返答はしない。
返答は機械的に、タスク名としてふさわしい文字列のみを出力すること。`;

// --- グローバル状態管理 (Global State) ---
let chatHistory = [];  // UI表示用の全チャット履歴: [{type, message, properties, timestamp}]
let chatSession = [];  // AIに送信する短期会話コンテキスト: {role, content}
let currentTargetId = null;       // 現在選択中のNotionターゲットID
let currentTargetName = '';       // 現在選択中のターゲット名
let currentTargetType = 'database'; // 'database' または 'page'
let currentSchema = null;         // Notionデータベースのスキーマ構造
let currentPreviewData = null;    // タグサジェスト用のプレビューデータ
let currentSystemPrompt = null;   // 現在適用されているシステムプロンプト
let isComposing = false;          // IME入力中かどうか（Enter送信の制御に使用）

// --- 画像入力状態 (Image State) ---
let currentImageBase64 = null;    // 送信待機中の画像データ（Base64文字列）
let currentImageMimeType = null;  // 画像のMIMEタイプ (image/jpeg, image/png 等)

// --- モデル & コスト管理 (Model & Cost State) ---
let availableModels = [];         // 利用可能な全モデルリスト
let textOnlyModels = [];          // テキスト専用モデルリスト
let visionModels = [];            // 画像認識対応モデルリスト
let defaultTextModel = null;      // デフォルトのテキストモデル
let defaultMultimodalModel = null; // デフォルトの画像対応モデル
let currentModel = null;          // 現在ユーザーが選択しているモデル（nullなら自動選択）
let tempSelectedModel = null;     // 設定モーダルでの一時選択状態
let sessionCost = 0.0;            // 現在のセッションでの推定コスト合計
let showModelInfo = true;         // チャットバブルにモデル情報を表示するかどうか

document.addEventListener('DOMContentLoaded', () => {
    // === 初期化処理 (Initialization) ===
    // HTML要素の取得とイベントリスナーの設定を行います。

    // DOM要素の取得
    const appSelector = document.getElementById('appSelector');
    const memoInput = document.getElementById('memoInput');
    const sessionClearBtn = document.getElementById('sessionClearBtn');
    const viewContentBtn = document.getElementById('viewContentBtn');
    const settingsBtn = document.getElementById('settingsBtn');
    const settingsMenu = document.getElementById('settingsMenu');
    
    // --- 画像アップロード UI (Image Input Elements) ---
    const addMediaBtn = document.getElementById('addMediaBtn');
    const mediaMenu = document.getElementById('mediaMenu');
    const cameraBtn = document.getElementById('cameraBtn');
    const galleryBtn = document.getElementById('galleryBtn');
    const cameraInput = document.getElementById('cameraInput');
    const imageInput = document.getElementById('imageInput');
    const removeImageBtn = document.getElementById('removeImageBtn');
    
    // メディアメニューのトグル
    if (addMediaBtn) {
        addMediaBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            mediaMenu.classList.toggle('hidden');
        });
        
        // メニュー外クリックで閉じる処理
        document.addEventListener('click', (e) => {
            if (mediaMenu && !mediaMenu.contains(e.target) && e.target !== addMediaBtn) {
                mediaMenu.classList.add('hidden');
            }
        });

        // カメラ/ギャラリー起動ボタン
        if (cameraBtn) cameraBtn.addEventListener('click', () => {
            cameraInput.click();
            mediaMenu.classList.add('hidden');
        });
        
        if (galleryBtn) galleryBtn.addEventListener('click', () => {
            imageInput.click();
            mediaMenu.classList.add('hidden');
        });

        // ファイル選択時のハンドラ（画像圧縮とプレビュー）
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
                
                // クライアントサイドでの画像圧縮 (Canvasを使用)
                // サーバーへの転送量を減らし、AIのトークン消費を抑えるために重要です。
                const { base64, mimeType } = await compressImage(file);
                console.log('[Image Upload] Image compressed, new size:', base64.length, 'chars');
                
                // プレビュー表示
                setPreviewImage(base64, mimeType);
                updateState('✅', '画像準備完了', { step: 'ready' });
                showToast("画像を読み込みました");
                setTimeout(() => {
                    const stateDisplay = document.getElementById('stateDisplay');
                    if (stateDisplay) stateDisplay.classList.add('hidden');
                }, 2000);
                
                // 同じファイルを再選択できるようにリセット
                e.target.value = ''; 
            } catch (err) {
                console.error('[Image Upload] Error:', err);
                showToast("画像の読み込みに失敗しました: " + err.message);
            }
        };
        
        if (cameraInput) cameraInput.addEventListener('change', handleFileSelect);
        if (imageInput) imageInput.addEventListener('change', handleFileSelect);
        
        // 画像削除ボタン
        if (removeImageBtn) removeImageBtn.addEventListener('click', () => {
            console.log('[Image Upload] Removing image preview');
            clearPreviewImage();
        });
    }
    
    // 1. ラストラフ（下書き）の復元
    // ブラウザのlocalStorageから編集中のテキストを復元します。
    const savedDraft = localStorage.getItem(DRAFT_KEY);
    if (savedDraft) {
        memoInput.value = savedDraft;
        // 高さ調整のためにinputイベントを発火
        memoInput.dispatchEvent(new Event('input'));
    }
    
    // 2. テキストエリアの自動リサイズ (Auto-resize)
    // 入力内容に応じて高さを自動調整し、スマホでも見やすくします。
    memoInput.addEventListener('input', () => {
        memoInput.style.height = 'auto';
        memoInput.style.height = Math.min(memoInput.scrollHeight, 120) + 'px';
        
        // 入力のたびに下書き保存
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

    // Reference Page Toggle Logic
    const referenceToggle = document.getElementById('referencePageToggle');
    if (referenceToggle) {
        const savedRefState = localStorage.getItem(REFERENCE_PAGE_KEY);
        if (savedRefState !== null) {
            referenceToggle.checked = savedRefState === 'true';
        }
        
        referenceToggle.addEventListener('change', (e) => {
            localStorage.setItem(REFERENCE_PAGE_KEY, e.target.checked);
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
        
        // Close active chat bubbles when clicking outside
        document.querySelectorAll('.chat-bubble.show-actions').forEach(b => {
            b.classList.remove('show-actions');
        });
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
    
    // 11. Debug Panel
    loadDebugInfo();
    const toggleDebugBtn = document.getElementById('toggleDebugBtn');
    if (toggleDebugBtn) {
        toggleDebugBtn.addEventListener('click', () => {
            const debugPanel = document.getElementById('debugPanel');
            const isHidden = debugPanel.classList.contains('hidden');
            if (isHidden) {
                debugPanel.classList.remove('hidden');
                toggleDebugBtn.textContent = '非表示';
            } else {
                debugPanel.classList.add('hidden');
                toggleDebugBtn.textContent = '表示';
            }
        });
    }
});

// === Debug Information ===
async function loadDebugInfo() {
    const debugContent = document.getElementById('debugContent');
    if (!debugContent) return;
    
    try {
        const res = await fetch('/api/debug');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        
        let html = '';
        
        // Environment
        html += '<div class="debug-section"><h4>⚙️ Environment</h4>';
        Object.entries(data.environment).forEach(([key, value]) => {
            html += `<div class="debug-item"><span class="debug-key">${key}:</span><span class="debug-value">${value}</span></div>`;
        });
        html += '</div>';
        
        // Paths
        html += '<div class="debug-section"><h4>📁 Paths</h4>';
        Object.entries(data.paths).forEach(([key, value]) => {
            const displayValue = Array.isArray(value) ? value.join(', ') : value;
            html += `<div class="debug-item"><span class="debug-key">${key}:</span><span class="debug-value">${displayValue}</span></div>`;
        });
        html += '</div>';
        
        // Filesystem Checks
        html += '<div class="debug-section"><h4>🗂️ Filesystem Checks</h4>';
        Object.entries(data.filesystem_checks).forEach(([path, info]) => {
            const existsClass = info.exists ? 'debug-true' : 'debug-false';
            html += `<div class="debug-item">`;
            html += `<span class="debug-key">${path}:</span>`;
            html += `<span class="${existsClass}">${info.exists ? '✅ EXISTS' : '❌ NOT FOUND'}</span>`;
            if (info.exists) {
                if (info.is_file) html += ` | File (${info.size} bytes)`;
                if (info.is_dir && info.contents) html += ` | Dir: [${info.contents.join(', ')}]`;
            }
            html += `</div>`;
        });
        html += '</div>';
        
        // CWD Contents
        html += '<div class="debug-section"><h4>📂 Current Directory Contents</h4>';
        if (Array.isArray(data.cwd_contents)) {
            html += `<div class="debug-item">${data.cwd_contents.join(', ')}</div>`;
        } else {
            html += `<div class="debug-item">${data.cwd_contents}</div>`;
        }
        html += '</div>';
        
        // Static File Mount
        html += '<div class="debug-section"><h4>🚀 Static File Mount</h4>';
        html += `<div class="debug-item">${data.static_file_mount}</div>`;
        html += '</div>';
        
        // App Routes
html += '<div class="debug-section"><h4>🛣️ Registered Routes (First 10)</h4>';
        data.app_routes.slice(0, 10).forEach(route => {
            html += `<div class="debug-item">`;
            html += `<span class="debug-key">${route.path}:</span>`;
            html += `<span class="debug-value">${route.methods.join(', ') || 'ANY'} (${route.name})</span>`;
            html += `</div>`;
        });
        html += '</div>';
        
        debugContent.innerHTML = html;
        
    } catch (err) {
        debugContent.innerHTML = `<div style="color: #e57373;">Failed to load debug info: ${err.message}</div>`;
    }
}

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
            // Tap to show "Add to Notion"
            bubble.style.cursor = 'pointer';
            bubble.onclick = (e) => {
                // Don't toggle if selecting text
                if (window.getSelection().toString().length > 0) return;
                
                // Don't toggle if clicking a link/button inside (except this bubble's container)
                if (e.target.tagName === 'A') return;

                // Close other open bubbles
                const wasShown = bubble.classList.contains('show-actions');
                document.querySelectorAll('.chat-bubble.show-actions').forEach(b => {
                    b.classList.remove('show-actions');
                });

                if (!wasShown) {
                    bubble.classList.add('show-actions');
                }
                
                e.stopPropagation(); // Prevent document click from closing it
            };

            const addBtn = document.createElement('button');
            addBtn.className = 'bubble-add-btn';
            addBtn.textContent = 'Notionに追加';
            addBtn.onclick = (e) => {
                e.stopPropagation();
                handleAddFromBubble(entry);
                // Optional: remove class after adding?
                // bubble.classList.remove('show-actions'); 
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

// --- チャット・分析メインロジック (Core Logic) ---

async function handleChatAI() {
    console.log('[handleChatAI] Function called');
    const memoInput = document.getElementById('memoInput');
    const text = memoInput.value.trim();
    
    console.log('[handleChatAI] Text:', text ? `"${text}"` : '(empty)');
    console.log('[handleChatAI] Has image:', !!currentImageBase64);
    console.log('[handleChatAI] Target ID:', currentTargetId);
    
    // 入力チェック: テキストまたは画像が必須
    if (!text && !currentImageBase64) {
        console.log('[handleChatAI] Early return: no text and no image');
        showToast("テキストまたは画像を入力してください");
        return;
    }
    
    // ターゲット未選択チェック
    if (!currentTargetId) {
        console.log('[handleChatAI] Early return: no target selected');
        showToast("ターゲットを選択してください");
        return;
    }
    
    console.log('[handleChatAI] Validation passed, preparing message');
    updateState('📝', 'メッセージを準備中...', { step: 'preparing' });
    
    // 1. ユーザーメッセージの表示準備
    // テキストと画像（あれば）を組み合わせてチャットバブルに表示します。
    let displayMessage = text;
    if (currentImageBase64) {
        const imgTag = `<br><img src="data:${currentImageMimeType};base64,${currentImageBase64}" style="max-width:100px; border-radius:4px;">`;
        displayMessage = (text ? text + "<br>" : "") + "[画像送信]" + imgTag;
    }
    
    addChatMessage('user', displayMessage);
    
    // AIへのコンテキスト用にはテキストのみを追加（画像は別途送信）
    if (text) chatSession.push({role: 'user', content: text});
    
    // 重要: 送信データを一時変数にコピーしてからステートをクリアする
    // これにより、非同期処理中にユーザーが次の操作を行っても影響を受けません。
    const imageToSend = currentImageBase64;
    const mimeToSend = currentImageMimeType;
    
    console.log('[handleChatAI] Image data copied:', imageToSend ? `${imageToSend.length} chars` : 'null');
    
    // 入力欄とプレビューのクリア
    memoInput.value = '';
    memoInput.dispatchEvent(new Event('input'));
    clearPreviewImage();
    
    // 2. 使用するAIモデルの決定
    // ユーザーが明示的に選択していない場合、画像ありならVisionモデル、なしならテキストモデルを自動選択します。
    const hasImage = !!imageToSend;
    let modelToUse = currentModel;
    if (!modelToUse) {
        modelToUse = hasImage ? defaultMultimodalModel : defaultTextModel;
    }
    
    // UI表示用モデル名の取得
    const modelInfo = availableModels.find(m => m.id === modelToUse);
    const modelDisplay = modelInfo 
        ? `[${modelInfo.provider}] ${modelInfo.name}`
        : (modelToUse || 'Auto');

    // 3. 処理状態の更新 (State Indication)
    updateState('🔄', `AI分析中... (${modelDisplay})`, {
        model: modelToUse,
        hasImage: hasImage,
        autoSelected: !currentModel,
        step: 'analyzing'
    });
    
    try {
        const systemPrompt = currentSystemPrompt || DEFAULT_SYSTEM_PROMPT;
        
        // 「ページを参照」機能: オプションでターゲットの内容をコンテキストに含める
        const referenceToggle = document.getElementById('referencePageToggle');
        let referenceContext = '';
        if (referenceToggle && referenceToggle.checked && currentTargetId) {
            referenceContext = await fetchAndTruncatePageContent(currentTargetId, currentTargetType);
        }

        // ペイロードの構築
        const payload = {
            text: text,
            target_id: currentTargetId,
            system_prompt: systemPrompt,
            session_history: chatSession.slice(0, -1).slice(-10), // 直近10件のみ送信
            reference_context: referenceContext,
            image_data: imageToSend,
            image_mime_type: mimeToSend,
            model: currentModel // 自動選択の場合はnullを送る
        };
        
        updateState('📡', 'サーバーに送信中...', { step: 'uploading' });
        console.log('[handleChatAI] Sending request to /api/chat');
        console.log('[handleChatAI] Payload:', {
            ...payload,
            image_data: payload.image_data ? `(${payload.image_data.length} chars)` : null
        });
        
        // 4. APIリクエスト
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
        
        // コスト情報の更新
        if (data.cost) {
            updateSessionCost(data.cost);
        }
        
        // ステート更新（完了）
        const completedModelInfo = availableModels.find(m => m.id === data.model);
        const completedDisplay = completedModelInfo 
            ? `[${completedModelInfo.provider}] ${completedModelInfo.name}`
            : data.model;
        
        updateState('✅', `Completed (${completedDisplay})`, { 
            usage: data.usage,
            cost: data.cost
        });
        
        // 5. AIメッセージの表示
        if (data.message) {
            const modelInfo = {
                model: data.model,
                usage: data.usage,
                cost: data.cost
            };
            addChatMessage('ai', data.message, null, modelInfo);
            chatSession.push({role: 'assistant', content: data.message});
        }
        
        // 6. 抽出されたプロパティのフォーム反映
        // AIがJSONでプロパティを返した場合、自動的にフォームに入力します。
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

// --- プロパティUI (Dynamic Property Forms) ---

function renderDynamicForm(container, schema) {
    container.innerHTML = '';
    
    // **重要**: 逆順で表示 (Reverse Order)
    // Notionのプロパティは通常、重要なものが最後（または最初）に来る傾向があるため、逆順に表示してUIの見栄えを調整しています。
    const entries = Object.entries(schema).reverse();
    
    for (const [name, prop] of entries) {
        // Notionが自動管理するシステムプロパティは編集不要なのでスキップします。
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
        
        // プロパティタイプに応じた入力フォームの生成
        if (prop.type === 'select' || prop.type === 'multi_select') {
            input = document.createElement('select');
            input.className = 'prop-input';
            input.dataset.key = name;
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
            input.dataset.key = name;
            input.dataset.type = prop.type;
        } else if (prop.type === 'checkbox') {
            input = document.createElement('input');
            input.type = 'checkbox';
            input.className = 'prop-input';
            input.dataset.key = name;
            input.dataset.type = prop.type;
        } else {
            // その他のテキスト系プロパティ (text, title, rich_text, number, url 等)
            input = document.createElement('input');
            input.type = 'text';
            input.className = 'prop-input';
            input.dataset.key = name;
            input.dataset.type = prop.type;
        }
        
        wrapper.appendChild(input);
        container.appendChild(wrapper);
    }
    
    // 過去のデータから動的にタグ候補を追加
    updateDynamicSelectOptions();
}

function updateDynamicSelectOptions() {
    // プレビューデータ（過去の登録データ）がない場合は何もしない
    if (!currentPreviewData || !currentPreviewData.rows) return;
    
    // 全てのselect/multi_select要素を取得
    const selects = document.querySelectorAll('#propertiesForm select');
    
    selects.forEach(select => {
        const propName = select.dataset.key;
        const propType = select.dataset.type;
        
        if (!propName || (propType !== 'select' && propType !== 'multi_select')) return;
        
        // プレビューデータから既存の値を抽出してSetに格納（重複排除）
        const existingValues = new Set();
        currentPreviewData.rows.forEach(row => {
            const value = row[propName];
            if (value && value.trim()) {
                // multi_selectの場合、APIからはカンマ区切り文字列で返ってくることがあるため分割
                if (value.includes(',')) {
                    value.split(',').forEach(v => existingValues.add(v.trim()));
                } else {
                    existingValues.add(value.trim());
                }
            }
        });
        
        // スキーマに既に定義されているオプションも確認
        const schemaOptions = new Set();
        Array.from(select.options).forEach(opt => {
            if (opt.value) schemaOptions.add(opt.value);
        });
        
        // スキーマにはないが、過去データには存在する値（Ad-hocなタグなど）をオプションに追加
        existingValues.forEach(value => {
            if (!schemaOptions.has(value)) {
                const opt = document.createElement('option');
                opt.value = value;
                opt.textContent = value + ' (データから)'; // ユーザーに由来がわかるように表示
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



// --- プレビュー表示関数 (Content Rendering) ---

function renderDatabaseTable(data, container) {
    if (!container) container = document.getElementById('contentModalPreview');
    container.innerHTML = '';
    
    if (!data.columns || data.columns.length === 0) {
        container.innerHTML = '<p class="placeholder-text">(履歴なし)</p>';
        return;
    }
    
    // カラムの並び替え (Column Sorting)
    // "Title" や "Name" などの主要なカラムを左側に表示し、可読性を向上させます。
    const sortedCols = [...data.columns].sort((a, b) => {
        const aLow = a.toLowerCase();
        const bLow = b.toLowerCase();
        if (aLow === 'title' || aLow === 'name') return -1;
        if (bLow === 'title' || bLow === 'name') return 1;
        return 0;
    });

    // 簡易的なHTMLテーブルとしてレンダリング
    let html = '<div class="notion-table-wrapper"><table class="notion-table"><thead><tr>';
    sortedCols.forEach(col => html += `<th>${col}</th>`);
    html += '</tr></thead><tbody>';
    
    // 最新のデータを10件まで表示
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
    
    // Notionのブロックを簡易的なHTML要素に変換して表示
    // 現在はプレーンテキストとして表示していますが、必要に応じてMarkdownレンダリングなどを追加可能です。
    blocks.forEach(block => {
        const div = document.createElement('div');
        div.className = `notion-block notion-${block.type}`;
        div.textContent = block.content;
        container.appendChild(div);
    });
}

// --- ユーティリティ & キャッシュ & サーバー通信 ---

// --- ユーティリティ & キャッシュ & サーバー通信 (Utils & Caching) ---

// レスポンスをローカルストレージにキャッシュするラッパー関数
// 頻繁なAPIコールを防ぎ、UXを改善するために使用します。
async function fetchWithCache(url, key) {
    const cached = localStorage.getItem(key);
    if (cached) {
        try {
            const entry = JSON.parse(cached);
            // 有効期限内であればキャッシュを返す
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
        
        // 新しいデータをキャッシュに保存
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
        // ターゲットリスト取得（キャッシュ有効）
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
    // このオプションが選択された場合、モーダルを表示するロジックが発火します。
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
    
    // 初期選択があれば反映してフォームをレンダリング
    if (selector.value && selector.value !== '__NEW_PAGE__') handleTargetChange(selector.value);
}

// ターゲット変更時のハンドラ
// スキーマ情報の取得とUIの更新を行います。
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
        // スキーマ取得（キャッシュ有効）
        const data = await fetchWithCache(`/api/schema/${targetId}`, SCHEMA_CACHE_PREFIX + targetId);
        currentSchema = data.schema;
        
        // 動的フォームの生成
        renderDynamicForm(formContainer, currentSchema);
        
        // ターゲットタイプに応じたUI制御
        const propsSection = document.getElementById('propertiesSection');
        const propsContainer = document.getElementById('propertiesContainer');
        if (currentTargetType === 'database') {
            // データベースの場合は属性セクションを表示（デフォルトで閉じた状態）
            if (propsContainer) propsContainer.style.display = 'block';
            if (propsSection) propsSection.classList.add('hidden');
        } else {
            // ページの場合は属性セクション全体を非表示
            // ページには構造化されたプロパティがないためです。
            if (propsContainer) propsContainer.style.display = 'none';
        }
        
        // システムプロンプトの初期化
        try {
            // localStorageからカスタムプロンプトを取得
            const promptKey = `${LOCAL_PROMPT_PREFIX}${targetId}`;
            currentSystemPrompt = localStorage.getItem(promptKey) || null;
            
        } catch (e) {
            console.error("Prompt load failed:", e);
            currentSystemPrompt = null;
        }

    } catch(e) {
        console.error('[handleTargetChange Error]', e);
        formContainer.innerHTML = `<p class="error">スキーマ読み込み失敗: ${e.message}</p>`;
        
        // 初心者向けに具体的なエラーメッセージを表示
        let userMessage = "スキーマ読み込みエラー";
        
        if (e.message.includes('Failed to fetch') || e.message.includes('NetworkError')) {
            // サーバーが起動していない、またはネットワーク接続エラー
            userMessage = "❌ サーバーに接続できません。サーバーが起動しているか確認してください";
        } else if (e.message.includes('HTTPエラー 404')) {
            // ページが見つからない
            userMessage = "❌ ページが見つかりません。ページIDが正しいか確認してください";
        } else if (e.message.includes('HTTPエラー 401') || e.message.includes('HTTPエラー 403')) {
            // 認証エラー
            userMessage = "❌ アクセス権限がありません。Notion APIキーとページの共有設定を確認してください";
        } else if (e.message.includes('HTTPエラー 500') || e.message.includes('HTTPエラー 503')) {
            // サーバーエラー
            userMessage = "❌ サーバーでエラーが発生しました。しばらく待ってから再試行してください";
        } else if (e.message.includes('HTTPエラー')) {
            // その他のHTTPエラー
            userMessage = `❌ エラーが発生しました: ${e.message}`;
        }
        
        showToast(userMessage);
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

// --- SystemPrompt編集機能 (System Prompt Management) ---

function openPromptModal() {
    if (!currentTargetId) {
        showToast('ターゲットを選択してください');
        return;
    }
    
    const modal = document.getElementById('promptModal');
    const targetNameSpan = document.getElementById('modalTargetName');
    const textarea = document.getElementById('promptTextarea');
    const saveBtn = document.getElementById('savePromptBtn');
    const resetBtn = document.getElementById('resetPromptBtn');
    
    // ターゲット名を表示
    targetNameSpan.textContent = currentTargetName;
    
    // カスタムプロンプトの有無を確認 (localStorage)
    const promptKey = `${LOCAL_PROMPT_PREFIX}${currentTargetId}`;
    const savedPrompt = localStorage.getItem(promptKey);
    
    // カスタム設定がある場合のみリセットボタンを表示
    if (resetBtn) {
        if (savedPrompt) {
            resetBtn.classList.remove('hidden');
        } else {
            resetBtn.classList.add('hidden');
        }
    }
    
    // 現在のプロンプトまたはデフォルトを表示
    textarea.value = currentSystemPrompt || DEFAULT_SYSTEM_PROMPT;
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
    const resetBtn = document.getElementById('resetPromptBtn');
    const newPrompt = textarea.value.trim();
    
    saveBtn.disabled = true;
    
    try {
        // デフォルトと異なる場合のみlocalStorageに保存
        const promptKey = `${LOCAL_PROMPT_PREFIX}${currentTargetId}`;
        
        if (newPrompt && newPrompt !== DEFAULT_SYSTEM_PROMPT) {
            // カスタムプロンプトを保存
            localStorage.setItem(promptKey, newPrompt);
            currentSystemPrompt = newPrompt;
            
            // リセットボタンを表示
            if (resetBtn) {
                resetBtn.classList.remove('hidden');
            }
        } else {
            // デフォルトと同じならカスタム設定を削除
            localStorage.removeItem(promptKey);
            currentSystemPrompt = null;
            
            // リセットボタンを隠す
            if (resetBtn) {
                resetBtn.classList.add('hidden');
            }
        }
        
        showToast('✅ システムプロンプトを保存しました');
    } catch (e) {
        console.error('Failed to save prompt:', e);
        showToast('❌ 保存に失敗しました');
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = '保存';
    }
}

function resetSystemPrompt() {
    if (!currentTargetId) return;
    
    const promptKey = `${LOCAL_PROMPT_PREFIX}${currentTargetId}`;
    localStorage.removeItem(promptKey); // 設定を削除
    currentSystemPrompt = null;
    
    // テキストエリアをデフォルトに戻す
    const textarea = document.getElementById('promptTextarea');
    if (textarea) {
        textarea.value = DEFAULT_SYSTEM_PROMPT;
    }
    
    // リセットボタンを隠す
    const resetBtn = document.getElementById('resetPromptBtn');
    if (resetBtn) {
        resetBtn.classList.add('hidden');
    }
    
    showToast('✅ デフォルトに戻しました');
}


// イベントリスナー登録
document.addEventListener('DOMContentLoaded', () => {
    // 既存のDOMContentLoadedとは別に実行される
    const editPromptBtn = document.getElementById('editPromptBtn');
    const closeModalBtn = document.getElementById('closeModalBtn');
    const cancelPromptBtn = document.getElementById('cancelPromptBtn');
    const savePromptBtn = document.getElementById('savePromptBtn');
    const resetPromptBtn = document.getElementById('resetPromptBtn');
    const promptModal = document.getElementById('promptModal');

    if (editPromptBtn) editPromptBtn.addEventListener('click', openPromptModal);
    if (closeModalBtn) closeModalBtn.addEventListener('click', closePromptModal);
    if (cancelPromptBtn) cancelPromptBtn.addEventListener('click', closePromptModal);
    if (savePromptBtn) savePromptBtn.addEventListener('click', saveSystemPrompt);
    if (resetPromptBtn) resetPromptBtn.addEventListener('click', resetSystemPrompt);


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

// --- 新規ページ作成機能 (New Page Creation) ---

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
        // APIを呼び出してページを作成
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
        // これにより、新しいページがドロップダウンリストにすぐに表示されます。
        localStorage.removeItem(TARGETS_CACHE_KEY);
        const appSelector = document.getElementById('appSelector');
        await loadTargets(appSelector);
        
        // 新規作成したページを自動選択
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

// --- ページ内容モーダル機能 (Content Viewer) ---

function openContentModal() {
    if (!currentTargetId) {
        showToast('ターゲットを選択してください');
        return;
    }
    
    const modal = document.getElementById('contentModal');
    
    // タイトルをNotionリンクに変更
    // タイトルをクリックすると実際のNotionページが開くようにUXを改善しています。
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
            updateDynamicSelectOptions();  // 取得したデータに基づいてフォームの選択肢を更新
        } else {
            renderPageBlocks(data.blocks, container);
            container.classList.remove('database-view');
        }
    } catch(e) {
        container.innerHTML = '<p class="error">プレビューを取得できませんでした</p>';
    }
}

// --- 新機能: 設定、モデル選択、ステート表示 (New Features) ---

function toggleSettingsMenu() {
    const menu = document.getElementById('settingsMenu');
    menu.classList.toggle('hidden');
}

async function loadAvailableModels() {
    try {
        const res = await fetch('/api/models');
        if (!res.ok) throw new Error('Failed to load models');
        
        const data = await res.json();
        
        // モデルの分類とデフォルト設定
        availableModels = data.all || [];
        textOnlyModels = data.text_only || [];
        visionModels = data.vision_capable || [];
        defaultTextModel = data.defaults?.text;
        defaultMultimodalModel = data.defaults?.multimodal;
        
        // ユーザーの前回の選択を復元（なければ自動選択）
        currentModel = localStorage.getItem('memo_ai_selected_model') || null;
        
        // 保存されていたモデルが現在も有効か確認
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
    
    // 一時変数に現在の設定をコピー（キャンセル機能のため）
    tempSelectedModel = currentModel;
    
    renderModelList();
    modal.classList.remove('hidden');
}

function renderModelList() {
    const modelList = document.getElementById('modelList');
    modelList.innerHTML = '';
    
    // デフォルトモデルの解決
    const textModelInfo = availableModels.find(m => m.id === defaultTextModel);
    const visionModelInfo = availableModels.find(m => m.id === defaultMultimodalModel);
    
    const textDisplay = textModelInfo 
        ? `[${textModelInfo.provider}] ${textModelInfo.name}`
        : (defaultTextModel || 'Unknown');
    const visionDisplay = visionModelInfo 
        ? `[${visionModelInfo.provider}] ${visionModelInfo.name}`
        : (defaultMultimodalModel || 'Unknown');

    // 自動選択オプション (推奨)
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

    // 区切り線
    const separator = document.createElement('div');
    separator.style.borderBottom = '1px solid var(--border-color)';
    separator.style.margin = '8px 0';
    modelList.appendChild(separator);

    // モデル一覧（逆順で表示）
    availableModels.slice().reverse().forEach(model => {
        modelList.appendChild(createModelItem(model));
    });
}

function createModelItem(model) {
    const item = document.createElement('div');
    item.className = 'model-item';
    
    const isSelected = model.id === tempSelectedModel;
    if (isSelected) item.classList.add('selected');
    
    // Vision対応アイコン
    const visionIcon = model.supports_vision ? ' 📷' : '';
    
    // [Provider] モデル名 [📷]
    const displayName = `[${model.provider}] ${model.name}${visionIcon}`;
    
    // レートリミット注意書き
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
    
    // localStorageに保存
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

// --- ステート表示ロジック (State Display Logic) ---
// AI処理の進行状況をアイコンとテキストでユーザーにフィードバックします。
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
    stateDetails.classList.add('hidden'); // デフォルトでは詳細は折りたたむ
    
    // トグルハンドラ
    const toggle = document.getElementById('stateToggle');
    toggle.onclick = (e) => {
        e.stopPropagation();
        stateDetails.classList.toggle('hidden');
    };
}

function updateState(icon, text, details = null) {
    showState(icon, text, details);
    
    // 成功・完了時は数秒後に自動的に非表示にする
    if (icon === '✅') {
        setTimeout(() => {
            document.getElementById('stateDisplay').classList.add('hidden');
        }, 5000);
    }
}
