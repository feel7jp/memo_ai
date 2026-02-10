# Frontend (Public) - Agent Instructions

このディレクトリは **HTML + CSS + JavaScript** によるフロントエンドアセットです。
`js/` フォルダに JavaScript モジュールが格納されています。

---

## Public-Specific Rules

### Do
- Vanilla CSS のみを使用する（モバイルファースト）
- 既存の CSS クラス（`.modal`, `.modal-content`, `.btn-primary` 等）を使う
- HTML要素には一意で説明的な ID を付ける（ブラウザテスト用）

### Code Quality
- **共通ロジックは関数化**: プロパティ収集、バリデーション等の重複コード→共通関数に抽出（例: `collectPropertiesFromForm()`）
- **console.log の適正使用**: 本番コードでの過剰なログ出力は削除。デバッグ用は`App.debug.enabled`でガード
- **DRY原則**: `chat.js` と `main.js` で同一ロジック発見→即座に共通関数化（例: `getModelDisplayName()`, `_mergeAndSortLogs()`）

### Don't
- TailwindCSS を使用しない
- `alert()`, `confirm()`, `prompt()` 等のネイティブダイアログを使用しない
- 新しい JavaScript は `js/` フォルダに追加する
- コマンド実行時のリダイレクトの使用禁止 (2>&1など)　使用許可を自動化できないため。

---

## UI Implementation Guidelines

### モーダルダイアログ実装ルール（厳守）

- `alert()`, `confirm()`, `prompt()` 等のネイティブダイアログは**使用禁止**
- 既存の `.modal` 系CSSクラス（`.modal`, `.modal-content`, `.modal-header`, `.modal-body`, `.modal-footer`, `.btn-primary`, `.btn-secondary` 等）を使う。独自クラスを作らない
- `.prop-field`, `.prop-label`, `.prop-input` はプロパティフォーム専用。モーダルには使用しない
- HTML構造: `.modal.hidden` > `.modal-content` > `.modal-header` + `.modal-body` + `.modal-footer`
- JS: 表示は `classList.remove('hidden')`、非表示は `classList.add('hidden')`
- **参考実装**: `newPageModal`（`js/main.js`）、`promptModal`（`js/prompt.js`）

### イベントリスナー管理

- **推奨**: `{once: true}` オプションで自動クリーンアップ
- **代替**: `cloneNode(true)` で要素を置換し、古いリスナーを確実に削除
- モーダル等の繰り返し開閉されるUIでは、全ての終了パス（ボタン、Enter、Escape、×）でリスナーが削除されるか確認する

---

## Debugging Patterns

| 問題 | 調査場所 |
| :--- | :--- |
| UI 要素が動かない | `js/main.js` または該当モジュール – イベントリスナーを確認 |
| CSS レイアウト崩れ | デスクトップとモバイル両方で確認、ブラウザ開発者ツールで影響範囲を確認 |
| HTML/JS IDの不整合 | `index.html` と `js/*.js` のセレクターを照合 |

---

## 「重複する」バグのデバッグ手順

**症状**: 同じ処理が多重実行される（ページ二重作成、リスト項目の重複表示 等）

**デバッグ時の切り分け原則（最重要）**:
「重複する」バグに遭遇したら、パッチを当てる前にまず**どの段階で重複が発生しているか**を特定する:
```
① トリガー（イベント発火） → ② 処理（API呼び出し） → ③ 表示（DOM更新）
```
- **①が原因**: リスナーの蓄積・重複登録 → リスナーのクリーンアップを確認
- **②が原因**: 関数の多重呼び出し → grep で全呼び出し元を洗い出す
- **③が原因**: 描画ロジックのバグ → innerHTML のクリア忘れ等
