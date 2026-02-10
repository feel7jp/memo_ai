"""
サービス層関数 (Business Logic Helpers)

エンドポイントから呼ばれる共通ロジックを定義します。
"""

import re
from datetime import datetime

from api.config import NOTION_BLOCK_CHAR_LIMIT


def extract_plain_text(rich_text_items: list) -> str:
    """
    Notion API の rich_text / title 配列からプレーンテキストを結合して返す。

    アプリケーション全体で散在していた
    `"".join([t.get("plain_text", "") for t in items])` パターンの共通化。

    Args:
        rich_text_items: Notion API の rich_text または title 配列

    Returns:
        結合されたプレーンテキスト文字列
    """
    if not rich_text_items:
        return ""
    return "".join(t.get("plain_text", "") for t in rich_text_items)


def sanitize_image_data(text: str) -> str:
    """
    テキストコンテンツからBase64形式の画像データを除去します。

    Notionに送信する際、長大なBase64文字列が含まれているとエラーやパフォーマンス低下の原因になるため、
    正規表現を使ってこれらを削除または置換します。
    Markdown形式の画像リンクとHTML形式のimgタグの両方に対応しています。
    """
    # Markdown形式の画像 (data URIスキーム) を削除: ![alt](data:image/png;base64,...)
    text = re.sub(r"!\[.*?\]\(data:image\/.*?\)", "", text, flags=re.DOTALL)
    # HTML形式のimgタグ (data URIスキーム) を削除: <img src="data:image/..." ...>
    text = re.sub(
        r'<img[^>]+src=["\']data:image\/[^"\']+["\'][^>]*>', "", text, flags=re.DOTALL
    )
    # 特定のマーカー文字列を除去
    text = text.replace("[画像送信]", "").strip()
    return text


def get_current_jst_str() -> str:
    """
    現在時刻をJST（日本標準時）の文字列で取得

    AIに現在時刻の情報を与えることで、日時に関する回答の精度を向上させます。
    """
    import zoneinfo

    jst = zoneinfo.ZoneInfo("Asia/Tokyo")
    now = datetime.now(jst)
    return now.strftime("%Y-%m-%d %H:%M:%S JST")


def _chunk_rich_text_items(
    items: list, text_key: str = "rich_text", limit: int = NOTION_BLOCK_CHAR_LIMIT
) -> list:
    """
    rich_text/title配列の各アイテムを指定文字数で分割

    Notion APIはrich_textやtitleの各アイテムに2000文字の制限があります。
    この関数は長いテキストを持つアイテムを分割して、制限内に収めます。

    Args:
        items: rich_text/title配列
        text_key: 処理対象のキー（"rich_text" or "title"）
        limit: 1アイテムあたりの文字数上限（デフォルト NOTION_BLOCK_CHAR_LIMIT）

    Returns:
        分割後のアイテム配列
    """
    result = []
    for item in items:
        if "text" not in item:
            result.append(item)
            continue

        content = item["text"].get("content", "")
        if len(content) <= limit:
            result.append(item)
        else:
            # 長いコンテンツを分割
            for i in range(0, len(content), limit):
                chunk_item = {
                    "type": "text",
                    "text": {"content": content[i : i + limit]},
                }
                # 元のアイテムにannotationsがあれば引き継ぐ
                if "annotations" in item:
                    chunk_item["annotations"] = item["annotations"]
                result.append(chunk_item)

    return result


def _sanitize_rich_text_field(items: list, sanitize_fn) -> list:
    """
    rich_text/title配列のテキストをサニタイズし、文字数制限で分割する。

    既存の _chunk_rich_text_items を内部で再利用する実装。
    sanitize_fn は sanitize_image_data などのテキスト変換関数を想定。

    Args:
        items: rich_text/title配列
        sanitize_fn: テキストサニタイズ関数

    Returns:
        サニタイズ & 分割済み配列
    """
    # Step 1: サニタイズ（Base64画像除去等）
    for item in items:
        if "text" in item and "content" in item["text"]:
            item["text"]["content"] = sanitize_fn(item["text"]["content"])

    # Step 2: 文字数制限による分割（既存関数を再利用）
    return _chunk_rich_text_items(items)


def sanitize_notion_properties(properties: dict) -> dict:
    """
    Notionプロパティ値をサニタイズ（画像データ除去 + 文字数分割）。

    rich_text と title フィールドを検出し、それぞれを
    _sanitize_rich_text_field で処理する。

    Args:
        properties: Notionプロパティ辞書

    Returns:
        サニタイズ済みプロパティ辞書
    """
    sanitized = properties.copy()

    for key, val in sanitized.items():
        if not isinstance(val, dict):
            continue

        if "rich_text" in val and val["rich_text"]:
            val["rich_text"] = _sanitize_rich_text_field(
                val["rich_text"], sanitize_image_data
            )

        if "title" in val and val["title"]:
            val["title"] = _sanitize_rich_text_field(val["title"], sanitize_image_data)

    return sanitized


def ensure_title_property(properties: dict, fallback_text: str) -> dict:
    """
    タイトルプロパティが存在しない場合、コンテンツから自動生成する。

    Args:
        properties: サニタイズ済みプロパティ
        fallback_text: タイトル生成のフォールバックテキスト

    Returns:
        タイトルが保証されたプロパティ辞書
    """
    # タイトルの存在チェック
    has_title = any(
        "title" in val for val in properties.values() if isinstance(val, dict)
    )

    if not has_title:
        safe_title = (fallback_text or "Untitled").split("\n")[0][:100]
        properties["Name"] = {"title": [{"text": {"content": safe_title}}]}

    return properties


def create_content_blocks(text: str, chunk_size: int = NOTION_BLOCK_CHAR_LIMIT) -> list:
    """
    テキストをNotionのparagraphブロック配列に変換する。

    Notion APIのブロックサイズ制限(NOTION_BLOCK_CHAR_LIMIT)に従い自動分割。

    Args:
        text: 変換するテキスト
        chunk_size: 分割サイズ（デフォルト NOTION_BLOCK_CHAR_LIMIT）

    Returns:
        Notion APIのchildrenブロック配列
    """
    if not text:
        return []

    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": text[i : i + chunk_size]}}
                ]
            },
        }
        for i in range(0, len(text), chunk_size)
    ]
