"""
拡張テスト: Part 6で特定した高優先度ロジックのテスト

リファクタリング前に、壊れやすいロジックを徹底的にテストします。
"""

import pytest
from api.services import sanitize_image_data
from unittest.mock import patch, AsyncMock


# ===== sanitize_image_data() テスト (🔴最高優先度) =====


def test_sanitize_markdown_image():
    """Markdown形式の画像データが除去されること"""
    input_text = "Hello ![alt](data:image/png;base64,abc123) World"
    expected = "Hello  World"
    assert sanitize_image_data(input_text) == expected


def test_sanitize_html_image():
    """HTML img タグの画像データが除去されること"""
    input_text = 'Text <img src="data:image/jpeg;base64,xyz">!'
    expected = "Text !"
    assert sanitize_image_data(input_text) == expected


def test_sanitize_marker():
    """[画像送信]マーカーが除去されること"""
    input_text = "[画像送信] メッセージ"
    expected = "メッセージ"
    assert sanitize_image_data(input_text) == expected


def test_sanitize_combined():
    """複数パターンが同時に除去されること"""
    input_text = '[画像送信] Hello ![](data:image/png;base64,abc) <img src="data:image/jpeg;base64,xyz"> World'
    result = sanitize_image_data(input_text)
    # 画像データがすべて除去され、マーカーも消えること
    assert "data:image" not in result
    assert "[画像送信]" not in result
    assert "Hello" in result
    assert "World" in result


def test_sanitize_normal_text():
    """通常のテキストはそのまま残ること"""
    input_text = "普通のテキスト"
    assert sanitize_image_data(input_text) == input_text


def test_sanitize_url_preserved():
    """通常のURL（非data URI）は残ること"""
    input_text = "![img](https://example.com/img.png)"
    assert sanitize_image_data(input_text) == input_text


# ===== process_block() テスト (🟠高優先度) =====


@pytest.mark.asyncio
async def test_process_block_child_database(client):
    """child_database タイプが正しく変換されること"""
    from api.endpoints import get_targets

    mock_blocks = [
        {
            "id": "db-123",
            "type": "child_database",
            "child_database": {"title": "My Database"},
        }
    ]

    with patch(
        "api.endpoints.fetch_children_list", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = mock_blocks

        from fastapi import Request
        from unittest.mock import MagicMock

        mock_request = MagicMock(spec=Request)

        # rate_limiterをモック
        with patch(
            "api.endpoints.rate_limiter.check_rate_limit", new_callable=AsyncMock
        ):
            response = await get_targets(mock_request)

            assert len(response["targets"]) == 1
            target = response["targets"][0]
            assert target["id"] == "db-123"
            assert target["type"] == "database"
            assert target["title"] == "My Database"


@pytest.mark.asyncio
async def test_process_block_child_page(client):
    """child_page タイプが正しく変換されること"""
    from api.endpoints import get_targets

    mock_blocks = [
        {"id": "page-456", "type": "child_page", "child_page": {"title": "My Page"}}
    ]

    with patch(
        "api.endpoints.fetch_children_list", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = mock_blocks

        from fastapi import Request
        from unittest.mock import MagicMock

        mock_request = MagicMock(spec=Request)

        with patch(
            "api.endpoints.rate_limiter.check_rate_limit", new_callable=AsyncMock
        ):
            response = await get_targets(mock_request)

            assert len(response["targets"]) == 1
            target = response["targets"][0]
            assert target["id"] == "page-456"
            assert target["type"] == "page"
            assert target["title"] == "My Page"


@pytest.mark.asyncio
async def test_process_block_unknown_type(client):
    """未知のブロックタイプは除外されること"""
    from api.endpoints import get_targets

    mock_blocks = [{"id": "bookmark-789", "type": "bookmark", "bookmark": {}}]

    with patch(
        "api.endpoints.fetch_children_list", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = mock_blocks

        from fastapi import Request
        from unittest.mock import MagicMock

        mock_request = MagicMock(spec=Request)

        with patch(
            "api.endpoints.rate_limiter.check_rate_limit", new_callable=AsyncMock
        ):
            response = await get_targets(mock_request)

            # 未知タイプは除外されるので空配列
            assert len(response["targets"]) == 0


# ===== 境界値テスト (save分割) =====


@pytest.mark.asyncio
async def test_save_boundary_1999_chars(client):
    """1999文字: 分割されないこと"""
    text = "a" * 1999

    with patch("api.notion.create_page", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = "https://notion.so/page"

        payload = {
            "target_db_id": "db-id",
            "target_type": "database",
            "properties": {"Content": {"rich_text": [{"text": {"content": text}}]}},
        }

        response = await client.post("/api/save", json=payload)
        assert response.status_code == 200

        args, _ = mock_create.call_args
        props = args[1]
        rich_text_items = props["Content"]["rich_text"]

        # 分割されない
        assert len(rich_text_items) == 1
        assert len(rich_text_items[0]["text"]["content"]) == 1999


@pytest.mark.asyncio
async def test_save_boundary_2000_chars(client):
    """2000文字: 分割されないこと"""
    text = "a" * 2000

    with patch("api.notion.create_page", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = "https://notion.so/page"

        payload = {
            "target_db_id": "db-id",
            "target_type": "database",
            "properties": {"Content": {"rich_text": [{"text": {"content": text}}]}},
        }

        response = await client.post("/api/save", json=payload)
        assert response.status_code == 200

        args, _ = mock_create.call_args
        props = args[1]
        rich_text_items = props["Content"]["rich_text"]

        # ちょうど2000文字なので分割されない
        assert len(rich_text_items) == 1
        assert len(rich_text_items[0]["text"]["content"]) == 2000


@pytest.mark.asyncio
async def test_save_boundary_2001_chars(client):
    """2001文字: 分割されること"""
    text = "a" * 2001

    with patch("api.notion.create_page", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = "https://notion.so/page"

        payload = {
            "target_db_id": "db-id",
            "target_type": "database",
            "properties": {"Content": {"rich_text": [{"text": {"content": text}}]}},
        }

        response = await client.post("/api/save", json=payload)
        assert response.status_code == 200

        args, _ = mock_create.call_args
        props = args[1]
        rich_text_items = props["Content"]["rich_text"]

        # 2001文字なので 2000 + 1 の2つに分割
        assert len(rich_text_items) == 2
        assert len(rich_text_items[0]["text"]["content"]) == 2000
        assert len(rich_text_items[1]["text"]["content"]) == 1
