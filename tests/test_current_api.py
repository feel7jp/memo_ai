"""
現状のAPI仕様を固定するベースラインテスト

リファクタリング前に全てパスすることを確認し、
リファクタリング後も同じテストがパスすることで、デグレがないことを保証します。
"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.smoke
@pytest.mark.regression
@pytest.mark.asyncio
async def test_health_check(client):
    """ヘルスチェックが正常に動作する"""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.smoke
@pytest.mark.regression
@pytest.mark.asyncio
async def test_config_endpoint(client):
    """設定エンドポイントが必要なキーを返す"""
    response = await client.get("/api/config")
    assert response.status_code == 200
    data = response.json()

    # 必須キーの存在確認
    assert "debug_mode" in data
    assert "default_system_prompt" in data
    assert "configs" in data
    assert isinstance(data["configs"], list)


@pytest.mark.smoke
@pytest.mark.regression
@pytest.mark.asyncio
async def test_models_endpoint(client):
    """モデル一覧エンドポイントが正常に動作する"""
    response = await client.get("/api/models")
    assert response.status_code == 200
    data = response.json()

    # 必須キーの存在確認
    assert "all" in data
    assert "text_only" in data
    assert "vision_capable" in data
    assert "defaults" in data

    # defaults構造の確認
    assert "text" in data["defaults"]
    assert "multimodal" in data["defaults"]

    # 配列型の確認
    assert isinstance(data["all"], list)
    assert isinstance(data["text_only"], list)
    assert isinstance(data["vision_capable"], list)


@pytest.mark.asyncio
async def test_targets_endpoint_structure(client):
    """ターゲット一覧エンドポイントの応答構造を確認"""
    # Notion API呼び出しをモック
    with patch("api.endpoints.fetch_children_list") as mock_fetch:
        # モックデータ: 子ページとデータベース
        mock_fetch.return_value = [
            {
                "id": "test-page-id",
                "type": "child_page",
                "child_page": {"title": "テストページ"},
            },
            {
                "id": "test-db-id",
                "type": "child_database",
                "child_database": {"title": "テストDB"},
            },
        ]

        response = await client.get("/api/targets")
        assert response.status_code == 200
        data = response.json()

        # 構造確認
        assert "targets" in data
        assert isinstance(data["targets"], list)

        # 各要素の構造確認
        if len(data["targets"]) > 0:
            target = data["targets"][0]
            assert "id" in target
            assert "type" in target
            assert "title" in target


@pytest.mark.asyncio
async def test_save_page_sanitization(client):
    """
    ページ保存時の画像データサニタイズを確認
    """
    # append_block をモック
    with patch("api.notion.append_block") as mock_append:
        mock_append.return_value = True

        # 画像データを含むリクエスト
        payload = {
            "target_db_id": "test-page-id",
            "target_type": "page",
            "text": "テスト ![img](data:image/png;base64,abcd...) 画像除去テスト",
            "properties": {},
        }

        response = await client.post("/api/save", json=payload)
        assert response.status_code == 200

        # append_block が呼ばれたことを確認
        assert mock_append.called

        # 渡された引数を取得
        call_args = mock_append.call_args
        saved_text = call_args[0][1]  # 第2引数がテキスト

        # 画像データが除去されていることを確認
        assert "data:image" not in saved_text
        assert "テスト" in saved_text
        assert "画像除去テスト" in saved_text


@pytest.mark.asyncio
async def test_save_database_structure(client):
    """
    データベース保存の基本動作確認
    """
    # create_page をモック
    with patch("api.notion.create_page") as mock_create:
        mock_create.return_value = "https://notion.so/test-page"

        payload = {
            "target_db_id": "test-db-id",
            "target_type": "database",
            "properties": {
                "Name": {"title": [{"text": {"content": "テストアイテム"}}]}
            },
        }

        response = await client.post("/api/save", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert "url" in data


@pytest.mark.asyncio
async def test_analyze_endpoint_mock(client):
    """
    分析エンドポイントの基本構造確認（モック使用）
    """
    # AI呼び出しとNotion呼び出しをモック
    with (
        patch("api.ai.analyze_text_with_ai") as mock_ai,
        patch("api.endpoints.get_db_schema") as mock_schema,
        patch("api.notion.fetch_recent_pages") as mock_recent,
    ):
        mock_ai.return_value = {"properties": {}}
        mock_schema.return_value = {"Name": {"type": "title"}}
        mock_recent.return_value = []

        payload = {
            "text": "テスト入力",
            "target_db_id": "test-db",
            "system_prompt": "テストプロンプト",
        }

        response = await client.post("/api/analyze", json=payload)
        # AI呼び出しが成功すれば200
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_endpoint_mock(client):
    """
    チャットエンドポイントの基本構造確認（モック使用）
    """
    # Notion API, AI APIをモック
    with (
        patch("api.ai.chat_analyze_text_with_ai") as mock_ai,
        patch("api.endpoints.get_schema") as mock_schema,
    ):
        mock_ai.return_value = {"response": "テスト応答", "model": "gemini-1.5-flash"}
        mock_schema.return_value = {"type": "database", "schema": {}}

        payload = {"text": "こんにちは", "target_id": "test-target"}

        response = await client.post("/api/chat", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "response" in data or "model" in data


@pytest.mark.asyncio
async def test_create_page_validation(client):
    """
    新規ページ作成のバリデーション確認
    """
    # page_name が空の場合
    payload = {"page_name": ""}
    response = await client.post("/api/pages/create", json=payload)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_save_long_text_splitting(client):
    """
    保存時に長文テキスト(2000文字超)が分割されるロジックを検証
    """
    # 2500文字のテキストを作成
    long_text = "a" * 2500

    with patch("api.notion.create_page", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = "https://notion.so/new-page"

        payload = {
            "target_db_id": "test-db",
            "target_type": "database",
            "properties": {
                "Description": {"rich_text": [{"text": {"content": long_text}}]}
            },
        }

        response = await client.post("/api/save", json=payload)
        assert response.status_code == 200

        # create_page に渡された引数を検証
        args, _ = mock_create.call_args
        props = args[1]

        rich_text_items = props["Description"]["rich_text"]

        # 2500文字なので、2000文字 + 500文字 の2つの要素に分割されているはず
        assert len(rich_text_items) == 2
        assert len(rich_text_items[0]["text"]["content"]) == 2000
        assert len(rich_text_items[1]["text"]["content"]) == 500
