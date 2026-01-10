import os
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import json
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python 3.9以降では標準ライブラリですが、古いバージョンのためのバックポート対応
    # Backport for Python 3.8 or older if needed, though 3.9+ has zoneinfo
    from backports.zoneinfo import ZoneInfo

from contextlib import asynccontextmanager
import httpx

# --- 自作モジュールのインポート ---
# Notion APIとの通信を担当する関数群
from api.notion import fetch_config_db, get_db_schema, fetch_recent_pages, create_page, fetch_children_list, get_page_info, safe_api_call, append_block, query_database
# AI（Gemini等）との連携を担当する関数群
from api.ai import analyze_text_with_ai, chat_analyze_text_with_ai
# 使用可能なAIモデル定義
from api.models import get_available_models, get_text_models, get_vision_models
# アプリケーションのデフォルト設定
from api.config import DEFAULT_TEXT_MODEL, DEFAULT_MULTIMODAL_MODEL


# 環境変数の読み込み (.envファイルの内容をロード)
if not Path(".env").exists():
    raise FileNotFoundError("❌ .envファイルが見つかりません。プロジェクトのルートディレクトリに .env ファイルを作成してください。")
load_dotenv()

# --- グローバル変数 ---
# アプリケーション全体で共有する設定値などを保持する辞書
APP_CONFIG = {"config_db_id": None}

# --- ライフスパンイベント (Lifespan Events) ---
# FastAPIアプリケーションの起動時と終了時に実行される処理を定義します。
# 以前の @app.on_event("startup") の代わりとなるモダンな書き方です。
@asynccontextmanager
async def lifespan(app: FastAPI):
    import socket
    
    # 起動時のログ出力
    # アプリケーションの状態や環境情報をコンソールに表示して、デバッグを容易にします。
    print("\n" + "=" * 70)
    print("🚀 Memo AI サーバーを起動しています...")
    print("=" * 70)
    
    # Vercel環境かローカル環境かを判定
    is_vercel = os.environ.get('VERCEL')
    if is_vercel:
        print(f"📦 環境: Vercel (Production)")
    else:
        print(f"💻 環境: ローカル開発環境")
    
    print(f"📁 作業ディレクトリ: {os.getcwd()}")
    print(f"🐍 Python バージョン: {os.sys.version.split()[0]}")
    
    # 静的ファイルディレクトリの存在確認
    # ローカル環境とVercel環境でパスが異なる可能性があるため、複数の候補をチェックします。
    if not is_vercel:
        # ローカル環境でのみ詳細チェック
        static_paths = ["public"]
        for path in static_paths:
            exists = os.path.exists(path)
            if exists and os.path.isdir(path):
                try:
                    files = os.listdir(path)
                    print(f"📂 静的ファイル: {path}/ ({len(files)}個のファイル)")
                except Exception as e:
                    print(f"⚠️  静的ファイルの読み込みエラー: {e}")
    
    print("=" * 70)
    
    # ローカルIPアドレスの取得と起動URL表示
    # スマホなどから同じネットワーク内のPCで動いているサーバーにアクセスする際のURLを表示します。
    if not is_vercel:
        # ポート番号を環境変数またはコマンドライン引数から取得
        # 1. PORT環境変数をチェック
        # 2. コマンドライン引数の --port オプションをチェック
        # 3. デフォルト値 8000 を使用
        port = os.environ.get("PORT")
        if not port:
            import sys
            # sys.argvから --port 引数を探す
            for i, arg in enumerate(sys.argv):
                if arg == "--port" and i + 1 < len(sys.argv):
                    port = sys.argv[i + 1]
                    break
        if not port:
            port = "8000"
        
        print("")
        print("✅ サーバーが起動しました！")
        print("")
        print("📍 アクセスURL:")
        print(f"   ├─ ローカル:    http://localhost:{port}")
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            print(f"   └─ スマホから:  http://{local_ip}:{port}")
        except Exception:
            print("   └─ スマホから:  (IPアドレス取得失敗)")
        
        print("")
        print("💡 サーバーを停止するには: Ctrl + C を押してください")
        print("=")

    # 環境変数の簡易チェック
    if not is_vercel:
        page_id = os.environ.get("NOTION_ROOT_PAGE_ID", "")
        if page_id and ("-" in page_id or "http" in page_id or len(page_id) < 20):
            print(f"⚠️  NOTION_ROOT_PAGE_ID が不正な可能性: {page_id[:30]}... (ハイフン/URL除外, NotionページURLから32文字の英数字のみ抽出)")
    
    yield
    # yieldより後のコードはアプリケーション終了時に実行されます (シャットダウン処理)
    # ここでは特に処理は記述していません。

# FastAPIアプリケーションのインスタンス作成
app = FastAPI(lifespan=lifespan)

# --- CORS (Cross-Origin Resource Sharing) 設定 ---
# 異なるオリジン（ドメイン、ポート）からのリクエストを許可するための設定です。
# 開発中は "*" で全て許可し、フロントエンドとバックエンドの通信を容易にします。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ヘルパー関数 (Helper Functions) ---

def sanitize_image_data(text: str) -> str:
    """
    テキストコンテンツからBase64形式の画像データを除去します。
    
    Notionに送信する際、長大なBase64文字列が含まれているとエラーやパフォーマンス低下の原因になるため、
    正規表現を使ってこれらを削除または置換します。
    Markdown形式の画像リンクとHTML形式のimgタグの両方に対応しています。
    """
    import re
    # Markdown形式の画像 (data URIスキーム) を削除: ![alt](data:image/png;base64,...)
    text = re.sub(r'!\[.*?\]\(data:image\/.*?\)', '', text, flags=re.DOTALL)
    # HTML形式のimgタグ (data URIスキーム) を削除: <img src="data:image/..." ...>
    text = re.sub(r'<img[^>]+src=["\']data:image\/[^"\']+["\'][^>]*>', '', text, flags=re.DOTALL)
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

# --- Pydanticモデル定義 (データバリデーション用) ---
# APIのリクエストボディの構造を定義し、型チェックと自動ドキュメント生成を行います。

class AnalyzeRequest(BaseModel):
    """テキスト分析用・タスク抽出用のリクエストモデル"""
    text: str                  # ユーザーの入力テキスト
    target_db_id: str          # 対象のNotionデータベースID
    system_prompt: str         # AIへの指示（システムプロンプト）
    model: Optional[str] = None # 使用するAIモデル（指定がなければデフォルト）

class SaveRequest(BaseModel):
    """Notionへの保存用リクエストモデル"""
    target_db_id: str          # 保存先のデータベースID または ページID
    target_type: Optional[str] = "database" # 'database' (データベースに行を追加) or 'page' (ページにブロックを追加)
    properties: Dict[str, Any] # 保存するプロパティ（タイトル、日付、タグなど）
    text: Optional[str] = None # ページに追加する場合の本文テキスト

class ChatRequest(BaseModel):
    """チャット対話用のリクエストモデル"""
    text: Optional[str] = ""   # ユーザーのメッセージ (画像のみの場合は空文字も許容)
    target_id: str             # 会話のコンテキストとなるNotionページ/DBのID
    system_prompt: Optional[str] = None # AIへの振る舞いの指示
    session_history: Optional[List[Dict[str, str]]] = None # 会話履歴 (メモリ機能)
    reference_context: Optional[str] = None # 参照中のページ内容などの追加コンテキスト
    image_data: Optional[str] = None # 画像送信時のBase64データ
    image_mime_type: Optional[str] = None # 画像のMIMEタイプ (例: image/jpeg)
    model: Optional[str] = None # 使用するAIモデル


# --- Endpoints ---

# Vercel環境でのみルートハンドラを定義
# ローカル環境では、app.mount による静的ファイル配信に任せる
if os.environ.get("VERCEL"):
    @app.get("/")
    async def root():
        """
        Vercel環境専用のルートパスハンドラ
        
        Vercel環境では静的ファイルはCDNによって配信されるため、
        APIサーバー側では明示的に index.html へリダイレクトさせます。
        
        ローカル環境ではこのハンドラは定義されず、
        ファイル末尾の app.mount による静的ファイル配信が機能します。
        """
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/index.html")

@app.get("/api/health")
def health_check():
    """
    ヘルスチェック用エンドポイント
    
    サーバーが正常に稼働しているかを確認するために監視サービス等から叩かれます。
    """
    return {"status": "ok"}


# Debug endpoint removed for production
# Uncomment if needed for troubleshooting
# @app.get("/api/debug")
# async def debug_info():
#     ...


@app.get("/api/config")
async def get_config():
    """
    設定情報の取得
    
    NotionのConfigデータベースから、アプリの設定（プロンプト一覧など）を取得します。
    """
    config_db_id = APP_CONFIG["config_db_id"] or os.environ.get("NOTION_CONFIG_DB_ID")
    
    if not config_db_id:
        # セットアップが完了していない、または環境変数が未設定の場合の処置
        # ユーザーに設定DBのIDがないことを伝えます。
        raise HTTPException(status_code=500, detail="Configuration Database ID not found (Setup failed?)")
    
    configs = await fetch_config_db(config_db_id)
    return {"configs": configs}

@app.get("/api/models")
async def get_models():
    """
    利用可能なAIモデル一覧の取得
    
    テキスト専用モデルとマルチモーダル（画像対応）モデルに分類して返します。
    フロントエンドでユーザーがモデルを選択する際に使用されます。
    """
    try:
        all_models = get_available_models()
        text_only = get_text_models()
        vision_capable = get_vision_models()
        
        return {
            "all": all_models,
            "text_only": text_only,
            "vision_capable": vision_capable,
            "defaults": {
                "text": DEFAULT_TEXT_MODEL,
                "multimodal": DEFAULT_MULTIMODAL_MODEL
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/targets")
async def get_targets():
    """
    操作対象（Notionページ/データベース）一覧の取得
    
    ルートページ直下にあるページやデータベース、およびリンクされているページを取得します。
    これらはユーザーがメモの保存先やチャットのコンテキストとして選択する候補となります。
    """
    root_id = os.environ.get("NOTION_ROOT_PAGE_ID")
    if not root_id:
        raise HTTPException(status_code=500, detail="❌ NOTION_ROOT_PAGE_ID が設定されていません。.envファイルに NOTION_ROOT_PAGE_ID=your_page_id を追加してください。")
    
    children = await fetch_children_list(root_id)
    targets = []
    
    # リンクされたアイテムの詳細情報を取得するために並行処理を行うかどうか検討箇所
    # 現状はループ内で await していますが、並列化で高速化の余地があります。
    
    async def process_block(block):
        """1つのブロック情報を解析してターゲット形式に変換する内部関数"""
        b_type = block.get("type")
        
        if b_type == "child_database":
            # 子データベースの場合
            info = block.get("child_database", {})
            return {
                "id": block["id"],
                "type": "database",
                "title": info.get("title", "Untitled Database")
            }
        elif b_type == "child_page":
            # 子ページの場合
            info = block.get("child_page", {})
            return {
                "id": block["id"],
                "type": "page",
                "title": info.get("title", "Untitled Page")
            }
        elif b_type == "link_to_page":
            # ページリンク（エイリアス）の場合
            info = block.get("link_to_page", {})
            target_type = info.get("type")
            target_id = info.get(target_type)
            
            # リンク先の詳細情報を実際に取得しに行きます
            if target_type == "page_id":
                page = await get_page_info(target_id)
                if page:
                    # ページのタイトルプロパティを探して取得
                    props = page.get("properties", {})
                    title_plain = "Untitled Linked Page"
                    for k, v in props.items():
                        if v["type"] == "title" and v["title"]:
                            title_plain = v["title"][0]["plain_text"]
                            break
                    return {
                        "id": target_id,
                        "type": "page",
                        "title": title_plain + " (Link)"
                    }
            elif target_type == "database_id":
                # データベースの詳細を取得
                db = await safe_api_call("GET", f"databases/{target_id}")
                if db:
                    title_obj = db.get("title", [])
                    title_plain = title_obj[0]["plain_text"] if title_obj else "Untitled Linked DB"
                    return {
                        "id": target_id,
                        "type": "database",
                        "title": title_plain + " (Link)"
                    }
        return None

    # 全てのブロックを並行処理で解析
    results = await asyncio.gather(*[process_block(block) for block in children])
    # None (対象外のブロック) を除去してリスト化
    targets = [res for res in results if res]
            
    return {"targets": targets}

@app.get("/api/schema/{target_id}")
async def get_schema(target_id: str):
    """
    対象（DBまたはページ）のスキーマ情報の取得
    
    ページの場合は単純な構造を返し、データベースの場合は各プロパティ（列）の定義を返します。
    エラーハンドリングを強化しており、DBとしてもページとしても取得できなかった場合に詳細なエラーを返します。
    """
    db_error = None
    page_error = None
    
    # まずデータベースとして取得を試みる
    try:
        db = await get_db_schema(target_id)
        return {
            "type": "database",
            "schema": db
        }
    except ValueError as e:
        # IDがデータベースではない場合のエラー (400 Bad Request)
        db_error = str(e)
    except Exception as e:
        db_error = str(e)
        print(f"[Schema Fetch] Database fetch error: {e}")
    
    # 次にページとして取得を試みる（フォールバック）
    try:
        page = await get_page_info(target_id)
        if page:
            # ページの場合の固定スキーマ
            return {
                "type": "page",
                "schema": {
                    "Title": {"type": "title"},
                    "Content": {"type": "rich_text"}
                }
            }
        else:
            # ページ取得APIがNoneを返した場合
            page_error = f"Target {target_id} not found as Page (returned None)"
    except Exception as e:
        page_error = str(e)
        print(f"[Schema Fetch] Page fetch error: {e}")
    
    # 両方失敗した場合
    print(f"[Schema Fetch] Both database and page fetch failed for {target_id}")
    raise HTTPException(
        status_code=404,
        detail={
            "error": "Schema fetch failed",
            "target_id": target_id,
            "attempted": ["database", "page"],
            "database_error": db_error or "Unknown",
            "page_error": page_error or "Unknown",
            "suggestions": [
                "Notion APIキーの権限を確認してください",
                "ターゲットIDが正しいか確認してください",
                "Notionでこのページ/DBが削除されていないか確認してください"
            ]
        }
    )


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest):
    """
    テキスト分析API (AIによるタスク抽出)
    
    Notionのデータベース構造（スキーマ）と既存のデータを参照し、
    ユーザーのテキスト入力からデータベースに登録するための適切なプロパティ値をAIに推定させます。
    """
    target_db_id = request.target_db_id
    
    # 1. データベース情報の並行取得
    # VercelのFunction Timeout (10秒や60秒) を考慮し、重いNotion API呼び出しを並列化して時間を短縮します。
    # - get_db_schema: プロパティ定義を取得
    # - fetch_recent_pages: 最新の登録データ例を取得 (Few-shotプロンプト用)
    try:
        results = await asyncio.gather(
            get_db_schema(target_db_id),
            fetch_recent_pages(target_db_id, limit=3),
            return_exceptions=True
        )
        
        schema = results[0]
        recent_examples = results[1]
        
        # 個別のエラーハンドリング
        # 片方が失敗しても、最低限AIが動くように空データとして扱います。
        if isinstance(schema, Exception):
            print(f"Error fetching schema: {schema}")
            schema = {} # AIはスキーマなしでもタイトルのみの推測などは可能です
        if isinstance(recent_examples, Exception):
            print(f"Error fetching recent examples: {recent_examples}")
            recent_examples = []
            
    except Exception as e:
        print(f"Parallel fetch failed: {e}")
        schema = {}
        recent_examples = []

    # 2. システムプロンプトの準備
    # フロントエンドから渡されたカスタムプロンプトを使用します。
    system_prompt = request.system_prompt
    if not system_prompt:
        system_prompt = "You are a helpful assistant." # 万が一のためのデフォルト

    # 日時コンテキストの注入
    # AIが相対日時（「明日」「来週」など）を正しく理解できるように、現在時刻をプロンプトの冒頭に挿入します。
    current_time_str = get_current_jst_str()
    system_prompt = f"Current Time: {current_time_str}\n\n{system_prompt}"

    # 3. AIによる分析実行
    try:
        # Gemini等のLLMを呼び出し、JSON形式でのレスポンスを期待します。
        result = await analyze_text_with_ai(
            text=request.text,
            schema=schema,
            recent_examples=recent_examples,
            system_prompt=system_prompt,
            model=request.model
        )
        # 結果にはAIの回答だけでなく、トークン消費量やコスト情報も含まれる場合があります。
        return result
    except httpx.ReadTimeout:
        # Notion APIやAI APIのタイムアウト処理
        raise HTTPException(
            status_code=504,
            detail={
                "error": "Notion API Timeout",
                "message": "Notion APIの応答がタイムアウトしました。しばらく待ってから再試行してください。",
                "suggestions": ["Notionのステータスを確認してください", "しばらく待ってから再試行してください"]
            }
        )
    except Exception as e:
        # その他の予期せぬエラー
        print(f"[AI Analysis Error] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "AI analysis failed",
                "message": str(e),
                "type": type(e).__name__,
                "suggestions": [
                    "GEMINI_API_KEYが正しく設定されているか確認してください",
                    "Gemini APIの利用制限に達していないか確認してください",
                    "入力テキストが長すぎないか確認してください"
                ]
            }
        )

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    チャットAIエンドポイント (対話機能)
    
    特定のNotionページやデータベースをコンテキストとして、AIと会話を行います。
    画像入力や履歴を踏まえた回答が可能です。
    """
    print(f"[Chat] Request received for target: {request.target_id}")
    print(f"[Chat] Has image: {bool(request.image_data)}")
    print(f"[Chat] Text length: {len(request.text) if request.text else 0}")
    
    try:
        target_id = request.target_id
        
        # コンテキスト情報の取得 (スキーマやタイトル)
        # これにより、AIは「今どのページについて話しているか」を理解できます。
        print(f"[Chat] Fetching schema for target: {target_id}")
        try:
            schema_result = await get_schema(target_id)
            schema = schema_result.get("schema", {})
            target_type = schema_result.get("type", "database")
            print(f"[Chat] Schema fetched, type: {target_type}, properties: {len(schema)}")
        except Exception as schema_error:
            # ターゲット情報の取得失敗は致命的ではないため、エラーを返して終了します。
            print(f"[Chat] Schema fetch error: {schema_error}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Schema fetch failed",
                    "message": str(schema_error),
                    "suggestions": [
                        "ターゲットIDが正しいか確認してください",
                        "Notion APIキーの権限を確認してください"
                    ]
                }
            )
        
        # システムプロンプトの設定
        system_prompt = request.system_prompt
        if not system_prompt:
             # デフォルトのペルソナ（秘書）設定
             # Note: このプロンプトは public/script.js の DEFAULT_SYSTEM_PROMPT と同じ内容です
             system_prompt = """優秀な秘書として、ユーザーのタスクを明確にする手伝いをすること。
明確な実行できる タスク名に言い換えて。先頭に的確な絵文字を追加して
画像の場合は、そこから何をしようとしているのか推定して、タスクにして。
会話的な返答はしない。
返答は機械的に、タスク名としてふさわしい文字列のみを出力すること。
"""
        
        # 日時コンテキストの注入
        current_time_str = get_current_jst_str()
        system_prompt = f"Current Time: {current_time_str}\n\n{system_prompt}"
        
        # セッション履歴の構築
        # フロントエンドから渡された会話履歴に、参照コンテキスト（ページ本文など）をシステムメッセージとして追加します。
        session_history = request.session_history or []
        if request.reference_context:
            session_history = [
                {"role": "system", "content": request.reference_context}
            ] + session_history
        
        # AI実行 (チャットモード)
        # 画像が含まれるかどうかは内部で自動判別され、対応するモデルが選択されます。
        print(f"[Chat] Calling AI with model: {request.model or 'auto'}")
        try:
            result = await chat_analyze_text_with_ai(
                text=request.text,
                schema=schema,
                system_prompt=system_prompt,
                session_history=session_history,
                image_data=request.image_data,
                image_mime_type=request.image_mime_type,
                model=request.model
            )
            print(f"[Chat] AI response received, model used: {result.get('model')}")
            return result
        except httpx.ReadTimeout:
            raise HTTPException(
                status_code=504,
                detail={
                    "error": "Notion API Timeout",
                    "message": "Notion APIの応答がタイムアウトしました。",
                    "type": "ReadTimeout"
                }
            )
        except Exception as ai_error:
            print(f"[Chat AI Error] {type(ai_error).__name__}: {ai_error}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Chat AI failed",
                    "message": str(ai_error),
                    "type": type(ai_error).__name__,
                    "suggestions": [
                        "GEMINI_API_KEYが正しく設定されているか確認してください",
                        "Gemini APIの利用制限に達していないか確認してください"
                    ]
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Chat Endpoint Error] {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Unexpected error",
                "message": str(e),
                "type": type(e).__name__
            }
        )

@app.post("/api/save")
async def save(request: SaveRequest):
    """
    保存実行API
    
    ユーザーが承認した内容を実際にNotionに書き込みます。
    ページへの追記（ブロック追加）と、データベースへの新規アイテム作成の両方に対応しています。
    """
    try:
        if request.target_type == "page":
            # --- ページへの追記処理 ---
            content = request.text or "No content"
            # プロパティに"Content"が含まれている場合はそちらを優先（フォームからの入力など）
            if "Content" in request.properties:
                 c_obj = request.properties["Content"]
                 if "rich_text" in c_obj:
                     content = c_obj["rich_text"][0]["text"]["content"]
            
            # 画像データのサニタイズ（Notionブロックには直接Base64画像を埋め込めないため除去）
            content = sanitize_image_data(content)

            # 巨大なテキストのハンドリング
            # 10万文字を超えるような極端なデータは、APIエラーやタイムアウトを防ぐために切り詰めます。
            # 通常の長文（数千文字）は append_block 関数内で適切に分割処理されます。
            if len(content) > 100000:
                print(f"[Save] Warning: Extremely large content ({len(content)} chars). Truncating to 100k.")
                content = content[:100000] + "\n...(Truncated)..."

            success = await append_block(request.target_db_id, content)
            if not success:
               pass # 失敗時の詳細ハンドリングは append_block 実装に依存しますが、ここでは続行します。
            
            return {"status": "success", "url": ""} # ブロック追加の場合はURLを特定しにくいため空文字
        else:
            # --- データベースへの新規ページ作成処理 ---
            
            # プロパティに含まれる画像データのサニタイズ
            sanitized_props = request.properties.copy()
            
            def sanitize_val(val):
                if isinstance(val, str):
                    return sanitize_image_data(val)
                return val

            # rich_text プロパティの詳細なサニタイズと文字数制限対応
            # Notionのテキストプロパティには2000文字の制限がある場合があるため、
            # 必要であれば分割したりチェックしたりするロジックが含まれています。
            for key, val in sanitized_props.items():
                if isinstance(val, dict):
                    # rich_text型のフィールド処理
                    if "rich_text" in val and val["rich_text"]:
                        new_rich_text = []
                        for item in val["rich_text"]:
                            if "text" in item:
                                content = sanitize_val(item["text"]["content"])
                                # 2000文字を超える場合は分割して登録を試みる
                                if len(content) > 2000:
                                    for i in range(0, len(content), 2000):
                                        new_item = item.copy()
                                        new_item["text"] = item["text"].copy()
                                        new_item["text"]["content"] = content[i:i+2000]
                                        new_rich_text.append(new_item)
                                else:
                                    item["text"]["content"] = content
                                    new_rich_text.append(item)
                            else:
                                new_rich_text.append(item)
                        val["rich_text"] = new_rich_text
                    
                    # title型のフィールド処理（rich_textと同様）
                    if "title" in val and val["title"]:
                        new_title = []
                        for item in val["title"]:
                            if "text" in item:
                                content = sanitize_val(item["text"]["content"])
                                if len(content) > 2000:
                                    for i in range(0, len(content), 2000):
                                        new_item = item.copy()
                                        new_item["text"] = item["text"].copy()
                                        new_item["text"]["content"] = content[i:i+2000]
                                        new_title.append(new_item)
                                else:
                                    item["text"]["content"] = content
                                    new_title.append(item)
                            else:
                                new_title.append(item)
                        val["title"] = new_title

            # Notion APIを使ってページを作成
            url = await create_page(request.target_db_id, sanitized_props)
            return {"status": "success", "url": url}
    except Exception as e:
        print(f"[Save Error] {e}")
        # 保存失敗はユーザーにとって重要なエラーなので500を返します。
        raise HTTPException(status_code=500, detail=f"Failed to save to Notion: {str(e)}")


@app.post("/api/pages/create")
async def create_new_page(request: dict):
    """
    新規ページの作成API
    
    ルートページ直下に新しい空のページを作成します。
    ユーザーが会話のログを新しい場所に保存したい場合などに使用します。
    """
    try:
        page_name = request.get("page_name", "").strip()
        
        if not page_name:
            raise HTTPException(status_code=400, detail="ページ名が必要です")
        
        # 環境変数からNotionのルートページIDを取得します。
        root_id = os.environ.get("NOTION_ROOT_PAGE_ID")
        # ルートページIDが設定されていない場合はエラーを返します。
        if not root_id:
            raise HTTPException(status_code=500, detail="❌ NOTION_ROOT_PAGE_ID が設定されていません。.envファイルに NOTION_ROOT_PAGE_ID=your_page_id を追加してください。")
        
        # Notion API呼び出し
        # safe_api_call関数を使用して、新しいページを作成します。
        # 親ページとしてNOTION_ROOT_PAGE_IDを指定し、タイトルプロパティを設定します。
        new_page = await safe_api_call("POST", "pages", json={
            "parent": {"type": "page_id", "page_id": root_id},
            "properties": {
                "title": {
                    "title": [{"text": {"content": page_name}}]
                }
            }
        })
        
        # ページ作成が失敗した場合はエラーを発生させます。
        if not new_page:
            raise Exception("Failed to create page")
        
        # 作成されたページのID、タイトル、タイプを返します。
        return {
            "id": new_page["id"],
            "title": page_name,
            "type": "page"
        }
    except HTTPException:
        # HTTPExceptionはそのまま再スローします。
        raise
    except Exception as e:
        # その他の予期せぬエラーが発生した場合は、ログに出力し、500エラーを返します。
        print(f"[Create Page Error] {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"ページ作成に失敗しました: {str(e)}")


# --- コンテンツプレビュー用エンドポイント (Content Preview) ---
# フロントエンドで「参照中」のページやデータベースの中身を簡易表示するために使用します。

@app.get("/api/content/page/{page_id}")
async def get_page_content(page_id: str):
    """
    ページ内容の取得
    
    指定されたページのブロック情報を取得し、テキストのみを抽出して簡易的な構造で返します。
    """
    from .notion import fetch_children_list
    
    try:
        # Notion APIから指定されたページの子ブロックリストを取得します。
        results = await fetch_children_list(page_id)
        blocks = []
        
        # 各ブロックをループ処理し、テキストコンテンツを抽出します。
        for block in results:
            b_type = block.get("type")
            content = ""
            
            # ブロックタイプに応じてテキストを抽出
            # rich_text, child_page, child_databaseなど、主要なブロックタイプに対応します。
            if b_type in block:
                info = block[b_type]
                if "rich_text" in info:
                    content = "".join([t.get("plain_text", "") for t in info["rich_text"]])
                elif b_type == "child_page":
                    content = info.get("title", "")
                elif b_type == "child_database":
                    content = info.get("title", "")
            
            # 抽出したタイプとコンテンツをリストに追加します。
            blocks.append({
                "type": b_type,
                "content": content
            })
            
        # ページのタイプとブロックのリストを返します。
        return {"type": "page", "blocks": blocks}
    except Exception as e:
        # エラーが発生した場合はログに出力し、500エラーを返します。
        print(f"[Page Content Error] {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch page content: {str(e)}")

@app.get("/api/content/database/{database_id}")
async def get_database_content(database_id: str):
    """
    データベース内容の取得
    
    指定されたデータベースのレコード（ページ）を取得し、テーブル形式で表示しやすいように整形して返します。
    最大15件に制限しています。
    """
    from .notion import query_database
    
    try:
        # Notion APIからデータベースのクエリを実行し、最大15件のレコードを取得します。
        results = await query_database(database_id, limit=15)
        # 結果がない場合は、空のデータベース構造を返します。
        if not results:
            return {"type": "database", "columns": [], "rows": []}
            
        # 最初のレコードからカラム（プロパティ）一覧を取得します。
        # これをテーブルのヘッダーとして使用します。
        columns = list(results[0]["properties"].keys())
        
        # 実際にテーブルに表示するデータを整形
        rows = []
        for page in results:
            row_data = {}
            # 各カラムについて、プロパティの値を抽出します。
            for col in columns:
                prop = page["properties"].get(col)
                if not prop:
                    row_data[col] = "" # プロパティが存在しない場合は空文字列
                    continue
                
                # プロパティタイプごとの表示用テキスト抽出
                # Notionの様々なプロパティタイプに対応し、人間が読みやすい形式に変換します。
                p_type = prop["type"]
                if p_type == "title":
                    row_data[col] = "".join([t.get("plain_text", "") for t in prop["title"]])
                elif p_type == "rich_text":
                    row_data[col] = "".join([t.get("plain_text", "") for t in prop["rich_text"]])
                elif p_type == "select":
                    row_data[col] = prop["select"]["name"] if prop["select"] else ""
                elif p_type == "multi_select":
                    row_data[col] = ", ".join([o["name"] for o in prop["multi_select"]])
                elif p_type == "date":
                    row_data[col] = prop["date"]["start"] if prop["date"] else ""
                elif p_type == "url":
                    row_data[col] = prop["url"] or ""
                elif p_type == "checkbox":
                    row_data[col] = "✅" if prop["checkbox"] else "⬜"
                elif p_type == "number": # 追加: numberタイプ
                    row_data[col] = str(prop["number"]) if prop["number"] is not None else ""
                elif p_type == "people": # 追加: peopleタイプ
                    row_data[col] = ", ".join([u.get("name", "Unknown") for u in prop["people"]])
                elif p_type == "status": # 追加: statusタイプ
                    row_data[col] = prop["status"].get("name", "") if prop["status"] else ""
                else:
                    row_data[col] = f"({p_type})" # 未対応のタイプはタイプ名を表示
            
            rows.append(row_data)
            
        # データベースのタイプ、カラム（ヘッダー）、整形された行データを返します。
        return {
            "type": "database",
            "columns": columns,
            "rows": rows
        }
    except Exception as e:
        # エラーが発生した場合はログに出力し、500エラーを返します。
        print(f"[Database Content Error] {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch database content: {str(e)}")

# --- 静的ファイルの配信設定 ---
# この app.mount は最後に記述することが推奨されます。
# そうしないと、APIのエンドポイント ("/api/...") よりも先に "/" がマッチしてしまい、
# 意図しないルーティングになる可能性があります。

if not os.environ.get("VERCEL"):
    # ローカル開発環境用
    # "public" フォルダ内のファイルを "/" パスで配信します。
    # html=True により、/index.html へのアクセスなしで / でアクセス可能になります。
    print("💾 Mounting static files from 'public/' directory (local mode)")
    app.mount("/", StaticFiles(directory="public", html=True), name="static")
else:
    # Vercel環境用
    # Vercel Deploymentでは、vercel.jsonの設定やOutput APIに基づき、
    # 静的ファイルは自動的に最適化されて配信されるため、FastAPI側でのマウントは不要（または競合の原因）となります。
    print("☁️  Skipping static file mount (Vercel mode - using Build Output API)")
