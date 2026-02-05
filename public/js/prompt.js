// ========== PROMPT MODULE ==========
// システムプロンプト編集モーダル機能

// プロンプト編集の状態管理
let promptOriginalValue = '';

// システムプロンプトモーダルを開く
export function openPromptModal() {
    const showToast = window.showToast;
    
    if (!window.App.target.id) {
        showToast('ターゲットを選択してください');
        return;
    }
    
    const modal = document.getElementById('promptModal');
    const selector = document.getElementById('promptTargetSelect');
    const textarea = document.getElementById('promptTextarea');
    const saveBtn = document.getElementById('savePromptBtn');
    const resetBtn = document.getElementById('resetPromptBtn');
    
    // ターゲットリストを読み込み（キャッシュから）
    const cachedTargets = localStorage.getItem(window.App.cache.KEYS.TARGETS);
    if (cachedTargets) {
        try {
            const data = JSON.parse(cachedTargets).data;
            
            // プロンプトモーダル用のターゲットリスト作成（新規作成オプションなし）
            selector.innerHTML = '';
            if (data.targets && data.targets.length > 0) {
                data.targets.forEach(t => {
                    const opt = document.createElement('option');
                    opt.value = t.id;
                    opt.textContent = `[${t.type === 'database' ? 'DB' : 'Page'}] ${t.title}`;
                    opt.dataset.type = t.type;
                    selector.appendChild(opt);
                });
                // 現在のターゲットを選択
                selector.value = window.App.target.id;
                // 初期選択を記録
                selector.dataset.prevValue = window.App.target.id;
            }
        } catch(e) {
            console.error('Failed to load targets for prompt modal:', e);
        }
    }
    
    // 選択中のターゲットのプロンプトを表示
    const promptKey = `${window.App.cache.KEYS.PROMPT_PREFIX}${window.App.target.id}`;
    const savedPrompt = localStorage.getItem(promptKey);
    
    // リセットボタン: 常に有効化
    if (resetBtn) {
        resetBtn.disabled = false;
        resetBtn.classList.remove('hidden');
    }
    
    // カスタムプロンプトがあれば表示、なければデフォルトを表示
    if (savedPrompt) {
        textarea.value = savedPrompt;
    } else {
        textarea.value = window.App.defaultPrompt;
    }
    textarea.placeholder = 'システムプロンプトを入力してください...';
    
    promptOriginalValue = textarea.value; // 元の値を保存
    textarea.disabled = false;
    saveBtn.disabled = false;
    
    // ターゲット変更時のイベントリスナーを設定
    // 既存のリスナーを削除してから追加（重複防止）
    const newSelector = selector.cloneNode(true);
    selector.parentNode.replaceChild(newSelector, selector);
    
    newSelector.addEventListener('change', function(e) {
        const newTargetId = e.target.value;
        const prevTargetId = e.target.dataset.prevValue;
        
        // 変更がある場合は確認
        if (textarea.value !== promptOriginalValue) {
            showDiscardConfirmation(() => {
                // 破棄を確認したら新しいターゲットに切り替え
                e.target.dataset.prevValue = newTargetId;
                loadPromptForTarget(newTargetId);
            });
            // キャンセルされた場合は元に戻す
            // Note: showDiscardConfirmationのcancelボタンが押された場合は何もしない
            // しかし、selectの値は既に変わってしまっているので戻す必要がある
            // この処理を非同期で行う
            setTimeout(() => {
                if (e.target.dataset.prevValue !== newTargetId) {
                    e.target.value = e.target.dataset.prevValue;
                }
            }, 100);
        } else {
            // 変更がない場合はそのまま切り替え
            e.target.dataset.prevValue = newTargetId;
            loadPromptForTarget(newTargetId);
        }
    });
    
    // モーダルを表示
    modal.classList.remove('hidden');
}

// 破棄確認モーダルの制御
export function showDiscardConfirmation(onConfirm) {
    const modal = document.getElementById('confirmDiscardModal');
    const confirmBtn = document.getElementById('confirmDiscardBtn');
    const cancelBtn = document.getElementById('cancelDiscardBtn');
    const closeBtn = document.getElementById('closeConfirmDiscardModalBtn');
    
    // イベントリスナーの一時的な登録（クリーンアップが必要）
    const cleanup = () => {
        confirmBtn.onclick = null;
        cancelBtn.onclick = null;
        closeBtn.onclick = null;
        modal.classList.add('hidden');
    };
    
    confirmBtn.onclick = () => {
        cleanup();
        onConfirm();
    };
    
    cancelBtn.onclick = cleanup;
    closeBtn.onclick = cleanup;
    
    modal.classList.remove('hidden');
}

// システムプロンプトモーダルを閉じる
export function closePromptModal() {
    const textarea = document.getElementById('promptTextarea');
    // 変更がある場合は警告
    if (textarea && textarea.value !== promptOriginalValue) {
        showDiscardConfirmation(() => {
            const modal = document.getElementById('promptModal');
            modal.classList.add('hidden');
        });
        return;
    }
    
    const modal = document.getElementById('promptModal');
    modal.classList.add('hidden');
}

// システムプロンプトを保存
export async function saveSystemPrompt() {
    const showToast = window.showToast;
    const selector = document.getElementById('promptTargetSelect');
    const targetId = selector?.value || window.App.target.id;
    
    if (!targetId) return;

    const textarea = document.getElementById('promptTextarea');
    const saveBtn = document.getElementById('savePromptBtn');
    const resetBtn = document.getElementById('resetPromptBtn');
    const newPrompt = textarea.value.trim();
    
    saveBtn.disabled = true;
    
    try {
        const promptKey = `${window.App.cache.KEYS.PROMPT_PREFIX}${targetId}`;
        
        // 空白文字のみ、または空の場合 → デフォルトを使用（カスタム設定を削除）
        // デフォルトと同じ場合 → デフォルトを使用（カスタム設定を削除）
        // それ以外 → カスタムプロンプトとして保存
        if (!newPrompt || newPrompt === window.App.defaultPrompt.trim()) {
            // デフォルトを使用: localStorageから削除
            localStorage.removeItem(promptKey);
            
            // 現在のターゲットと同じ場合はApp.target.systemPromptも更新
            if (targetId === window.App.target.id) {
                window.App.target.systemPrompt = null;
            }
            
            // リセットボタンを隠す
            if (resetBtn) {
                resetBtn.classList.add('hidden');
                resetBtn.disabled = true;
            }
        } else {
            // カスタムプロンプトを保存
            localStorage.setItem(promptKey, newPrompt);
            
            // 現在のターゲットと同じ場合はApp.target.systemPromptも更新
            if (targetId === window.App.target.id) {
                window.App.target.systemPrompt = newPrompt;
            }
            
            // リセットボタンを表示
            if (resetBtn) {
                resetBtn.classList.remove('hidden');
                resetBtn.disabled = false;
            }
        }
        
        // 保存後、元の値を更新（ダーティフラグをクリア）
        promptOriginalValue = textarea.value;
        
        showToast('✅ システムプロンプトを保存しました');
        closePromptModal(); // 保存後にモーダルを閉じる
    } catch (e) {
        console.error('Failed to save prompt:', e);
        showToast('❌ 保存に失敗しました');
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = '保存';
    }
}

// システムプロンプトをリセット
export function resetSystemPrompt() {
    const showToast = window.showToast;
    const textarea = document.getElementById('promptTextarea');
    if (textarea) {
        textarea.value = window.App.defaultPrompt;
        showToast('デフォルトのテキストを入力しました');
    }
}

// ターゲットプロンプト読み込み処理
export function loadPromptForTarget(targetId) {
    const textarea = document.getElementById('promptTextarea');
    const resetBtn = document.getElementById('resetPromptBtn');
    
    const promptKey = `${window.App.cache.KEYS.PROMPT_PREFIX}${targetId}`;
    const savedPrompt = localStorage.getItem(promptKey);
    
    // カスタムプロンプトがあれば表示、なければデフォルトを表示
    if (savedPrompt) {
        textarea.value = savedPrompt;
    } else {
        textarea.value = window.App.defaultPrompt;
    }
    textarea.placeholder = 'システムプロンプトを入力してください...';
    promptOriginalValue = textarea.value;
    
    // リセットボタンの表示制御
    if (resetBtn) {
        resetBtn.disabled = false;
        resetBtn.classList.remove('hidden');
    }
}
