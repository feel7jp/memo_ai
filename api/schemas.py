"""
Pydanticモデル定義 (API Request/Response Schemas)

APIのリクエストボディの構造を定義し、型チェックと自動ドキュメント生成を行います。
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    """テキスト分析用・タスク抽出用のリクエストモデル"""

    text: str  # ユーザーの入力テキスト
    target_db_id: str  # 対象のNotionデータベースID
    system_prompt: str  # AIへの指示（システムプロンプト）
    model: Optional[str] = None  # 使用するAIモデル（指定がなければデフォルト）


class SaveRequest(BaseModel):
    """Notionへの保存用リクエストモデル"""

    target_db_id: str  # 保存先のデータベースID または ページID
    target_type: Optional[str] = (
        "database"  # 'database' (データベースに行を追加) or 'page' (ページにブロックを追加)
    )
    properties: Dict[str, Any]  # 保存するプロパティ（タイトル、日付、タグなど）
    text: Optional[str] = None  # ページに追加する場合の本文テキスト


class ChatRequest(BaseModel):
    """チャット対話用のリクエストモデル"""

    text: Optional[str] = ""  # ユーザーのメッセージ (画像のみの場合は空文字も許容)
    target_id: str  # 会話のコンテキストとなるNotionページ/DBのID
    system_prompt: Optional[str] = None  # AIへの振る舞いの指示
    session_history: Optional[List[Dict[str, str]]] = None  # 会話履歴 (メモリ機能)
    reference_context: Optional[str] = None  # 参照中のページ内容などの追加コンテキスト
    image_data: Optional[str] = None  # 画像送信時のBase64データ
    image_mime_type: Optional[str] = None  # 画像のMIMEタイプ (例: image/jpeg)
    model: Optional[str] = None  # 使用するAIモデル
