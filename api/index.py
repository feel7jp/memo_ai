import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python 3.9以降では標準ライブラリですが、古いバージョンのためのバックポート対応
    # Backport for Python 3.8 or older if needed, though 3.9+ has zoneinfo
    from backports.zoneinfo import ZoneInfo

from contextlib import asynccontextmanager

# --- 自作モジュールのインポート ---
# Notion APIとの通信を担当する関数群
# update_page_properties はendpoints.pyで使用

# AI（Gemini等）との連携を担当する関数群

# 使用可能なAIモデル定義
from api.models import get_available_models

# アプリケーションのデフォルト設定
from api.config import (
    DEBUG_MODE,
    normalize_notion_id,
)


# Endpoints definition
from api.endpoints import router as endpoints_router


# 環境変数の読み込み
# ローカル環境では.envファイルから読み込み、Vercel環境では環境変数から直接読み込み
load_dotenv()  # .envファイルがあれば読み込む（なくてもエラーにしない）

# 必須環境変数のチェック
required_env_vars = {
    "NOTION_API_KEY": "Notion APIキー",
    "NOTION_ROOT_PAGE_ID": "NotionルートページID",
}

missing_vars = []
for var_name, var_description in required_env_vars.items():
    value = os.environ.get(var_name)
    # NOTION_ROOT_PAGE_IDの正規化
    if var_name == "NOTION_ROOT_PAGE_ID" and value:
        os.environ[var_name] = normalize_notion_id(value)
    if not value:
        missing_vars.append(f"  - {var_name} ({var_description})")

if missing_vars:
    error_message = "❌ 必須の環境変数が設定されていません:\n" + "\n".join(missing_vars)
    error_message += "\n\n設定方法:"
    error_message += "\n  ローカル環境: .envファイルに上記の変数を追加してください"
    error_message += "\n  Vercel環境: プロジェクト設定の環境変数に追加してください"
    raise EnvironmentError(error_message)

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
    is_vercel = os.environ.get("VERCEL")
    if is_vercel:
        print("📦 環境: Vercel (Production)")
    else:
        print("💻 環境: ローカル開発環境")

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

    # JavaScriptファイルの構文チェック（ローカル環境のみ）
    if not is_vercel:
        print("\n🔍 JavaScriptファイルの構文チェック中...")
        try:
            import subprocess
            import glob

            js_files = glob.glob("public/js/*.js")
            syntax_errors = []

            for js_file in js_files:
                try:
                    result = subprocess.run(
                        ["node", "--check", js_file],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode != 0:
                        syntax_errors.append(f"  ❌ {js_file}: {result.stderr.strip()}")
                    else:
                        print(f"  ✅ {js_file}: OK")
                except FileNotFoundError:
                    print(
                        "  ⚠️  Node.js が見つかりません。構文チェックをスキップします。"
                    )
                    break
                except subprocess.TimeoutExpired:
                    syntax_errors.append(f"  ⏱️  {js_file}: タイムアウト")
                except Exception as e:
                    syntax_errors.append(f"  ⚠️  {js_file}: {str(e)}")

            if syntax_errors:
                print("\n" + "=" * 70)
                print("⚠️  JavaScript構文エラーが検出されました:")
                for error in syntax_errors:
                    print(error)
                print("=" * 70 + "\n")
            else:
                if js_files:
                    print(
                        f"  ✅ すべてのJavaScriptファイル ({len(js_files)}個) の構文チェックに合格しました\n"
                    )

        except Exception as e:
            print(f"  ⚠️  構文チェック中にエラーが発生: {e}\n")

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
        print("=" * 70)

    # 環境変数の簡易チェック
    if not is_vercel:
        page_id = os.environ.get("NOTION_ROOT_PAGE_ID", "")
        if page_id and ("-" in page_id or "http" in page_id or len(page_id) < 20):
            print(
                f"⚠️  NOTION_ROOT_PAGE_ID が不正な可能性: {page_id[:30]}... (ハイフン/URL除外, NotionページURLから32文字の英数字のみ抽出)"
            )

    yield
    # yieldより後のコードはアプリケーション終了時に実行されます (シャットダウン処理)
    # ここでは特に処理は記述していません。


# FastAPIアプリケーションのインスタンス作成
app = FastAPI(lifespan=lifespan)


# --- グローバル例外ハンドラー (Global Exception Handler) ---
@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """
    全ての未処理例外をキャッチし、統一フォーマットでJSONレスポンスを返す

    - DEBUG_MODE=True: 詳細なエラー情報とトレースバックを返す
    - DEBUG_MODE=False: 最小限のエラー情報のみ返す（セキュリティ）
    """
    import traceback
    from fastapi.responses import JSONResponse

    # ログ出力（将来的にlogger使用）
    print(f"[ERROR] Unhandled exception: {type(exc).__name__}: {str(exc)}")

    # レスポンス内容
    error_detail = {
        "error": type(exc).__name__,
        "message": str(exc) if DEBUG_MODE else "Internal server error",
    }

    # DEBUG_MODEの場合のみトレースバックを含める
    if DEBUG_MODE:
        error_detail["traceback"] = traceback.format_exc()

    return JSONResponse(status_code=500, content=error_detail)


# --- CORS (Cross-Origin Resource Sharing) 設定 ---
# 本番環境では自動検出またはALLOWED_ORIGINS環境変数で設定


def detect_allowed_origins() -> list:
    """CORS許可オリジンを自動検出または環境変数から取得"""
    # 1. 明示的な環境変数があれば優先
    explicit = os.environ.get("ALLOWED_ORIGINS")
    if explicit:
        origins = [o.strip() for o in explicit.split(",")]
        print(f"🔐 [CORS] Explicit: {', '.join(origins)}")
        return origins

    # 2. 本番環境の自動検出
    detected = []

    # Vercel: VERCEL_URL から自動取得
    vercel_url = os.environ.get("VERCEL_URL")
    if vercel_url:
        detected.append(f"https://{vercel_url}")
        # プロダクションドメインも追加 (VERCEL_PROJECT_PRODUCTION_URL)
        prod_url = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
        if prod_url:
            detected.append(f"https://{prod_url}")

    # GCP Cloud Run: K_SERVICE環境変数で検出, CLOUD_RUN_URLで取得
    cloud_run_url = os.environ.get("CLOUD_RUN_URL")
    if cloud_run_url:
        detected.append(cloud_run_url)

    if detected:
        print(f"🔐 [CORS] Auto-detected: {', '.join(detected)}")
        return detected

    # 3. 本番環境で未設定の場合は警告して全許可
    if not DEBUG_MODE:
        print("⚠️  [CORS] 本番環境では ALLOWED_ORIGINS を設定してください")
        print("    例: ALLOWED_ORIGINS=https://yourdomain.com")
    else:
        print("🌍 [CORS] Development mode: allowing all origins (*)")

    return ["*"]


allowed_origins = detect_allowed_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Endpoints Router Include ---
app.include_router(endpoints_router)


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


# Debug endpoint (development only) - guarded by DEBUG_MODE
# This endpoint is only registered when DEBUG_MODE=true in the environment
if DEBUG_MODE:

    @app.get("/api/debug5075378")
    async def debug_info():
        """
        デバッグ情報取得エンドポイント（開発専用）

        環境変数、ファイルパス、ルート情報などを返します。
        この情報はトラブルシューティングに役立ちますが、本番環境では公開すべきではありません。
        DEBUG_MODE=falseの場合、このエンドポイントは登録されません。
        """
        import sys

        # 現在時刻（JST）
        jst = ZoneInfo("Asia/Tokyo")
        now = datetime.now(jst)
        timestamp = now.strftime("%Y-%m-%dT%H:%M:%S%z")

        # 環境情報
        is_vercel = bool(os.environ.get("VERCEL"))
        environment = {
            "is_vercel": is_vercel,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "host": "0.0.0.0" if not is_vercel else "Vercel",
        }

        # パス情報
        paths = {"cwd": os.getcwd(), "static_dir": "public", "api_dir": "api"}

        # ファイルシステムチェック
        filesystem_checks = {}
        check_paths = ["public", ".env", "README.md", "requirements.txt", "api"]

        for path in check_paths:
            full_path = os.path.join(os.getcwd(), path)
            exists = os.path.exists(full_path)
            info = {"exists": exists}

            if exists:
                info["is_file"] = os.path.isfile(full_path)
                info["is_dir"] = os.path.isdir(full_path)

                if info["is_file"]:
                    info["size"] = os.path.getsize(full_path)
                elif info["is_dir"]:
                    try:
                        contents = os.listdir(full_path)
                        info["contents"] = contents[:10]  # 最初の10個のみ
                    except (PermissionError, FileNotFoundError, OSError) as e:
                        # ディレクトリの読み取り権限がない場合やファイルシステムエラーを想定
                        info["error"] = f"読み取りエラー: {type(e).__name__}"

            filesystem_checks[path] = info

        # 環境変数（マスク済み）
        env_vars = {}
        important_vars = [
            "NOTION_API_KEY",
            "NOTION_ROOT_PAGE_ID",
            "GEMINI_API_KEY",
            "PORT",
        ]

        for var in important_vars:
            value = os.environ.get(var)
            if value:
                # APIキーなどは一部のみ表示
                if "KEY" in var or "SECRET" in var:
                    masked = (
                        f"{value[:8]}...{value[-4:]}"
                        if len(value) > 12
                        else "***masked***"
                    )
                    env_vars[var] = masked
                elif "ID" in var:
                    # IDは最初の8文字のみ表示
                    masked = f"{value[:8]}..." if len(value) > 8 else value
                    env_vars[var] = masked
                else:
                    env_vars[var] = value
            else:
                env_vars[var] = None

        # 登録ルート情報
        routes = []
        for route in app.routes:
            route_info = {
                "path": route.path,
                "name": route.name,
                "methods": list(route.methods) if hasattr(route, "methods") else [],
            }
            routes.append(route_info)

        # CORS設定情報
        cors_info = {
            "allowed_origins": allowed_origins,
            "is_restricted": allowed_origins != ["*"],
            "detected_platform": None,
        }

        # プラットフォーム検出
        if os.environ.get("VERCEL_URL"):
            cors_info["detected_platform"] = "Vercel"
        elif os.environ.get("CLOUD_RUN_URL"):
            cors_info["detected_platform"] = "GCP Cloud Run"
        elif os.environ.get("ALLOWED_ORIGINS"):
            cors_info["detected_platform"] = "Manual (ALLOWED_ORIGINS)"

        # モデル情報（デバッグ用）
        recommended_models = get_available_models(recommended_only=True)
        all_models = get_available_models(recommended_only=False)
        models_info = {
            "recommended_count": len(recommended_models),
            "total_count": len(all_models),
            "raw_list": all_models,  # 全モデルの生データ
        }

        # バックエンドAPIログ（Notion + LLM）
        from api.notion import notion_api_log
        from api.llm_client import llm_api_log

        backend_logs = {
            "notion": list(notion_api_log),
            "llm": list(llm_api_log),
        }

        return {
            "timestamp": timestamp,
            "environment": environment,
            "paths": paths,
            "filesystem_checks": filesystem_checks,
            "env_vars": env_vars,
            "cors": cors_info,
            "routes": routes[:20],  # 最初の20個のみ
            "models": models_info,
            "backend_logs": backend_logs,
        }

    # End of DEBUG_MODE section


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
