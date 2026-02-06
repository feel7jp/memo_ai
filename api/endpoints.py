"""
エンドポイント定義 (API Routes)

System系およびNotion参照系エンドポイントを定義します。
段階的移行: Step 1 - System系（health, config, models）
            Step 2 - Notion参照系（targets, schema, content×3）
"""

from fastapi import APIRouter, HTTPException, Request
import os
import asyncio

# グローバル変数（index.pyから参照）
from api.config import (
    DEBUG_MODE,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEXT_MODEL,
    DEFAULT_MULTIMODAL_MODEL,
    NOTION_BLOCK_CHAR_LIMIT,
    NOTION_CONTENT_MAX_LENGTH,
)
from api.notion import (
    fetch_config_db,
    fetch_children_list,
    get_db_schema,
    get_page_info,
    safe_api_call,
    fetch_recent_pages,
)
from api.models import get_available_models, get_text_models, get_vision_models
from api.schemas import AnalyzeRequest, ChatRequest, SaveRequest

# rate_limiterはindex.pyから参照が必要（循環参照回避のため）
# この変数はindex.pyで初期化後、endpoints使用前にセットする必要がある
rate_limiter = None

# FastAPI Router
router = APIRouter()


# ===== System系エンドポイント =====


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

        return {
            "all": all_models,
            "text_only": text_only,
            "vision_capable": vision_capable,
            "defaults": {
                "text": DEFAULT_TEXT_MODEL,
                "multimodal": DEFAULT_MULTIMODAL_MODEL,
            },
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
        print(f"[Schema Fetch] Database fetch error: {e}")

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
        print(f"[Schema Fetch] Page fetch error: {e}")

    print(f"[Schema Fetch] Both database and page fetch failed for {target_id}")
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


# --- AI系エンドポイント (Step 3) ---


@router.post("/api/analyze")
async def analyze_endpoint(request: Request, analyze_req: AnalyzeRequest):
    """
    テキスト分析API (AIによるタスク抽出)

    Notionのデータベース構造（スキーマ）と既存のデータを参照し、
    ユーザーのテキスト入力からデータベースに登録するための適切なプロパティ値をAIに推定させます。
    """
    from api.ai import analyze_text_with_ai
    from api.services import get_current_jst_str
    import httpx

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
            print(f"Error fetching schema: {schema}")
            schema = {}
        if isinstance(recent_examples, Exception):
            print(f"Error fetching recent examples: {recent_examples}")
            recent_examples = []

    except Exception as e:
        print(f"Parallel fetch failed: {e}")
        schema = {}
        recent_examples = []

    # 2. システムプロンプトの準備
    system_prompt = analyze_req.system_prompt
    if not system_prompt:
        system_prompt = "You are a helpful assistant."

    current_time_str = get_current_jst_str()
    system_prompt = f"Current Time: {current_time_str}\\n\\n{system_prompt}"

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
        print(f"[AI Analysis Error] {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()

        detail = {"error": "AI analysis failed"}
        if DEBUG_MODE:
            detail["message"] = str(e)
            detail["type"] = type(e).__name__
        else:
            detail["message"] = "AIの処理中にエラーが発生しました"
        detail["suggestions"] = [
            "しばらく待ってから再試行してください",
            "問題が続く場合は管理者にお問い合わせください",
        ]
        raise HTTPException(status_code=500, detail=detail)


@router.post("/api/chat")
async def chat_endpoint(request: Request, chat_req: ChatRequest):
    """
    チャットAIエンドポイント (対話機能)

    特定のNotionページやデータベースをコンテキストとして、AIと会話を行います。
    画像入力や履歴を踏まえた回答が可能です。
    """
    from api.ai import chat_analyze_text_with_ai
    from api.services import get_current_jst_str
    import httpx

    await rate_limiter.check_rate_limit(request, endpoint="chat")

    print(f"[Chat] Request received for target: {chat_req.target_id}")
    print(f"[Chat] Has image: {bool(chat_req.image_data)}")
    print(f"[Chat] Text length: {len(chat_req.text) if chat_req.text else 0}")

    try:
        target_id = chat_req.target_id

        print(f"[Chat] Fetching schema for target: {target_id}")
        try:
            schema_result = await get_schema(target_id, request)
            schema = schema_result.get("schema", {})
            target_type = schema_result.get("type", "database")
            print(
                f"[Chat] Schema fetched, type: {target_type}, properties: {len(schema)}"
            )
        except Exception as schema_error:
            print(f"[Chat] Schema fetch error: {schema_error}")
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
        system_prompt = f"Current Time: {current_time_str}\\n\\n{system_prompt}"

        session_history = chat_req.session_history or []
        if chat_req.reference_context:
            session_history = [
                {"role": "system", "content": chat_req.reference_context}
            ] + session_history

        print(f"[Chat] Calling AI with model: {chat_req.model or 'auto'}")
        try:
            result = await chat_analyze_text_with_ai(
                text=chat_req.text,
                schema=schema,
                system_prompt=system_prompt,
                session_history=session_history,
                image_data=chat_req.image_data,
                image_mime_type=chat_req.image_mime_type,
                model=chat_req.model,
            )
            print(f"[Chat] AI response received, model used: {result.get('model')}")
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
            print(f"[Chat AI Error] {type(ai_error).__name__}: {ai_error}")
            import traceback

            traceback.print_exc()

            detail = {"error": "Chat AI failed"}
            if DEBUG_MODE:
                detail["message"] = str(ai_error)
                detail["type"] = type(ai_error).__name__
            else:
                detail["message"] = "チャット処理中にエラーが発生しました"
            detail["suggestions"] = ["しばらく待ってから再試行してください"]
            raise HTTPException(status_code=500, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Chat Endpoint Error] {e}")
        import traceback

        traceback.print_exc()

        detail = {"error": "Unexpected error"}
        if DEBUG_MODE:
            detail["message"] = str(e)
            detail["type"] = type(e).__name__
        else:
            detail["message"] = "予期しないエラーが発生しました"
        raise HTTPException(status_code=500, detail=detail)


# --- Update系エンドポイント (Step 4) ---


@router.post("/api/save")
async def save_endpoint(save_req: SaveRequest):
    """
    保存実行API

    ユーザーが承認した内容を実際にNotionに書き込みます。
    ページへの追記（ブロック追加）と、データベースへの新規アイテム作成の両方に対応しています。
    """
    from api.notion import append_block, create_page
    from api.services import sanitize_image_data

    try:
        if save_req.target_type == "page":
            content = save_req.text or "No content"
            if "Content" in save_req.properties:
                c_obj = save_req.properties["Content"]
                if "rich_text" in c_obj:
                    content = c_obj["rich_text"][0]["text"]["content"]

            content = sanitize_image_data(content)

            if len(content) > NOTION_CONTENT_MAX_LENGTH:
                print(
                    f"[Save] Warning: Extremely large content ({len(content)} chars). Truncating."
                )
                content = content[:10000] + "\n...(Truncated)..."

            await append_block(save_req.target_db_id, content)
            return {"status": "success", "url": ""}
        else:
            sanitized_props = save_req.properties.copy()

            def sanitize_val(val):
                if isinstance(val, str):
                    return sanitize_image_data(val)
                return val

            for key, val in sanitized_props.items():
                if isinstance(val, dict):
                    if "rich_text" in val and val["rich_text"]:
                        new_rich_text = []
                        for item in val["rich_text"]:
                            if "text" in item:
                                content = sanitize_val(item["text"]["content"])
                                if len(content) > NOTION_BLOCK_CHAR_LIMIT:
                                    for i in range(
                                        0, len(content), NOTION_BLOCK_CHAR_LIMIT
                                    ):
                                        new_item = item.copy()
                                        new_item["text"] = item["text"].copy()
                                        new_item["text"]["content"] = content[
                                            i : i + NOTION_BLOCK_CHAR_LIMIT
                                        ]
                                        new_rich_text.append(new_item)
                                else:
                                    item["text"]["content"] = content
                                    new_rich_text.append(item)
                            else:
                                new_rich_text.append(item)
                        val["rich_text"] = new_rich_text

                    if "title" in val and val["title"]:
                        new_title = []
                        for item in val["title"]:
                            if "text" in item:
                                content = sanitize_val(item["text"]["content"])
                                if len(content) > NOTION_BLOCK_CHAR_LIMIT:
                                    for i in range(
                                        0, len(content), NOTION_BLOCK_CHAR_LIMIT
                                    ):
                                        new_item = item.copy()
                                        new_item["text"] = item["text"].copy()
                                        new_item["text"]["content"] = content[
                                            i : i + NOTION_BLOCK_CHAR_LIMIT
                                        ]
                                        new_title.append(new_item)
                                else:
                                    item["text"]["content"] = content
                                    new_title.append(item)
                            else:
                                new_title.append(item)
                        val["title"] = new_title

            url = await create_page(save_req.target_db_id, sanitized_props)
            return {"status": "success", "url": url}
    except Exception as e:
        print(f"[Save Error] {e}")
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
        print(f"[Update Page Error] {e}")
        import traceback

        traceback.print_exc()
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
        print(f"[Create Page Error] {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"ページ作成に失敗しました: {str(e)}"
        )
