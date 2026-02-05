// ========== CHAT MODULE ==========
// チャット履歴管理とAI通信機能

// チャットメッセージを追加
export function addChatMessage(type, message, properties = null, modelInfo = null) {
    const entry = {
        type: type,  // 'user' | 'ai' | 'system' | 'stamp'
        message: message,
        properties: properties,
        timestamp: Date.now(),
        modelInfo: modelInfo
    };
    
    window.App.chat.history.push(entry);
    renderChatHistory();
    saveChatHistory();
}

// チャット履歴をレンダリング
export function renderChatHistory() {
    const container = document.getElementById('chatHistory');
    container.innerHTML = '';
    
    console.log('[renderChatHistory] Rendering', window.App.chat.history.length, 'messages');
    
    window.App.chat.history.forEach((entry, index) => {
        console.log(`[renderChatHistory] Message ${index}:`, {
            type: entry.type,
            messageLength: entry.message?.length,
            messagePreview: entry.message?.substring(0, 50),
            hasModelInfo: !!entry.modelInfo
        });
        
        // スタンプタイプは特別な表示（吹き出しなし、大きく表示）
        if (entry.type === 'stamp') {
            const stampDiv = document.createElement('div');
            stampDiv.className = 'chat-stamp';
            stampDiv.textContent = entry.message;
            container.appendChild(stampDiv);
            return; // スタンプの処理はここで終了
        }
        
        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${entry.type}`;
        
        // メッセージ内容
        const processedMessage = entry.message.replace(/\n/g, '<br>');
        console.log(`[renderChatHistory] Processed message ${index}:`, processedMessage.substring(0, 100));
        bubble.innerHTML = processedMessage;
        
        console.log(`[renderChatHistory] Bubble innerHTML ${index}:`, bubble.innerHTML.substring(0, 100));
        
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
                if (window.handleAddFromBubble) window.handleAddFromBubble(entry);
            };
            bubble.appendChild(addBtn);
        }
        
        // AIのモデル情報表示
        if (entry.type === 'ai' && window.App.debug.showModelInfo && entry.modelInfo) {
            const infoDiv = document.createElement('div');
            infoDiv.className = 'model-info-text';
            const { model, usage, cost } = entry.modelInfo;
            
            // Try to find model info to get provider prefix
            const modelInfo = window.App.model.available.find(m => m.id === model);
            const modelDisplay = modelInfo 
                ? `${modelInfo.provider}/${modelInfo.name}`
                : model;
            
            let infoText = modelDisplay;
            if (cost) infoText += ` | $${parseFloat(cost).toFixed(5)}`;
            // usage is object {prompt_tokens, completion_tokens, total_tokens}
            if (usage && usage.total_tokens) {
                // 送信・受信・思考トークンを個別表示
                if (usage.prompt_tokens && usage.completion_tokens) {
                    infoText += ` | S:${usage.prompt_tokens} / R:${usage.completion_tokens}`;
                    
                    // Think トークンがあれば表示（複数の可能性がある位置を確認）
                    let thinkingTokens = null;
                    
                    // Gemini 2.0 thinking models: completion_tokens_details.thinking_tokens
                    if (usage.completion_tokens_details?.thinking_tokens) {
                        thinkingTokens = usage.completion_tokens_details.thinking_tokens;
                    }
                    // OpenAI o1/o3: completion_tokens_details.reasoning_tokens
                    else if (usage.completion_tokens_details?.reasoning_tokens) {
                        thinkingTokens = usage.completion_tokens_details.reasoning_tokens;
                    }
                    // Alternative location: cached_tokens_details.thinking_tokens
                    else if (usage.cached_tokens_details?.thinking_tokens) {
                        thinkingTokens = usage.cached_tokens_details.thinking_tokens;
                    }
                    
                    if (thinkingTokens) {
                        infoText += ` (Think:${thinkingTokens})`;
                    }
                } else {
                    infoText += ` | Tokens: ${usage.total_tokens}`;
                }
            }
            
            infoDiv.textContent = infoText;
            bubble.appendChild(infoDiv);
        }
        
        container.appendChild(bubble);
    });
    
    // 最下部にスクロール
    container.scrollTop = container.scrollHeight;
}

// チャット履歴を保存
export function saveChatHistory() {
    // 最新50件のみ保存
    localStorage.setItem(window.App.cache.KEYS.CHAT_HISTORY, JSON.stringify(window.App.chat.history.slice(-50)));
}

// チャット履歴を読み込み
export function loadChatHistory() {
    const saved = localStorage.getItem(window.App.cache.KEYS.CHAT_HISTORY);
    if (saved) {
        try {
            window.App.chat.history = JSON.parse(saved);
            renderChatHistory();
            
            // Rebuild App.chat.session for API context
            window.App.chat.session = window.App.chat.history
                .filter(entry => ['user', 'ai'].includes(entry.type))
                .map(entry => {
                    let content = entry.message;
                    
                    // 画像タグを削除して、テキストと[画像送信]のみを保持
                    // 例: "テキスト<br>[画像送信]<img...>" -> "テキスト [画像送信]"
                    content = content.replace(/<img[^>]*>/g, ''); // imgタグを削除
                    content = content.replace(/<br>/g, ' '); // <br>をスペースに置換
                    content = content.trim(); // 余分な空白を削除
                    
                    return {
                        role: entry.type === 'user' ? 'user' : 'assistant',
                        content: content
                    };
                });
            
        } catch(e) {
            console.error("History parse error", e);
        }
    }
}

// スタンプ（絵文字）を即座に送信してAI応答を取得
export async function sendStamp(emoji) {
    const showToast = window.showToast;
    const recordApiCall = window.recordApiCall;
    const fetchAndTruncatePageContent = window.fetchAndTruncatePageContent;
    
    if (!window.App.target.id) {
        showToast("ターゲットを選択してください");
        return;
    }
    
    // スタンプとしてチャットに追加（大きく表示）
    addChatMessage('stamp', emoji);
    
    // 入力欄をクリア（念のため）
    const memoInput = document.getElementById('memoInput');
    if (memoInput) memoInput.value = '';
    
    // AIタイピングインジケーター表示
    showAITypingIndicator();
    
    try {
        // リファレンスページの取得
        let referenceContext = null;
        const referenceToggle = document.getElementById('referencePageToggle');
        if (referenceToggle?.checked && window.App.target.id) {
            referenceContext = await fetchAndTruncatePageContent(window.App.target.id, window.App.target.type);
        }
        
        // APIリクエスト
        const requestBody = {
            text: emoji,
            target_id: window.App.target.id,
            system_prompt: window.App.target.systemPrompt || window.App.defaultPrompt,
            session_history: window.App.chat.session.slice(-10),
            reference_context: referenceContext,
            model: window.App.model.current
        };
        
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        hideAITypingIndicator();
        
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail?.message || err.detail || `HTTP ${res.status}`);
        }
        
        const data = await res.json();
        recordApiCall('/api/chat', 'POST', requestBody, data, null, res.status);
        
        // セッション履歴を更新
        window.App.chat.session.push({ role: 'user', content: emoji });
        window.App.chat.session.push({ role: 'assistant', content: data.message });
        
        // AI応答を表示
        const modelInfo = {
            model: data.model,
            usage: data.usage,
            cost: data.cost
        };
        addChatMessage('ai', data.message, null, modelInfo);
        
        // コスト累計
        if (data.cost) window.App.model.sessionCost += data.cost;
        
    } catch (err) {
        hideAITypingIndicator();
        console.error('[sendStamp] Error:', err);
        addChatMessage('ai', `❌ エラー: ${err.message}`);
        recordApiCall('/api/chat', 'POST', { text: emoji }, null, err.message, null);
    }
}

// AI応答待ちインジケーターを表示
export function showAITypingIndicator() {
    const chatHistory = document.getElementById('chatHistory');
    if (!chatHistory) return;
    
    // 既存のインジケーターがあれば削除
    const existing = chatHistory.querySelector('.ai-typing-indicator');
    if (existing) existing.remove();
    
    // 新しいインジケーターを作成
    const indicator = document.createElement('div');
    indicator.className = 'chat-bubble ai ai-typing-indicator';
    indicator.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
    chatHistory.appendChild(indicator);
    
    // 最下部にスクロール
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

// AI応答待ちインジケーターを非表示
export function hideAITypingIndicator() {
    const chatHistory = document.getElementById('chatHistory');
    if (!chatHistory) return;
    
    const indicator = chatHistory.querySelector('.ai-typing-indicator');
    if (indicator) indicator.remove();
}

export function handleAddFromBubble(entry) {
    const showToast = window.showToast;
    
    if (!entry || !entry.message) return;
    
    if (!window.App.target.id) {
        showToast('保存先のターゲットを選択してください');
        return;
    }
    
    // 入力欄にセット
    const memoInput = document.getElementById('memoInput');
    memoInput.value = entry.message;
    
    // フォームにフォーカス
    memoInput.focus();
    
    // 自動スクロール
    memoInput.scrollIntoView({ behavior: 'smooth' });
    
    showToast('入力欄にコピーしました。保存ボタンでNotionに追加できます。');
}

/**
 * メインのチャットAI送信処理
 */
export async function handleChatAI(inputText = null) {
    const showToast = window.showToast;
    const recordApiCall = window.recordApiCall;
    const updateState = window.updateState;
    const fetchAndTruncatePageContent = window.fetchAndTruncatePageContent;
    const clearPreviewImage = window.clearPreviewImage;
    const updateSessionCost = window.updateSessionCost || ((cost) => { if (cost) window.App.model.sessionCost += cost; });
    
    const memoInput = document.getElementById('memoInput');
    const text = inputText !== null ? inputText : memoInput.value.trim();
    
    // 入力チェック: テキストまたは画像が必須
    if (!text && !window.App.image.base64) {
        showToast("テキストまたは画像を入力してください");
        return;
    }
    
    // ターゲット未選択チェック
    if (!window.App.target.id) {
        showToast("ターゲットを選択してください");
        return;
    }
    updateState('📝', 'メッセージを準備中...', { step: 'preparing' });
    
    // 1. ユーザーメッセージの表示準備
    let displayMessage = text;
    if (window.App.image.base64) {
        const imgTag = `<br><img src="data:${window.App.image.mimeType};base64,${window.App.image.base64}" style="max-width:100px; border-radius:4px;">`;
        displayMessage = (text ? text + "<br>" : "") + "[画像送信]" + imgTag;
    }
    
    addChatMessage('user', displayMessage);
    
    // 重要: 送信データを一時変数にコピーしてからステートをクリアする
    const imageToSend = window.App.image.base64;
    const mimeToSend = window.App.image.mimeType;
    
    // 2. 会話履歴の準備
    const historyToSend = window.App.chat.session.slice(-10);
    
    // 3. AIへのコンテキスト用にメッセージを追加
    let contextMessage = text || '';
    if (imageToSend) {
        contextMessage = contextMessage ? `${contextMessage} [画像送信]` : '[画像送信]';
    }
    if (contextMessage) {
        window.App.chat.session.push({role: 'user', content: contextMessage});
    }
    
    // 入力欄とプレビューのクリア
    memoInput.value = '';
    memoInput.dispatchEvent(new Event('input'));
    clearPreviewImage();
    
    // 4. 使用するAIモデルの決定
    const hasImage = !!imageToSend;
    let modelToUse = window.App.model.current;
    if (!modelToUse) {
        modelToUse = hasImage ? window.App.model.defaultMultimodal : window.App.model.defaultText;
    }
    
    // UI表示用モデル名の取得
    const modelInfo = window.App.model.available.find(m => m.id === modelToUse);
    const modelDisplay = modelInfo 
        ? `[${modelInfo.provider}] ${modelInfo.name}`
        : (modelToUse || 'Auto');

    // 5. 処理状態の更新
    updateState('🔄', `AI分析中... (${modelDisplay})`, {
        model: modelToUse,
        hasImage: hasImage,
        autoSelected: !window.App.model.current,
        step: 'analyzing'
    });
    
    try {
        const systemPrompt = window.App.target.systemPrompt || window.App.defaultPrompt;
        
        // 「ページを参照」機能
        const referenceToggle = document.getElementById('referencePageToggle');
        let referenceContext = '';
        if (referenceToggle && referenceToggle.checked && window.App.target.id) {
            referenceContext = await fetchAndTruncatePageContent(window.App.target.id, window.App.target.type);
        }

        // ペイロードの構築
        const payload = {
            text: text,
            target_id: window.App.target.id,
            system_prompt: systemPrompt,
            session_history: historyToSend,
            reference_context: referenceContext,
            image_data: imageToSend,
            image_mime_type: mimeToSend,
            model: window.App.model.current
        };
        
        updateState('📡', 'サーバーに送信中...', { step: 'uploading' });
        showAITypingIndicator();
        
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        updateState('📥', 'レスポンスを処理中...', { step: 'processing_response' });
        
        if (!res.ok) {
            const errorData = await res.json().catch(() => ({ detail: "解析中にエラーが発生しました" }));
            recordApiCall('/api/chat', 'POST', payload, errorData, errorData.detail?.message || JSON.stringify(errorData), res.status);
            throw new Error(errorData.detail?.message || JSON.stringify(errorData));
        }
        
        const data = await res.json();
        
        // API通信履歴に記録
        recordApiCall('/api/chat', 'POST', payload, data, null, res.status);
        
        // AI応答受信後、インジケーターを非表示
        hideAITypingIndicator();
        
        // コスト情報の更新
        if (data.cost) {
            updateSessionCost(data.cost);
        }
        
        // ステート更新（完了）
        const completedModelInfo = window.App.model.available.find(m => m.id === data.model);
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
            window.App.chat.session.push({role: 'assistant', content: data.message});
        } else {
            console.warn('[handleChatAI] data.message is falsy');
            const warningMsg = `⚠️ AIからの応答メッセージが空でした（model: ${data.model || 'unknown'}）`;
            addChatMessage('system', warningMsg);
        }
        
        // 6. 抽出されたプロパティのフォーム反映
        if (data.properties && window.fillForm) {
            window.fillForm(data.properties);
        }
        
    } catch(e) {
        console.error('[handleChatAI] Error:', e);
        hideAITypingIndicator();
        
        recordApiCall('/api/chat', 'POST', { text: text, target_id: window.App.target.id }, null, e.message, null);
        
        updateState('❌', 'Error', { error: e.message });
        addChatMessage('system', "エラー: " + e.message);
        showToast("エラー: " + e.message);
    }
}

