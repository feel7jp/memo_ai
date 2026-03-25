// ========== MODEL MODULE ==========
// モデル選択UI機能

// モデル一覧を取得
export async function loadAvailableModels() {
    const showToast = window.showToast;

    try {
        // 全モデルを取得（推奨・非推奨の両方）
        const res = await fetch('/api/models?all=true');
        if (!res.ok) {
            window.recordApiCall('/api/models?all=true', 'GET', null, null, 'Failed to load models', res.status);
            throw new Error('Failed to load models');
        }

        /** @type {ModelsApiResponse} */
        const data = await res.json();
        window.recordApiCall('/api/models?all=true', 'GET', null, data, null, res.status);

        // 全モデルを保存
        window.App.model.allModels = data.all || [];

        // 推奨モデルのみをフィルタリング（デフォルト表示用）
        window.App.model.available = window.App.model.allModels.filter(m => m.recommended !== false);

        // その他の設定
        window.App.model.textOnly = data.text_only || [];
        window.App.model.vision = data.vision_capable || [];
        window.App.model.defaultText = data.default_text_model;
        window.App.model.defaultMultimodal = data.default_multimodal_model;
        // 利用可否情報の保存
        window.App.model.textAvailability = data.text_availability;
        window.App.model.multimodalAvailability = data.multimodal_availability;
        window.App.model.imageGenerationAvailability = data.image_generation_availability;

        window.App.model.showAllModels = false;  // デフォルトは推奨のみ表示

        console.log(`Loaded ${window.App.model.available.length} recommended models, ${window.App.model.allModels.length} total models`);

        // デフォルトモデルの警告チェック
        if (data.warnings && data.warnings.length > 0) {
            data.warnings.forEach(warning => {
                console.warn(`[MODEL WARNING] ${warning.message}`);
                // UIに警告トーストを表示
                showToast(warning.message);
            });
        }

        // ユーザーの前回の選択を復元（なければ自動選択）
        window.App.model.current = localStorage.getItem('memo_ai_selected_model') || null;

        // 保存されていたモデルが現在も有効か確認（推奨か全モデルのいずれかにあればOK）
        if (window.App.model.current) {
            const isValid = window.App.model.available.some(m => m.id === window.App.model.current);
            if (!isValid) {
                console.warn(`Stored model '${window.App.model.current}' is no longer available. Resetting to Auto.`);
                window.App.model.current = null;
                localStorage.removeItem('memo_ai_selected_model');
                showToast('保存されたモデルが無効なため、自動選択にリセットしました');
            }
        }


    } catch (err) {
        console.error('Failed to load models:', err);
        showToast('モデルリストの読み込みに失敗しました');
    }
}

// モデル選択モーダルを開く
export function openModelModal() {
    const modal = document.getElementById('modelModal');

    // 一時変数に現在の設定をコピー（キャンセル機能のため）
    window.App.model.tempSelected = window.App.model.current;

    renderModelList();
    modal.classList.remove('hidden');
}

// モデルリストをレンダリング
export function renderModelList() {
    const modelList = document.getElementById('modelList');
    modelList.innerHTML = '';

    // モデルリストがまだ取得されていない場合はローディング表示
    if (window.App.model.available.length === 0 && !window.App.model.allModels?.length) {
        modelList.innerHTML = `
            <div style="text-align: center; padding: 40px 20px; color: #666;">
                <div class="spinner" style="margin: 0 auto 16px;"></div>
                <p>モデル一覧を取得中...</p>
            </div>
        `;
        // 再取得を試みる
        loadAvailableModels().then(() => {
            // 取得完了後に再描画（モーダルが開いている場合のみ）
            if (!document.getElementById('modelModal').classList.contains('hidden')) {
                renderModelList();
            }
        });
        return;
    }

    // デフォルトモデルの解決
    const textModelInfo = window.App.model.available.find(m => m.id === window.App.model.defaultText);
    const visionModelInfo = window.App.model.available.find(m => m.id === window.App.model.defaultMultimodal);

    const textDisplay = textModelInfo
        ? `[${textModelInfo.provider}] ${textModelInfo.name}`
        : (window.App.model.defaultText || 'Unknown');
    const visionDisplay = visionModelInfo
        ? `[${visionModelInfo.provider}] ${visionModelInfo.name}`
        : (window.App.model.defaultMultimodal || 'Unknown');

    // デフォルトモデル利用不可の警告（詳細理由付き）
    const textWarning = window.App.model.textAvailability?.available === false
        ? ` <span title="${window.App.model.textAvailability.error}" style="color:#ff9800; cursor:help;">⚠️ ${window.App.model.textAvailability.error}</span>`
        : (!textModelInfo ? ' ⚠️' : '');

    const visionWarning = window.App.model.multimodalAvailability?.available === false
        ? ` <span title="${window.App.model.multimodalAvailability.error}" style="color:#ff9800; cursor:help;">⚠️ ${window.App.model.multimodalAvailability.error}</span>`
        : (!visionModelInfo ? ' ⚠️' : '');

    // 画像生成モデルの表示
    const imageGenAvailability = window.App.model.imageGenerationAvailability;
    const imageGenDisplay = imageGenAvailability?.available === true
        ? imageGenAvailability.model.split('/').pop()  // "gemini/gemini-2.5-flash-image" -> "gemini-2.5-flash-image"
        : 'Unknown';
    const imageGenWarning = imageGenAvailability?.available === false
        ? ` <span title="${imageGenAvailability.error}" style="color:#ff9800; cursor:help;">⚠️ ${imageGenAvailability.error}</span>`
        : (!imageGenAvailability?.available ? ' ⚠️' : '');

    // 表示モードトグル（推奨のみ / 全モデル）
    const toggleContainer = document.createElement('div');
    toggleContainer.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: #f0f0f0; border-radius: 8px; margin-bottom: 8px;';

    const toggleLabel = document.createElement('span');
    toggleLabel.style.cssText = 'font-size: 0.85em; color: #666;';
    toggleLabel.textContent = window.App.model.showAllModels
        ? `全モデル表示中 (${window.App.model.allModels?.length || 0}件)`
        : `推奨モデル表示中 (${window.App.model.available.length}件)`;

    const toggleBtn = document.createElement('button');
    toggleBtn.style.cssText = 'padding: 4px 12px; font-size: 0.8em; border: 1px solid #ccc; border-radius: 16px; background: white; cursor: pointer;';
    toggleBtn.textContent = window.App.model.showAllModels ? '推奨のみに戻す' : '全モデルを表示';
    toggleBtn.onclick = (e) => {
        e.stopPropagation();
        window.App.model.showAllModels = !window.App.model.showAllModels;
        renderModelList();
    };

    toggleContainer.appendChild(toggleLabel);
    toggleContainer.appendChild(toggleBtn);
    modelList.appendChild(toggleContainer);

    // 自動選択オプション (推奨)
    const autoItem = document.createElement('div');
    autoItem.className = 'model-item';
    if (window.App.model.tempSelected === null) autoItem.classList.add('selected');
    autoItem.innerHTML = `
        <div class="model-info">
            <div class="model-name">✨ 自動選択 (推奨)</div>
            <div class="model-provider" style="display: flex; flex-direction: column; gap: 4px; margin-top: 4px;">
                <div style="font-size: 0.9em;">📝 テキスト: <span style="font-weight: 500;">${textDisplay}${textWarning}</span></div>
                <div style="font-size: 0.9em;">🖼️ 画像読み込み: <span style="font-weight: 500;">${visionDisplay}${visionWarning}</span></div>
                <div style="font-size: 0.9em;">🎨 画像生成: <span style="font-weight: 500;">${imageGenDisplay}${imageGenWarning}</span></div>
            </div>
        </div>
        <span class="model-check">${window.App.model.tempSelected === null ? '✓' : ''}</span>
    `;

    autoItem.onclick = () => selectTempModel(null);
    modelList.appendChild(autoItem);

    // 区切り線
    const separator = document.createElement('div');
    separator.style.borderBottom = '1px solid var(--border-color)';
    separator.style.margin = '8px 0';
    modelList.appendChild(separator);

    // 表示するモデルリストを選択
    const modelsToShow = window.App.model.showAllModels
        ? (window.App.model.allModels || [])
        : window.App.model.available;

    // プロバイダー別にグループ化
    const grouped = {};
    modelsToShow.forEach(model => {
        const provider = model.provider || 'Other';
        if (!grouped[provider]) grouped[provider] = [];
        grouped[provider].push(model);
    });

    // プロバイダーごとにセクション作成（ソート順に表示）
    Object.keys(grouped).sort().forEach(provider => {
        // ヘッダー追加
        const header = document.createElement('div');
        header.className = 'model-group-header';
        header.textContent = provider;
        modelList.appendChild(header);

        // モデル追加（名前順にソート）
        grouped[provider].sort((a, b) => a.name.localeCompare(b.name)).forEach(model => {
            modelList.appendChild(createModelItem(model));
        });
    });
}

// 個別モデルアイテムの作成
export function createModelItem(model) {
    const item = document.createElement('div');
    item.className = 'model-item';

    const isSelected = model.id === window.App.model.tempSelected;
    if (isSelected) item.classList.add('selected');

    // 非推奨モデルのスタイル
    const isNotRecommended = model.recommended === false;
    if (isNotRecommended) {
        item.classList.add('not-recommended');
    }

    // Vision対応アイコン
    const visionIcon = model.supports_vision ? ' 📷' : '';
    const imageGenIcon = model.supports_image_generation ? ' 🎨' : '';

    // [Provider] モデル名 [📷] [🎨]
    const displayName = `[${model.provider}] ${model.name}${visionIcon}${imageGenIcon}`;

    // 非推奨バッジ（model_typeがあれば表示）
    const notRecommendedBadge = isNotRecommended && model.model_type
        ? `<div class="model-badge not-recommended">⚠️ 非推奨 (${model.model_type})</div>`
        : '';

    // レートリミット注意書き
    const rateLimitBadge = model.rate_limit_note
        ? `<div class="model-badge warning">⚠️ ${model.rate_limit_note}</div>`
        : '';

    // トークン単価表示（データがある場合のみ）
    let pricingText = '';
    if (model.cost_per_1k_tokens) {
        const inputCost = model.cost_per_1k_tokens.input;
        const outputCost = model.cost_per_1k_tokens.output;

        // コストデータがある場合（0でない場合）
        if (inputCost > 0 || outputCost > 0) {
            // 100万トークンあたりの価格に変換（1kトークンの価格 × 1000）
            const inputCostPer1M = (inputCost * 1000).toFixed(2);
            const outputCostPer1M = (outputCost * 1000).toFixed(2);

            pricingText = `<span class="model-pricing">$${inputCostPer1M}/$${outputCostPer1M}</span>`;
        }
    }

    // supported_methods表示（デバッグ用・小さく表示）
    let methodsText = '';
    if (model.supported_methods && model.supported_methods.length > 0) {
        const methodsShort = model.supported_methods.join(', ');
        methodsText = `<div class="model-methods" style="font-size: 0.7em; color: #888; margin-top: 2px;">Methods: ${methodsShort}</div>`;
    }

    item.innerHTML = `
        <div class="model-info">
            <div class="model-name">${displayName}${pricingText}</div>
            ${methodsText}
            ${notRecommendedBadge}
            ${rateLimitBadge}
        </div>
        <span class="model-check">${isSelected ? '✓' : ''}</span>
    `;

    item.onclick = () => selectTempModel(model.id);
    return item;
}

// 一時選択モデルを設定
export function selectTempModel(modelId) {
    window.App.model.tempSelected = modelId;
    renderModelList();
}

// モデル選択を保存
export function saveModelSelection() {
    const showToast = window.showToast;

    window.App.model.current = window.App.model.tempSelected;

    // localStorageに保存
    if (window.App.model.current) {
        localStorage.setItem('memo_ai_selected_model', window.App.model.current);
    } else {
        localStorage.removeItem('memo_ai_selected_model');
    }

    showToast('モデル設定を保存しました');
    closeModelModal();
}

// モーダルを閉じる
export function closeModelModal() {
    document.getElementById('modelModal').classList.add('hidden');
}

// セッションコストを更新
export function updateSessionCost(cost) {
    if (cost) window.App.model.sessionCost += cost;
}
