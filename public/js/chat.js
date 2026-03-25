// ========== CHAT MODULE ==========
// チャット履歴管理とAI通信機能

/**
 * モデルIDから表示用の名前を取得
 * @param {string} modelId - モデルID
 * @param {string} [fallback] - モデルが見つからない場合のフォールバック
 * @returns {string} "[provider] name" 形式の表示名
 */
function getModelDisplayName(modelId, fallback = null) {
    const info = window.App.model.available.find(m => m.id === modelId);
    return info ? `[${info.provider}] ${info.name}` : (fallback || modelId || 'Auto');
}

/**
 * Notion API形式のプロパティ値から表示用テキストを汎用的に抽出する
 * @param {any} val - Notion API形式のプロパティ値
 * @returns {string} 表示用テキスト
 */
function extractDisplayValue(val) {
    if (val == null) return '';
    if (typeof val === 'string') return val;
    if (typeof val === 'number' || typeof val === 'boolean') return String(val);

    // Notion API形式の各タイプに対応
    if (val.title) return val.title.map(t => t?.text?.content || t?.plain_text || '').join('');
    if (val.rich_text) return val.rich_text.map(t => t?.text?.content || t?.plain_text || '').join('');
    if (val.select) return val.select?.name || '';
    if (val.multi_select) return val.multi_select.map(o => o?.name || '').join(', ');
    if (val.date) return val.date?.start || '';
    if (val.checkbox !== undefined) return val.checkbox ? '✅' : '☐';
    if (val.number !== undefined) return String(val.number);
    if (val.url) return val.url;
    if (val.email) return val.email;
    if (val.status) return val.status?.name || '';

    return JSON.stringify(val);
}

// チャットメッセージを追加
/**
 * @param {'user' | 'ai' | 'system' | 'stamp'} type
 * @param {string} message
 * @param {Record<string, any> | null} properties
 * @param {ModelInfo | null} modelInfo
 */
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



    window.App.chat.history.forEach((entry, index) => {


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

        bubble.innerHTML = processedMessage;



        // AIメッセージにプロパティカードを表示
        if (entry.type === 'ai' && entry.properties && Object.keys(entry.properties).length > 0) {
            const propsCard = document.createElement('div');
            propsCard.className = 'props-card';

            for (const [key, val] of Object.entries(entry.properties)) {
                const row = document.createElement('div');
                row.className = 'props-card-row';

                const label = document.createElement('span');
                label.className = 'props-card-key';
                label.textContent = key;

                const value = document.createElement('span');
                value.className = 'props-card-val';
                value.textContent = extractDisplayValue(val);

                row.appendChild(label);
                row.appendChild(value);
                propsCard.appendChild(row);
            }

            bubble.appendChild(propsCard);
        }

        // AI画像関連の表示（propertiesの有無に関係なく動作）
        if (entry.type === 'ai') {
            const metadata = entry.modelInfo?.metadata;

            // 画像抽出プロパティのカードUIレンダリング
            if (metadata?.image_properties) {
                const card = document.createElement('div');
                card.className = 'image-properties-card';

                const props = metadata.image_properties;

                if (props.title || props.content) {
                    let cardContent = '<div class="properties-container">';

                    if (props.title) {
                        cardContent += `<div class="property-item"><strong>タイトル:</strong> ${props.title}</div>`;
                    }

                    if (props.content) {
                        cardContent += `<div class="property-item"><strong>内容:</strong> ${props.content}</div>`;
                    }

                    cardContent += '</div>';
                    card.innerHTML = cardContent;
                    bubble.appendChild(card);
                }
            }

            // AI生成画像の表示
            if (metadata?.image_base64) {
                const imgContainer = document.createElement('div');
                imgContainer.className = 'generated-image-container';

                const img = document.createElement('img');
                img.src = `data:image/png;base64,${metadata.image_base64}`;
                img.alt = 'AI生成画像';
                img.className = 'generated-image';

                imgContainer.appendChild(img);
                bubble.appendChild(imgContainer);
            }
        }

        // ユーザーまたはAIメッセージにホバーボタンを追加
        if (entry.type === 'user' || entry.type === 'ai') {
            // Tap to show "Add to Notion"
            bubble.style.cursor = 'pointer';
            bubble.onclick = (e) => {
                // Don't toggle if selecting text
                if (window.getSelection().toString().length > 0) return;

                // Don't toggle if clicking a link/button inside (except this bubble's container)
                if (/** @type {HTMLElement} */(e.target).tagName === 'A') return;

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
            const modelDisplay = getModelDisplayName(model);

            let infoText = modelDisplay;
            if (cost) infoText += ` | $${Number(cost).toFixed(5)}`;
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

                    // 画像タグを削除
                    content = content.replace(/<img[^>]*>/g, ''); // imgタグを削除
                    content = content.replace(/<br>/g, ' '); // <br>をスペースに置換
                    content = content.trim(); // 余分な空白を削除

                    return {
                        role: entry.type === 'user' ? 'user' : 'assistant',
                        content: content
                    };
                })
                .filter(item => item.content.length > 0);

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
    if (memoInput) /** @type {HTMLInputElement} */(memoInput).value = '';

    // AIタイピングインジケーター表示
    showAITypingIndicator();

    try {
        // リファレンスページの取得
        let referenceContext = null;
        const referenceToggle = document.getElementById('referencePageToggle');
        if (/** @type {HTMLInputElement} */(referenceToggle)?.checked && window.App.target.id) {
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

        /** @type {ChatApiResponse} */
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
        const errorMessage = /** @type {Error} */(err).message;
        addChatMessage('ai', `❌ エラー: ${errorMessage}`);
        recordApiCall('/api/chat', 'POST', { text: emoji }, null, errorMessage, null);
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

export async function handleAddFromBubble(entry) {
    const showToast = window.showToast;
    const setLoading = window.setLoading;
    const recordApiCall = window.recordApiCall;

    console.log('[handleAddFromBubble] Called with entry:', entry);
    console.log('[handleAddFromBubble] Current target:', window.App?.target);

    if (!entry || !entry.message) {
        console.warn('[handleAddFromBubble] No entry or message');
        return;
    }

    if (!window.App.target.id) {
        console.error('[handleAddFromBubble] No target selected. Target state:', window.App?.target);
        showToast('保存先のターゲットを選択してください');
        return;
    }

    console.log('[handleAddFromBubble] Target type:', window.App.target.type);
    console.log('[handleAddFromBubble] Target ID:', window.App.target.id);

    // Clean HTML tags from message content
    const content = entry.message
        .replace(/<br>/g, '\n')
        .replace(/整形案:\n/, '')
        .replace(/<img[^>]*>/g, '')  // Remove image tags
        .trim();

    if (!content) {
        showToast('保存する内容がありません');
        return;
    }

    setLoading(true, '保存中...');

    try {
        // Build properties for database type
        const properties = {};

        if (window.App.target.type === 'database') {
            // Database: AI抽出プロパティがあればベースとして使用
            Object.assign(properties, entry.properties || {});
            const inputs = document.querySelectorAll('#propertiesForm .prop-input');

            // Collect properties from form inputs
            inputs.forEach(/** @param {Element} el */ el => {
                const input = /** @type {HTMLElement} */(el);
                const key = input.dataset?.key;
                const type = input.dataset?.type;

                if (type === 'rich_text') {
                    // Use form value if exists, otherwise bubble content
                    const val = /** @type {HTMLInputElement} */(input).value || content;
                    properties[key] = { rich_text: [{ text: { content: val } }] };
                } else if (type === 'select' || type === 'status') {
                    // status uses the same structure as select
                    const selectVal = /** @type {HTMLSelectElement} */(input).value;
                    if (selectVal) {
                        const propType = type === 'status' ? 'status' : 'select';
                        properties[key] = { [propType]: { name: selectVal } };
                    }
                } else if (type === 'multi_select') {
                    // UIでは単一選択として扱うが、Notionには配列として送る
                    const selectVal = /** @type {HTMLSelectElement} */(input).value;
                    if (selectVal) {
                        properties[key] = { multi_select: [{ name: selectVal }] };
                    }
                } else if (type === 'date') {
                    const dateVal = /** @type {HTMLInputElement} */(input).value;
                    if (dateVal) properties[key] = { date: { start: dateVal } };
                } else if (type === 'checkbox') {
                    properties[key] = { checkbox: /** @type {HTMLInputElement} */(input).checked };
                } else if (type === 'url') {
                    const urlVal = /** @type {HTMLInputElement} */(input).value;
                    if (urlVal) properties[key] = { url: urlVal };
                } else if (type === 'email') {
                    const emailVal = /** @type {HTMLInputElement} */(input).value;
                    if (emailVal) properties[key] = { email: emailVal };
                } else if (type === 'number') {
                    const numVal = /** @type {HTMLInputElement} */(input).value;
                    if (numVal) properties[key] = { number: Number(numVal) };
                }
            });

            // IMPORTANT: Always set the title property from schema
            // Title properties are not shown in the form (skipped in renderDynamicForm),
            // so we need to find and populate them from the schema
            if (window.App.target.schema) {
                for (const [key, prop] of Object.entries(window.App.target.schema)) {
                    if (prop.type === 'title') {
                        // Use bubble content for title (truncated to 100 chars to fit Notion limits)
                        properties[key] = { title: [{ text: { content: content.substring(0, 100) } }] };
                        break; // Only one title property per database
                    }
                }
            }
        }

        // Build payload for both database and page types
        const payload = {
            target_db_id: window.App.target.id,
            target_type: window.App.target.type === 'database' ? 'database' : 'page',
            text: content,
            properties: window.App.target.type === 'database' ? properties : {}
        };

        console.log('[handleAddFromBubble] Payload prepared:', payload);
        console.log('[handleAddFromBubble] Calling /api/save...');

        // Single unified fetch for both database and page
        const res = await fetch('/api/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });

        console.log('[handleAddFromBubble] Response status:', res.status);

        const data = await res.json().catch(() => ({}));
        recordApiCall('/api/save', 'POST', payload, data,
                     res.ok ? null : (data.detail || '保存に失敗しました'),
                     res.status);

        if (!res.ok) throw new Error(data.detail || '保存に失敗しました');

        showToast('✅ Notionに追加しました');

    } catch(e) {
        console.error('[handleAddFromBubble] Error caught:', e);
        console.error('[handleAddFromBubble] Error stack:', /** @type {Error} */(e).stack);
        const errorMessage = /** @type {Error} */(e).message;
        showToast('❌ 保存エラー: ' + errorMessage);
        // Record error for debugging
        if (recordApiCall) {
            recordApiCall('/api/save', 'POST', {}, null, errorMessage, null);
        }
    } finally {
        setLoading(false);
    }
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
    const updateSessionCost = /** @type {any} */(window).updateSessionCost || ((cost) => { if (cost) window.App.model.sessionCost += cost; });

    const memoInput = document.getElementById('memoInput');
    const text = inputText !== null ? inputText : /** @type {HTMLInputElement} */(memoInput).value.trim();


    // 入力チェック: テキストまたは画像が必須
    if (!text && !window.App.image.data) {
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
    if (window.App.image.data) {
        const imgTag = `<br><img src="data:${window.App.image.mimeType};base64,${window.App.image.data}" style="max-width:100px; border-radius:4px;">`;
        displayMessage = (text ? text + "<br>" : "") + imgTag;
    }

    addChatMessage('user', displayMessage);

    // 重要: 送信データを一時変数にコピーしてからステートをクリアする
    const imageToSend = window.App.image.data;
    const mimeToSend = window.App.image.mimeType;
    const isImageGeneration = window.App.image.generationMode || false;

    // 2. 会話履歴の準備
    const historyToSend = window.App.chat.session.slice(-10);

    // 3. AIへのコンテキスト用にメッセージを追加（画像送信時もマーカーを残す）
    const contextMessage = text || (imageToSend ? '[画像を送信しました]' : '');
    if (contextMessage) {
        window.App.chat.session.push({role: 'user', content: contextMessage});
    }

    // 入力欄とプレビューのクリア
    /** @type {HTMLInputElement} */(memoInput).value = '';
    memoInput.dispatchEvent(new Event('input'));
    clearPreviewImage();

    // 画像生成モードをクリア（タグを消す）
    const disableImageGenMode = window.disableImageGenMode;
    if (disableImageGenMode) {
        disableImageGenMode();
    }


    // 4. 使用するAIモデルの決定
    const hasImage = !!imageToSend;
    let modelToUse = window.App.model.current;
    if (!modelToUse) {
        modelToUse = hasImage ? window.App.model.defaultMultimodal : window.App.model.defaultText;
    }

    // UI表示用モデル名の取得
    const modelDisplay = getModelDisplayName(modelToUse, 'Auto');

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
        if (referenceToggle && /** @type {HTMLInputElement} */(referenceToggle).checked && window.App.target.id) {
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
            model: window.App.model.current,
            image_generation: isImageGeneration
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

        /** @type {ChatApiResponse} */
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
        const completedDisplay = getModelDisplayName(data.model);

        updateState('✅', `Completed (${completedDisplay})`, {
            usage: data.usage,
            cost: data.cost
        });

        // 5. AIメッセージの表示（画像生成時はmessageが空でもimage_base64があればOK）
        if (data.message || data.image_base64) {
            const displayMessage = data.message || '';
            const modelInfo = {
                model: data.model,
                usage: data.usage,
                cost: data.cost,
                metadata: {
                    image_base64: data.image_base64 || null,
                    image_properties: data.metadata?.image_properties || null
                }
            };
            addChatMessage('ai', displayMessage, data.properties || null, modelInfo);
            // プロパティ情報をセッション履歴に含めて後続会話で参照可能にする
            let sessionContent = displayMessage;
            if (data.properties) {
                const propSummary = Object.entries(data.properties)
                    .map(([k, v]) => {
                        if (v?.title) return `${k}: ${v.title[0]?.text?.content || ''}`;
                        if (v?.rich_text) return `${k}: ${v.rich_text[0]?.text?.content || ''}`;
                        if (v?.select) return `${k}: ${v.select.name}`;
                        if (v?.multi_select) return `${k}: ${v.multi_select.map(o => o.name).join(', ')}`;
                        return `${k}: ${JSON.stringify(v)}`;
                    })
                    .join(' / ');
                sessionContent += `\n[抽出データ: ${propSummary}]`;
            }
            if (sessionContent) {
                window.App.chat.session.push({role: 'assistant', content: sessionContent});
            }
        } else {
            console.warn('[handleChatAI] data.message and image_base64 are both falsy');
            const warningMsg = `⚠️ AIからの応答が空でした（model: ${data.model || 'unknown'}）`;
            addChatMessage('system', warningMsg);
        }

        // 6. 抽出されたプロパティのフォーム反映
        if (data.properties && window.fillForm) {
            window.fillForm(data.properties);
        }

    } catch(e) {
        console.error('[handleChatAI] Error:', e);
        hideAITypingIndicator();
        const errorMessage = /** @type {Error} */(e).message;

        recordApiCall('/api/chat', 'POST', { text: text, target_id: window.App.target.id }, null, errorMessage, null);

        updateState('❌', 'Error', { error: errorMessage });
        addChatMessage('system', "エラー: " + errorMessage);
        showToast("エラー: " + errorMessage);
    }
}
