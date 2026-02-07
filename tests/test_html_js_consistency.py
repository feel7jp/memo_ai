"""
HTML-JavaScript Consistency Test
HTMLとJavaScript間のセレクター整合性を自動検証する。

検出対象:
  - getElementById('id') / querySelector('#id')
  - querySelector('.class') / querySelectorAll('.class')
  - JSテンプレート文字列内のid="..."定義も認識（動的DOM要素対応）
"""

import re
from pathlib import Path

# プロジェクトルート基準のパス
HTML_FILE = Path("public/index.html")
JS_DIR = Path("public/js")


def _extract_html_ids_and_classes(html_content: str):
    """HTMLからIDとクラス名を抽出"""
    ids = set(re.findall(r'id="([^"]+)"', html_content))
    classes = set()
    for match in re.findall(r'class="([^"]+)"', html_content):
        classes.update(match.split())
    return ids, classes


def _extract_js_selectors(js_dir: Path):
    """JavaScriptファイルからセレクター参照と動的ID定義を抽出"""
    id_refs: dict[str, list[str]] = {}
    class_refs: dict[str, list[str]] = {}
    dynamic_ids: set[str] = set()
    dynamic_classes: set[str] = set()

    for js_file in js_dir.glob("*.js"):
        content = js_file.read_text(encoding="utf-8")
        name = js_file.name

        # getElementById('xxx') / getElementById("xxx")
        for m in re.finditer(r"getElementById\(['\"]([a-zA-Z0-9_-]+)['\"]\)", content):
            id_refs.setdefault(m.group(1), []).append(name)

        # querySelector('#xxx') / querySelectorAll('#xxx')
        for m in re.finditer(r"querySelector(?:All)?\(['\"]#([a-zA-Z0-9_-]+)", content):
            id_refs.setdefault(m.group(1), []).append(name)

        # querySelector('.xxx') / querySelectorAll('.xxx')
        for m in re.finditer(
            r"querySelector(?:All)?\(['\"]\.([a-zA-Z0-9_-]+)", content
        ):
            class_refs.setdefault(m.group(1), []).append(name)

        # --- 動的DOM要素の定義を抽出（false positive防止） ---

        # JS内テンプレート文字列で定義されたid
        # 例: innerHTML = '<video id="cameraPreview"...>'
        for m in re.finditer(r'id=\\"([a-zA-Z0-9_-]+)\\"', content):
            dynamic_ids.add(m.group(1))
        for m in re.finditer(r'id="([a-zA-Z0-9_-]+)"', content):
            dynamic_ids.add(m.group(1))

        # className = 'chat-bubble ai' / classList.add('xxx')
        for m in re.finditer(r"className\s*=\s*['\"`]([^'\"`]+)", content):
            dynamic_classes.update(m.group(1).split())
        for m in re.finditer(r"classList\.add\(['\"]([a-zA-Z0-9_-]+)", content):
            dynamic_classes.add(m.group(1))

    return id_refs, class_refs, dynamic_ids, dynamic_classes


def _format_mismatches(label: str, missing: set, refs: dict) -> list[str]:
    """不整合を読みやすいエラーメッセージに整形"""
    if not missing:
        return []
    lines = [f"\n{label} ({len(missing)}):"]
    for name in sorted(missing):
        files = ", ".join(sorted(set(refs[name])))
        lines.append(f"  [MISSING] {name} (used in {files})")
    return lines


def test_html_js_selector_consistency():
    """HTMLに存在しないID/classがJavaScriptで参照されていないことを検証"""
    assert HTML_FILE.exists(), f"HTML not found: {HTML_FILE}"
    assert JS_DIR.is_dir(), f"JS directory not found: {JS_DIR}"

    html_content = HTML_FILE.read_text(encoding="utf-8")
    html_ids, html_classes = _extract_html_ids_and_classes(html_content)
    js_id_refs, js_class_refs, dynamic_ids, dynamic_classes = _extract_js_selectors(
        JS_DIR
    )

    # HTML内 + JS内テンプレートで定義された要素を合算
    all_known_ids = html_ids | dynamic_ids
    all_known_classes = html_classes | dynamic_classes

    missing_ids = set(js_id_refs.keys()) - all_known_ids
    missing_classes = set(js_class_refs.keys()) - all_known_classes

    errors = []
    errors.extend(
        _format_mismatches("IDs in JS but not in HTML", missing_ids, js_id_refs)
    )
    errors.extend(
        _format_mismatches(
            "Classes in JS but not in HTML", missing_classes, js_class_refs
        )
    )

    assert not errors, "\n".join(errors)


def test_no_orphan_html_ids():
    """HTMLのIDがJavaScriptで使用されていない場合を情報として報告(警告のみ)"""
    if not HTML_FILE.exists() or not JS_DIR.is_dir():
        return

    html_content = HTML_FILE.read_text(encoding="utf-8")
    html_ids, _ = _extract_html_ids_and_classes(html_content)
    js_id_refs, _, _, _ = _extract_js_selectors(JS_DIR)

    orphan_ids = html_ids - set(js_id_refs.keys())
    if orphan_ids:
        # テスト失敗にはしないが、情報として出力
        print(f"\n[INFO] HTML IDs not referenced in JS ({len(orphan_ids)}):")
        for name in sorted(orphan_ids):
            print(f"  - {name}")
