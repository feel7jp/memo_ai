"""
サービス層関数 (Business Logic Helpers)

エンドポイントから呼ばれる共通ロジックを定義します。
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo


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
    現在の日本時間 (JST) を文字列として返します。

    AIに現在のコンテキスト（日時）を正確に伝えるために重要です。
    また、曜日も日本語で付与することで、AIが「今週の〜」や「週末に〜」といった表現を理解しやすくします。
    フォーマット例: 2024-01-01 12:00 (2024年01月01日 12:00 JST) 月曜日
    """
    jst = ZoneInfo("Asia/Tokyo")
    now = datetime.now(jst)
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    weekday_str = weekdays[now.weekday()]

    # AIが理解しやすいフォーマット
    return f"{now.strftime('%Y-%m-%d %H:%M')} ({now.strftime('%Y年%m月%d日 %H:%M')} JST) {weekday_str}曜日"
