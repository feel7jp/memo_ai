"""
エンドポイント定義 (API Routes)

全APIルート（System系、Notion参照系、AI処理系、Update系）を定義します。
エラーレスポンスは _build_error_detail() で統一的に構築されます。
"""

from fastapi import APIRouter, HTTPException, Request
import os
import asyncio

import httpx

from api.logger import setup_logger
from api.config import (
    DEBUG_MODE,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEXT_MODEL,
    DEFAULT_MULTIMODAL_MODEL,
    NOTION_CONTENT_MAX_LENGTH,
)
from api.services import extract_plain_text, get_current_jst_str
from api.notion import (
    fetch_config_db,
    fetch_children_list,
    get_db_schema,
    get_page_info,
    safe_api_call,
    fetch_recent_pages,
)
from api.models import (
    get_available_models,
    get_text_models,
    get_vision_models,
    get_image_generation_models,
    _PROVIDER_ERRORS,
)
from api.schemas import AnalyzeRequest, ChatRequest, SaveRequest
from api.rate_limiter import rate_limiter

logger = setup_logger(__name__)


def _build_error_detail(
    error_key: str,
    exception: Exception,
    fallback_message: str,
    suggestions: list | None = None,
) -> dict:
    """
    エラーレスポンス用のdetail辞書を構築する。

    DEBUG_MODE有効時は例外の詳細情報を含め、
    無効時は日本語のフォールバックメッセージを返す。
    """
    detail = {"error": error_key}
    if DEBUG_MODE:
        detail["message"] = str(exception)
        detail["type"] = type(exception).__name__
    else:
        detail["message"] = fallback_message
    if suggestions:
        detail["suggestions"] = suggestions
    return detail


# FastAPI Router
router = APIRouter()


# ===== System Endpoints =====


@router.get("/api/health")
def health_check():
    """
    ヘルスチェック用エンドポイント

    サーバーが正常に稼働しているかを確認するために監視サービス等から叩かれます。
    """
    return {"status": "ok"}


@router.get("/api/config")
async def get_config():
    """
    設定情報の取得

    NotionのConfigデータベースから、アプリの設定（プロンプト一覧など）を取得します。
    """
    # APP_CONFIGはindex.pyのグローバル変数なので、ここでは直接アクセスできない
    # そのため、環境変数から取得する
    debug_mode = DEBUG_MODE

    config_db_id = os.environ.get("NOTION_CONFIG_DB_ID")

    if not config_db_id:
        # 設定DBがない場合でもdebug_modeは返す
        return {
            "configs": [],
            "debug_mode": debug_mode,
            "default_system_prompt": DEFAULT_SYSTEM_PROMPT,
        }

    configs = await fetch_config_db(config_db_id)

    return {
        "configs": configs,
        "debug_mode": debug_mode,
        "default_system_prompt": DEFAULT_SYSTEM_PROMPT,
    }


@router.get("/api/models")
async def get_models(all: bool = False):
    """
    利用可能なAIモデル一覧の取得

    テキスト専用モデルとマルチモーダル（画像対応）モデルに分類して返します。
    フロントエンドでユーザーがモデルを選択する際に使用されます。

    Args:
        all: True の場合、全モデルを返す。False（デフォルト）の場合、推奨モデルのみ。
    """
    try:
        from fastapi.concurrency import run_in_threadpool

        # モデル探索は外部API呼び出しを含む重い処理（かつ同期関数）なので、
        # スレッドプールで実行してメインループをブロックしないようにします。
        # これにより、Notion読み込みなどの他のリクエストが待たされるのを防ぎます。
        all_models = await run_in_threadpool(
            get_available_models, recommended_only=not all
        )

        # 以下のフィルタリング等はメモリ上の処理なので高速
        text_only = get_text_models()
        vision_capable = get_vision_models()

        # デフォルトモデルの可用性チェック
        from api.models import check_default_model_availability

        text_availability = check_default_model_availability(DEFAULT_TEXT_MODEL)
        multimodal_availability = check_default_model_availability(
            DEFAULT_MULTIMODAL_MODEL
        )

        # 画像生成モデルの可用性チェック
        # 画像生成には特定のデフォルトがないため、利用可能な画像生成モデルの有無で判定
        image_gen_models = get_image_generation_models()
        if image_gen_models:
            # 最もよく使われる画像生成モデル（存在する場合はgemini-2.5-flash-image）
            first_image_gen_model = image_gen_models[0]
            image_generation_availability = {
                "available": True,
                "model": first_image_gen_model["id"],
            }
        else:
            image_generation_availability = {
                "available": False,
                "model": "Unknown",
                "error": "No image generation models available. Check API keys.",
            }

        return {
            "all": all_models,
            "text_only": text_only,
            "vision_capable": vision_capable,
            "image_generation_capable": image_gen_models,
            "default_text_model": DEFAULT_TEXT_MODEL,
            "default_multimodal_model": DEFAULT_MULTIMODAL_MODEL,
            "text_availability": text_availability,
            "multimodal_availability": multimodal_availability,
            "image_generation_availability": image_generation_availability,
            **({"provider_errors": _PROVIDER_ERRORS} if _PROVIDER_ERRORS else {}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== Notion参照系エンドポイント =====


@router.get("/api/targets")
async def get_targets(request: Request):
    """
    操作対象（Notionページ/データベース）一覧の取得

    ルートページ直下にあるページやデータベース、およびリンクされているページを取得します。
    これらはユーザーがメモの保存先やチャットのコンテキストとして選択する候補となります。
    """
    # レート制限チェック
    await rate_limiter.check_rate_limit(request, endpoint="targets")
    root_id = os.environ.get("NOTION_ROOT_PAGE_ID")
    if not root_id:
        raise HTTPException(
            status_code=500,
            detail="❌ NOTION_ROOT_PAGE_ID が設定されていません。.envファイルに NOTION_ROOT_PAGE_ID=your_page_id を追加してください。",
        )

    children = await fetch_children_list(root_id)
    targets = []

    async def process_block(block):
        """1つのブロック情報を解析してターゲット形式に変換する内部関数"""
        b_type = block.get("type")

        if b_type == "child_database":
            info = block.get("child_database", {})
            return {
                "id": block["id"],
                "type": "database",
                "title": info.get("title", "Untitled Database"),
            }
        elif b_type == "child_page":
            info = block.get("child_page", {})
            return {
                "id": block["id"],
                "type": "page",
                "title": info.get("title", "Untitled Page"),
            }
        elif b_type == "link_to_page":
            info = block.get("link_to_page", {})
            target_type = info.get("type")
            target_id = info.get(target_type)

            if target_type == "page_id":
                page = await get_page_info(target_id)
                if page:
                    props = page.get("properties", {})
                    title_plain = "Untitled Linked Page"
                    for k, v in props.items():
                        if v["type"] == "title" and v["title"]:
                            title_plain = v["title"][0]["plain_text"]
                            break
                    return {
                        "id": target_id,
                        "type": "page",
                        "title": title_plain + " (Link)",
                    }
            elif target_type == "database_id":
                db = await safe_api_call("GET", f"databases/{target_id}")
                if db:
                    title_obj = db.get("title", [])
                    title_plain = (
                        title_obj[0]["plain_text"]
                        if title_obj
                        else "Untitled Linked DB"
                    )
                    return {
                        "id": target_id,
                        "type": "database",
                        "title": title_plain + " (Link)",
                    }
        return None

    results = await asyncio.gather(*[process_block(block) for block in children])
    targets = [res for res in results if res]

    return {"targets": targets}


@router.get("/api/schema/{target_id}")
async def get_schema(target_id: str, request: Request):
    """
    対象（DBまたはページ）のスキーマ情報の取得

    ページの場合は単純な構造を返し、データベースの場合は各プロパティ（列）の定義を返します。
    """
    await rate_limiter.check_rate_limit(request, endpoint="schema")
    db_error = None
    page_error = None

    try:
        db = await get_db_schema(target_id)
        return {"type": "database", "schema": db}
    except ValueError as e:
        db_error = str(e)
    except Exception as e:
        db_error = str(e)

    try:
        page = await get_page_info(target_id)
        if page:
            return {
                "type": "page",
                "schema": {
                    "Title": {"type": "title"},
                    "Content": {"type": "rich_text"},
                },
            }
        else:
            page_error = f"Target {target_id} not found as Page (returned None)"
    except Exception as e:
        page_error = str(e)

    raise HTTPException(
        status_code=404,
        detail={
            "error": "Schema fetch failed",
            "target_id": target_id,
            "attempted": ["database", "page"],
            "database_error": db_error or "Unknown",
            "page_error": page_error or "Unknown",
        },
    )


@router.get("/api/content/{page_id}")
async def get_content(page_id: str, request: Request, type: str = "page"):
    """
    ページまたはデータベースのコンテンツ取得

    AIの参照コンテキストとして使用するため、Notionページのブロック内容や
    データベースのエントリをプレーンテキストに変換して返します。

    Args:
        page_id: NotionページまたはデータベースのID
        type: "page" または "database"

    Returns:
        {
            "content": "フォーマットされたテキストコンテンツ"
        }
    """
    from api.notion import query_database

    # レート制限チェック
    await rate_limiter.check_rate_limit(request, endpoint="content")

    try:
        if type == "database":
            # データベースの場合：最近のエントリを取得してフォーマット

            entries = await query_database(page_id, limit=20)

            if not entries:
                return {"content": "データベースにエントリがありません。"}

            # エントリをテキスト形式に変換
            lines = [f"=== データベースコンテンツ (最新{len(entries)}件) ===\n"]

            for idx, entry in enumerate(entries, 1):
                props = entry.get("properties", {})
                entry_parts = [f"## エントリ {idx}"]

                # 各プロパティを抽出
                for prop_name, prop_data in props.items():
                    prop_type = prop_data.get("type")
                    value = None

                    if prop_type == "title":
                        title_objs = prop_data.get("title", [])
                        value = extract_plain_text(title_objs)
                    elif prop_type == "rich_text":
                        text_objs = prop_data.get("rich_text", [])
                        value = extract_plain_text(text_objs)
                    elif prop_type == "select":
                        select_obj = prop_data.get("select")
                        value = select_obj.get("name") if select_obj else None
                    elif prop_type == "multi_select":
                        options = prop_data.get("multi_select", [])
                        value = ", ".join([o.get("name", "") for o in options])
                    elif prop_type == "status":
                        status_obj = prop_data.get("status")
                        value = status_obj.get("name") if status_obj else None
                    elif prop_type == "date":
                        date_obj = prop_data.get("date")
                        value = date_obj.get("start") if date_obj else None
                    elif prop_type == "checkbox":
                        value = "✓" if prop_data.get("checkbox") else "✗"
                    elif prop_type == "number":
                        value = prop_data.get("number")

                    if value:
                        entry_parts.append(f"- {prop_name}: {value}")

                lines.append("\n".join(entry_parts))
                lines.append("")  # 空行

            content_text = "\n".join(lines)

            return {"content": content_text}

        else:
            # ページの場合：ブロック内容を取得してテキスト化

            blocks = await fetch_children_list(page_id, limit=100)

            if not blocks:
                return {"content": "ページにコンテンツがありません。"}

            # ブロックをプレーンテキストに変換
            lines = ["=== ページコンテンツ ===\n"]

            for block in blocks:
                block_type = block.get("type")

                # テキストを含む主要なブロックタイプを処理
                if block_type == "paragraph":
                    paragraph = block.get("paragraph", {})
                    text_objs = paragraph.get("rich_text", [])
                    text = extract_plain_text(text_objs)
                    if text.strip():
                        lines.append(text)

                elif block_type in ["heading_1", "heading_2", "heading_3"]:
                    heading = block.get(block_type, {})
                    text_objs = heading.get("rich_text", [])
                    text = extract_plain_text(text_objs)
                    if text.strip():
                        # 見出しレベルに応じてマークダウン記号を追加
                        prefix = "#" * int(block_type[-1])
                        lines.append(f"\n{prefix} {text}")

                elif block_type == "bulleted_list_item":
                    item = block.get("bulleted_list_item", {})
                    text_objs = item.get("rich_text", [])
                    text = extract_plain_text(text_objs)
                    if text.strip():
                        lines.append(f"• {text}")

                elif block_type == "numbered_list_item":
                    item = block.get("numbered_list_item", {})
                    text_objs = item.get("rich_text", [])
                    text = extract_plain_text(text_objs)
                    if text.strip():
                        lines.append(f"1. {text}")

                elif block_type == "to_do":
                    todo = block.get("to_do", {})
                    text_objs = todo.get("rich_text", [])
                    text = extract_plain_text(text_objs)
                    checked = todo.get("checked", False)
                    checkbox = "[x]" if checked else "[ ]"
                    if text.strip():
                        lines.append(f"{checkbox} {text}")

                elif block_type == "quote":
                    quote = block.get("quote", {})
                    text_objs = quote.get("rich_text", [])
                    text = extract_plain_text(text_objs)
                    if text.strip():
                        lines.append(f"> {text}")

                elif block_type == "code":
                    code = block.get("code", {})
                    text_objs = code.get("rich_text", [])
                    text = extract_plain_text(text_objs)
                    language = code.get("language", "")
                    if text.strip():
                        lines.append(f"```{language}\n{text}\n```")

            content_text = "\n".join(lines)

            return {"content": content_text}

    except Exception as e:
        logger.error("[Content Error] %s: %s", type(e).__name__, e, exc_info=True)


        # エラー時は空のコンテンツを返して処理を続行
        # （参照コンテキストがなくてもチャットは機能すべき）
        return {"content": f"コンテンツの取得中にエラーが発生しました: {str(e)}"}


# --- AI Endpoints ---


@router.post("/api/analyze")
async def analyze_endpoint(request: Request, analyze_req: AnalyzeRequest):
    """
    テキスト分析API (AIによるタスク抽出)

    Notionのデータベース構造（スキーマ）と既存のデータを参照し、
    ユーザーのテキスト入力からデータベースに登録するための適切なプロパティ値をAIに推定させます。
    """
    from api.ai import analyze_text_with_ai

    # レート制限チェック
    await rate_limiter.check_rate_limit(request, endpoint="analyze")

    target_db_id = analyze_req.target_db_id

    # 1. データベース情報の並行取得
    try:
        results = await asyncio.gather(
            get_db_schema(target_db_id),
            fetch_recent_pages(target_db_id, limit=3),
            return_exceptions=True,
        )

        schema = results[0]
        recent_examples = results[1]

        if isinstance(schema, Exception):
            logger.warning("Error fetching schema: %s", schema)
            schema = {}
        if isinstance(recent_examples, Exception):
            logger.warning("Error fetching recent examples: %s", recent_examples)
            recent_examples = []

    except Exception as e:
        logger.warning("Parallel fetch failed: %s", e)
        schema = {}
        recent_examples = []

    # 2. システムプロンプトの準備
    system_prompt = analyze_req.system_prompt
    if not system_prompt:
        system_prompt = "You are a helpful assistant."

    current_time_str = get_current_jst_str()
    system_prompt = f"Current Time: {current_time_str}\n\n{system_prompt}"

    # 3. AIによる分析実行
    try:
        result = await analyze_text_with_ai(
            text=analyze_req.text,
            schema=schema,
            recent_examples=recent_examples,
            system_prompt=system_prompt,
            model=analyze_req.model,
        )
        return result
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail={
                "error": "Notion API Timeout",
                "message": "Notion APIの応答がタイムアウトしました。しばらく待ってから再試行してください。",
                "suggestions": [
                    "Notionのステータスを確認してください",
                    "しばらく待ってから再試行してください",
                ],
            },
        )
    except Exception as e:
        logger.error("[AI Analysis Error] %s: %s", type(e).__name__, e, exc_info=True)


        raise HTTPException(
            status_code=500,
            detail=_build_error_detail(
                "AI analysis failed", e, "AIの処理中にエラーが発生しました",
                ["しばらく待ってから再試行してください", "問題が続く場合は管理者にお問い合わせください"],
            ),
        )


@router.post("/api/chat")
async def chat_endpoint(request: Request, chat_req: ChatRequest):
    """
    チャットAIエンドポイント (対話機能)

    特定のNotionページやデータベースをコンテキストとして、AIと会話を行います。
    画像入力や履歴を踏まえた回答が可能です。
    """
    from api.ai import chat_analyze_text_with_ai

    await rate_limiter.check_rate_limit(request, endpoint="chat")

    try:
        target_id = chat_req.target_id

        try:
            schema_result = await get_schema(target_id, request)
            schema = schema_result.get("schema", {})

        except Exception as schema_error:
            logger.warning("[Chat] Schema fetch error: %s", schema_error)
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Schema fetch failed",
                    "message": str(schema_error),
                    "suggestions": [
                        "ターゲットIDが正しいか確認してください",
                        "Notion APIキーの権限を確認してください",
                    ],
                },
            )

        system_prompt = chat_req.system_prompt
        if not system_prompt:
            system_prompt = DEFAULT_SYSTEM_PROMPT

        current_time_str = get_current_jst_str()
        system_prompt = f"Current Time: {current_time_str}\n\n{system_prompt}"

        session_history = chat_req.session_history or []
        if chat_req.reference_context:
            session_history = [
                {"role": "system", "content": chat_req.reference_context}
            ] + session_history

        try:
            result = await chat_analyze_text_with_ai(
                text=chat_req.text,
                schema=schema,
                system_prompt=system_prompt,
                session_history=session_history,
                image_data=chat_req.image_data,
                image_mime_type=chat_req.image_mime_type,
                model=chat_req.model,
                image_generation=chat_req.image_generation or False,
            )

            return result
        except httpx.ReadTimeout:
            raise HTTPException(
                status_code=504,
                detail={
                    "error": "Notion API Timeout",
                    "message": "Notion APIの応答がタイムアウトしました。",
                    "type": "ReadTimeout",
                },
            )
        except Exception as ai_error:
            logger.error("[Chat AI Error] %s: %s", type(ai_error).__name__, ai_error, exc_info=True)
    

            raise HTTPException(
                status_code=500,
                detail=_build_error_detail(
                    "Chat AI failed", ai_error, "チャット処理中にエラーが発生しました",
                    ["しばらく待ってから再試行してください"],
                ),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Chat Endpoint Error] %s", e, exc_info=True)


        raise HTTPException(
            status_code=500,
            detail=_build_error_detail(
                "Unexpected error", e, "予期しないエラーが発生しました",
            ),
        )


# --- Update系エンドポイント (Step 4) ---


@router.post("/api/save")
async def save_endpoint(save_req: SaveRequest):
    """
    保存実行API

    ユーザーが承認した内容を実際にNotionに書き込みます。
    ページへの追記（ブロック追加）と、データベースへの新規アイテム作成の両方に対応しています。
    """
    from api.notion import append_block, create_page
    from api.services import (
        sanitize_image_data,
        sanitize_notion_properties,
        ensure_title_property,
        create_content_blocks,
    )

    try:
        if save_req.target_type == "page":
            # Page: テキスト追記
            content = save_req.text or "No content"
            if "Content" in save_req.properties:
                c_obj = save_req.properties["Content"]
                if "rich_text" in c_obj:
                    content = c_obj["rich_text"][0]["text"]["content"]

            content = sanitize_image_data(content)
            if len(content) > NOTION_CONTENT_MAX_LENGTH:
                logger.warning(
                    "[Save] Content too large (%d chars). Truncating.", len(content)
                )
                content = content[:10000] + "\n...(Truncated)..."

            await append_block(save_req.target_db_id, content)
            return {"status": "success", "url": ""}
        else:
            # Database: 新規ページ作成
            props = sanitize_notion_properties(save_req.properties)
            props = ensure_title_property(props, save_req.text)
            children = create_content_blocks(save_req.text)

            url = await create_page(save_req.target_db_id, props, children)
            return {"status": "success", "url": url}
    except Exception as e:
        logger.error("[Save Error] %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to save to Notion: {str(e)}"
        )


@router.patch("/api/pages/{page_id}")
async def update_page(page_id: str, request: Request):
    """
    ページのプロパティを更新

    ページのタイトルやその他のプロパティを更新します。
    リクエストボディ例:
    {
        "properties": {
            "Name": {"title": [{"text": {"content": "新しいタイトル"}}]}
        }
    }
    """
    from api.notion import update_page_properties

    # レート制限チェック
    await rate_limiter.check_rate_limit(
        request, endpoint="update_page", custom_limit=20
    )

    try:
        body = await request.json()
        properties = body.get("properties", {})

        if not properties:
            raise HTTPException(
                status_code=400, detail="プロパティが指定されていません"
            )

        # ページプロパティの更新
        success = await update_page_properties(page_id, properties)

        if success:
            return {
                "status": "success",
                "message": "ページを更新しました",
                "page_id": page_id,
            }
        else:
            raise HTTPException(status_code=500, detail="ページの更新に失敗しました")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Update Page Error] %s", e, exc_info=True)

        raise HTTPException(status_code=500, detail=f"ページ更新エラー: {str(e)}")


@router.post("/api/pages/create")
async def create_page_endpoint(request: dict):
    """
    新規ページの作成API

    ルートページ直下に新しい空のページを作成します。
    """
    import os

    try:
        page_name = request.get("page_name", "").strip()

        if not page_name:
            raise HTTPException(status_code=400, detail="ページ名が必要です")

        root_id = os.environ.get("NOTION_ROOT_PAGE_ID")
        if not root_id:
            raise HTTPException(
                status_code=500,
                detail="❌ NOTION_ROOT_PAGE_ID が設定されていません。",
            )

        new_page = await safe_api_call(
            "POST",
            "pages",
            json={
                "parent": {"type": "page_id", "page_id": root_id},
                "properties": {"title": {"title": [{"text": {"content": page_name}}]}},
            },
        )

        if not new_page:
            raise Exception("Failed to create page")

        return {"id": new_page["id"], "title": page_name, "type": "page"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Create Page Error] %s", e, exc_info=True)

        raise HTTPException(
            status_code=500, detail=f"ページ作成に失敗しました: {str(e)}"
        )
