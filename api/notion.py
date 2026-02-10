import os
import asyncio
import httpx
import time
from datetime import datetime
from collections import deque
from typing import Dict, List, Optional, Any
from api.logger import setup_logger
from api.config import NOTION_BLOCK_CHAR_LIMIT
from api.services import extract_plain_text

logger = setup_logger(__name__)

# Notion API Configuration
# Notion APIのバージョンを指定（破壊的変更が多いため固定推奨）
NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"

# デバッグ用: 直近10件のNotion API通信ログ
notion_api_log = deque(maxlen=10)


def _record_notion_log(
    method: str,
    endpoint: str,
    status: Optional[int],
    duration: float,
    attempt: int,
    error: Optional[str],
    response_data: Optional[Dict],
):
    """Notion API通信をログに記録"""
    notion_api_log.append(
        {
            "timestamp": datetime.now().isoformat(),
            "method": method,
            "endpoint": endpoint,
            "status": status,
            "duration_ms": round(duration * 1000),
            "attempt": attempt + 1,
            "error": error,
            "response": response_data,  # 生のレスポンスデータをそのまま保存
        }
    )


async def safe_api_call(
    method,
    endpoint,
    ignore_errors: Optional[List[int]] = None,
    max_retries: int = 3,
    timeout: float = 30.0,
    **kwargs,
):
    """
    堅牢なAPIラッパー関数

    リトライロジック（指数バックオフ）とエラーハンドリングを内蔵し、
    ネットワークの不安定さやNotion APIの一時的なエラーに強い設計になっています。

    Args:
        method (str): HTTPメソッド (GET, POST等)
        endpoint (str): APIエンドポイント (例: "pages/xxx")
        ignore_errors (List[int]): 無視してNoneを返すステータスコードのリスト
        max_retries (int): 最大リトライ回数
        timeout (float): タイムアウト秒数
    """
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        raise ValueError(
            "❌ NOTION_API_KEY が設定されていません。.envファイルに NOTION_API_KEY=your_api_key_here を追加してください。"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    url = f"{BASE_URL}/{endpoint}"
    start_time = time.time()

    # リトライループ
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                # レート制限対策として少し待機
                await asyncio.sleep(0.35)

                response = await client.request(method, url, headers=headers, **kwargs)

                # HTTP 429 (Too Many Requests) のハンドリング
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 2))
                    logger.warning("Rate limited, waiting %ds...", retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                # 指定されたエラーコードの場合、例外を投げずにNoneを返す（例：404 Not Foundを許容する場合など）
                if ignore_errors and response.status_code in ignore_errors:
                    return None

                response.raise_for_status()
                result = response.json()

                # ログ記録（成功時）
                _record_notion_log(
                    method,
                    endpoint,
                    response.status_code,
                    time.time() - start_time,
                    attempt,
                    None,
                    result,
                )
                return result

        except (httpx.ReadTimeout, httpx.NetworkError) as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            if attempt < max_retries - 1:
                # 指数バックオフ: 1秒, 2秒, 4秒... と待機時間を倍にしていく
                backoff = 2**attempt
                logger.warning(
                    "%s on %s, retry %d/%d after %ds",
                    type(e).__name__,
                    endpoint,
                    attempt + 1,
                    max_retries,
                    backoff,
                )
                await asyncio.sleep(backoff)
            else:
                logger.error(
                    "%s on %s after %d attempts",
                    type(e).__name__,
                    endpoint,
                    max_retries,
                )
                _record_notion_log(
                    method,
                    endpoint,
                    None,
                    time.time() - start_time,
                    attempt,
                    error_msg,
                    None,
                )
                raise

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            error_msg = f"HTTP {status}: {str(e)}"
            logger.warning("HTTP %d on %s %s", status, method, endpoint)
            # 500系エラーはサーバー側の問題なのでリトライする価値がある
            if status >= 500 and attempt < max_retries - 1:
                backoff = 2**attempt
                logger.warning(
                    "Server error, retry %d/%d after %ds",
                    attempt + 1,
                    max_retries,
                    backoff,
                )
                await asyncio.sleep(backoff)
            else:
                _record_notion_log(
                    method,
                    endpoint,
                    status,
                    time.time() - start_time,
                    attempt,
                    error_msg,
                    None,
                )
                raise

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(
                "Unexpected error on %s: %s - %s", endpoint, type(e).__name__, e, exc_info=True
            )
            _record_notion_log(
                method,
                endpoint,
                None,
                time.time() - start_time,
                attempt,
                error_msg,
                None,
            )
            raise

    return None


async def get_page_info(page_id: str) -> Optional[Dict[str, Any]]:
    """
    ページの基本情報を取得

    プロパティ情報や親ページのIDなどを取得するために使用します。
    """
    return await safe_api_call("GET", f"pages/{page_id}")


async def fetch_config_db(config_db_id: str) -> List[Dict[str, str]]:
    """
    設定データベースから設定情報を一括取得

    Notion上の「設定用データベース」から、ターゲットID、プロンプト、名前などの設定を読み込みます。
    これにより、アプリケーションの再デプロイなしでアシスタントの挙動を変更できます。
    """
    # データベースクエリ（全件検索）
    response = await safe_api_call("POST", f"databases/{config_db_id}/query")
    if not response:
        return []

    configs = []
    for page in response.get("results", []):
        try:
            props = page["properties"]

            # プロパティ値の抽出ヘルパー（型安全にテキストを取得）
            def get_text(p):
                """プロパティからテキスト抽出"""
                if not p:
                    return ""
                t_type = p.get("type")
                if t_type == "title":
                    return extract_plain_text(p.get("title", []))
                if t_type == "rich_text":
                    return extract_plain_text(p.get("rich_text", []))
                return ""

            name = get_text(props.get("Name"))
            target_id = get_text(props.get("TargetDB_ID"))
            prompt = get_text(props.get("SystemPrompt"))

            if not name:
                continue  # 名前がないレコードは無視

            configs.append(
                {
                    "name": name,
                    "target_db_id": target_id.strip(),
                    "system_prompt": prompt,
                }
            )
        except (KeyError, IndexError):
            continue
    return configs


async def get_db_schema(target_db_id: str) -> Dict[str, Any]:
    """
    データベースのスキーマ（プロパティ定義）を取得

    AIが正確なJSON構造を生成するために、対象データベースのカラム一覧（型情報含む）を取得します。
    """
    # データベースメタデータの取得
    # IDがページIDだった場合、Notionは400を返すが、ここではエラーとして扱わずに例外処理側で判定させるために400を無視設定に入れています。
    # （呼び出し元で is None チェックをしている場合があるため）
    response = await safe_api_call(
        "GET", f"databases/{target_db_id}", ignore_errors=[400]
    )
    if response is None:
        raise ValueError("Not a database")

    return response.get("properties", {})


async def fetch_recent_pages(target_db_id: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    最新の登録データを取得 (Few-shot学習用)

    直近に作成されたデータを取得し、AIに「どのような形式でデータが登録されているか」の例として提示します。
    """
    # データベースクエリ（作成日時順の降順）
    body = {
        "page_size": limit,
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
    }
    response = await safe_api_call("POST", f"databases/{target_db_id}/query", json=body)
    if not response:
        return []
    return response.get("results", [])


async def create_page(
    target_db_id: str, properties: Dict[str, Any], children: List[Dict[str, Any]] = None
) -> str:
    """
    指定されたデータベースに新しいページを作成

    Args:
        target_db_id (str): 親データベースのID
        properties (Dict): 登録するプロパティ値
        children (List[Dict], optional): ページ本文に追加するブロックのリスト
    Returns:
        str: 新しく作成されたページのNotion URL
    """
    body = {"parent": {"database_id": target_db_id}, "properties": properties}
    if children:
        body["children"] = children

    response = await safe_api_call("POST", "pages", json=body)

    if response and "url" in response:
        return response["url"]

    raise Exception("Failed to create page")


async def fetch_children_list(
    parent_page_id: str, limit: int = 100
) -> List[Dict[str, Any]]:
    """
    ページ内ブロック（子要素）の一覧取得

    ターゲット選択画面でルートページ以下のコンテンツを表示したり、ページの内容を読み取るために使用します。
    """
    response = await safe_api_call(
        "GET", f"blocks/{parent_page_id}/children?page_size={limit}"
    )
    if not response:
        return []
    results = response.get("results", [])
    # 削除済み（アーカイブ）のブロックは除外して返します
    return [b for b in results if not b.get("archived")]


async def append_block(page_id: str, content: str) -> bool:
    """
    ページ末尾へのテキストブロック追加

    長文（NOTION_BLOCK_CHAR_LIMIT文字以上）に対応しており、自動的に適切なサイズに分割してNotionに送信します。
    """
    MAX_CHARS = NOTION_BLOCK_CHAR_LIMIT

    # コンテンツの分割（Chunking）
    # Pythonのスライス機能を使ってMAX_CHARS文字ごとのリストを作成
    chunks = [content[i : i + MAX_CHARS] for i in range(0, len(content), MAX_CHARS)]

    children = []
    for chunk in chunks:
        children.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": chunk}}]
                },
            }
        )

    # Notion APIの制限への対応
    # 1回のリクエストで送信できるブロック数は最大100個までです。
    BATCH_SIZE = 100
    success = True

    for i in range(0, len(children), BATCH_SIZE):
        batch = children[i : i + BATCH_SIZE]
        response = await safe_api_call(
            "PATCH", f"blocks/{page_id}/children", json={"children": batch}
        )
        if not response:
            success = False

    return success


async def query_database(database_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    データベースのクエリ実行

    最終更新日時の降順でソートしてデータを取得します。
    データベースコンテンツのプレビュー用などに使用されます。
    """
    body = {
        "page_size": limit,
        "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
    }
    # データベース検索は時間がかかることがあるため、タイムアウトを60秒に延長
    response = await safe_api_call(
        "POST", f"databases/{database_id}/query", json=body, timeout=60.0
    )
    if not response:
        return []
    return response.get("results", [])


async def update_page_properties(page_id: str, properties: Dict[str, Any]) -> bool:
    """
    ページのプロパティを更新

    既存のページのタイトルやその他のプロパティを更新します。

    Args:
        page_id (str): 更新対象のページID
        properties (Dict): 更新するプロパティ（Notion API形式）
            例: {"title": {"title": [{"text": {"content": "新しいタイトル"}}]}}

    Returns:
        bool: 更新が成功した場合True

    Examples:
        # タイトルを更新
        >>> await update_page_properties(
        ...     page_id="abc123",
        ...     properties={
        ...         "Name": {"title": [{"text": {"content": "新しいタイトル"}}]}
        ...     }
        ... )
    """
    body = {"properties": properties}

    response = await safe_api_call("PATCH", f"pages/{page_id}", json=body)
    return response is not None
