"""
pytest設定ファイル

テスト用の共通フィクスチャを定義します。
"""

import os

# Windows環境でのUTF-8出力対応（絵文字等を正しく表示するため）
# ベストプラクティス: PYTHONUTF8=1 を設定
os.environ["PYTHONUTF8"] = "1"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from api.index import app


# pytest-asyncioの設定: 各テストを自動的にasyncioで実行
pytest_plugins = ("pytest_asyncio",)


def pytest_configure(config):
    """カスタムマーカーの登録"""
    config.addinivalue_line(
        "markers", "smoke: 最重要テスト（健全性チェック、CI高速実行用）"
    )
    config.addinivalue_line(
        "markers", "regression: リグレッション検知テスト（全機能カバレッジ）"
    )
    config.addinivalue_line(
        "markers", "integration: 統合テスト（複数エンドポイント連携）"
    )
    config.addinivalue_line("markers", "security: セキュリティ関連テスト")


@pytest_asyncio.fixture
async def client():
    """
    非同期HTTPクライアントのフィクスチャ

    FastAPIアプリケーションに対してHTTPリクエストを送信するためのテストクライアント。
    app.mount による静的ファイル配信の影響を受けないように ASGITransport を使用。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def assert_response_ok(response, expected_status=200):
    """
    レスポンスのステータスコードを検証し、失敗時に詳細を出力するヘルパー

    使用例:
        response = await client.post("/api/save", json=payload)
        assert_response_ok(response)  # 200を期待
        assert_response_ok(response, 201)  # 201を期待
    """
    if response.status_code != expected_status:
        print(f"\n{'=' * 60}")
        print(f"[TEST FAILURE] Expected {expected_status}, got {response.status_code}")
        print(f"[RESPONSE URL] {response.url}")
        try:
            detail = response.json()
            print(f"[RESPONSE BODY] {detail}")
        except Exception:
            print(f"[RESPONSE TEXT] {response.text[:500]}")
        print(f"{'=' * 60}\n")
    assert response.status_code == expected_status, (
        f"Expected {expected_status}, got {response.status_code}"
    )


# --- エラー詳細出力フック ---


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    テスト失敗時に詳細なエラー情報を出力するフック

    Import問題やモックパスエラーのデバッグを容易にするため、
    例外の型と詳細メッセージを明示的に表示します。
    """
    outcome = yield
    rep = outcome.get_result()

    if rep.when == "call" and rep.failed:
        if call.excinfo:
            exc_type = call.excinfo.type.__name__
            exc_value = str(call.excinfo.value)

            print(f"\n{'=' * 60}")
            print(f"[DEBUG] Test FAILED: {item.name}")
            print(f"[DEBUG] Exception Type: {exc_type}")
            print(f"[DEBUG] Exception Message: {exc_value[:500]}")

            # Import/Attribute エラーの場合は追加情報
            if exc_type in (
                "ImportError",
                "ModuleNotFoundError",
                "AttributeError",
                "NameError",
            ):
                print("[DEBUG] ⚠️  Import/Module関連エラー検出!")
                print("[DEBUG] モックパスまたはimport文を確認してください")

            # HTTPステータスコードエラーの場合
            if "assert" in exc_value.lower() and (
                "==" in exc_value or "!=" in exc_value
            ):
                print(
                    "[DEBUG] 💡 ステータスコード不一致の場合、リクエストスキーマを確認"
                )
            print(f"{'=' * 60}\n")
