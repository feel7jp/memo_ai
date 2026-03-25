# Frontend (JavaScript + JSDoc) - Agent Instructions

このディレクトリは **Vanilla JavaScript + JSDoc型注釈** によるフロントエンド実装です。
ビルド不要で、ブラウザが直接実行できます。

---

## JSDoc-Specific Rules

### Do
- JSDoc コメントで型を明示する（ `/** @type {HTMLInputElement} */` 等）
- `types.d.ts` でグローバル型を定義
- DOM要素取得時は型アサーションを使用
- `import`/`export` は使わず、グローバル `window.*` へのエクスポートで連携
- `tsc --noEmit` で型チェックを実行（`npm run type-check`）

### Don't
- ビルドツール（Vite, Webpack等）を導入しない
- `import`/`export` を使用しない（ES Modules は使わない）
- `any` 型の乱用を避ける
- コマンド実行時のリダイレクトの使用禁止 (2>&1など)　使用許可を自動化できないため。

---

## File Structure

| ファイル | 役割 |
| :--- | :--- |
| `main.js` | エントリポイント、初期化、Notion ターゲット選択 |
| `chat.js` | チャット UI: 吹き出し描画、履歴管理 |
| `images.js` | 画像キャプチャ・処理 |
| `prompt.js` | システムプロンプト管理 |
| `model.js` | AI モデル選択 UI |
| `debug.js` | デバッグモーダル (DEBUG_MODE 時のみ) |
| `types.d.ts` | グローバル型定義 |

---

## UI Implementation Guidelines

`public/AGENTS.md` のUI実装ガイドラインに準拠すること:
- モーダルダイアログは `.modal` 系CSSクラスを使用
- ネイティブダイアログ (`alert`, `confirm`, `prompt`) は使用禁止
- イベントリスナーは `{once: true}` で自動クリーンアップを優先

---

## Notion Property Handling (重要)

`title` プロパティはフォームに表示されないため、**保存時にスキーマから検索して設定する**:

```javascript
if (window.App.target.schema) {
    for (const [key, prop] of Object.entries(window.App.target.schema)) {
        if (prop.type === 'title') {
            properties[key] = { title: [{ text: { content } }] };
            break;
        }
    }
}
```

---

## State Management Best Practices

### Snapshot Pattern (必須)

**原則**: API呼び出し前に変更可能な状態をローカル変数にキャプチャする

#### ❌ NG: 状態クリア後に参照
```javascript
// UI状態をクリア
clearImageData();
disableImageGenMode();

// ❌ すでにクリアされた値を送信してしまう
fetch('/api/chat', {
    method: 'POST',
    body: JSON.stringify({
        image_data: window.App.image.data,           // null
        image_generation: window.App.image.generationMode  // false
    })
});
```

#### ✅ OK: スナップショット → クリア → 使用
```javascript
// 1. スナップショット取得 (先にコピー)
const imageData = window.App.image.data;
const mimeType = window.App.image.mimeType;
const isImageGen = window.App.image.generationMode;

// 2. UI状態をクリア
clearImageData();
disableImageGenMode();

// 3. スナップショット値を使用
fetch('/api/chat', {
    method: 'POST',
    body: JSON.stringify({
        image_data: imageData,
        image_mime_type: mimeType,
        image_generation: isImageGen
    })
});
```

### Race Condition Prevention

連続したAPI呼び出しで古いレスポンスが新しいレスポンスを上書きしないよう、`AbortController` を使用:

```javascript
let currentController = null;

async function fetchData(query) {
    // 前のリクエストをキャンセル
    if (currentController) {
        currentController.abort();
    }

    currentController = new AbortController();

    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            signal: currentController.signal,
            body: JSON.stringify({ query })
        });
        return await response.json();
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Request was cancelled');
        } else {
            throw error;
        }
    }
}
```
