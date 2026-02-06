"""
ギャップカバレッジテスト: gap_analysis.mdで特定した未実装テスト

implementation_plan.mdとの照合で見つかった欠落テストを補完します。
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx


# ===== 1. GET /api/schema - 異常系（無効ID → 404） =====


@pytest.mark.asyncio
async def test_schema_error_handling_invalid_id(client):
    """
    無効なIDで404エラーが返り、database_errorとpage_errorの両方が含まれること
    """
    from api.endpoints import get_schema
    from fastapi import Request

    mock_request = MagicMock(spec=Request)

    # rate_limiterをモック
    with patch("api.endpoints.rate_limiter.check_rate_limit", new_callable=AsyncMock):
        # DBとPageの両方で失敗させる
        with patch(
            "api.endpoints.get_db_schema", side_effect=ValueError("Not a database")
        ):
            with patch("api.endpoints.get_page_info", return_value=None):
                with pytest.raises(Exception) as exc_info:
                    await get_schema("invalid-id-123", mock_request)

                # 404エラーであること
                assert exc_info.value.status_code == 404
                # エラー詳細に両方のエラーが含まれること
                detail = exc_info.value.detail
                assert "database_error" in detail
                assert "page_error" in detail


# ===== 2. POST /api/save - 画像除去（統合テスト） =====


@pytest.mark.asyncio
async def test_save_page_with_image_data_removal(client):
    """
    Page保存時、textに含まれる画像データが除去されること（統合テスト）
    """
    with patch("api.notion.append_block", new_callable=AsyncMock) as mock_append:
        mock_append.return_value = True

        payload = {
            "target_db_id": "page-id",
            "target_type": "page",
            "properties": {},
            "text": "Hello ![img](data:image/png;base64,abc123) World",
        }

        response = await client.post("/api/save", json=payload)
        assert response.status_code == 200

        # append_blockに渡された引数を確認
        args, _ = mock_append.call_args
        saved_text = args[1]

        # 画像データが除去されていること
        assert "data:image" not in saved_text
        assert "Hello" in saved_text
        assert "World" in saved_text


@pytest.mark.asyncio
async def test_save_database_with_image_in_richtext(client):
    """
    Database保存時、rich_text内の画像データが除去されること（統合テスト）
    """
    with patch("api.notion.create_page", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = "https://notion.so/page"

        payload = {
            "target_db_id": "db-id",
            "target_type": "database",
            "properties": {
                "Content": {
                    "rich_text": [
                        {
                            "text": {
                                "content": "Text with ![](data:image/jpeg;base64,xyz789) image"
                            }
                        }
                    ]
                }
            },
        }

        response = await client.post("/api/save", json=payload)
        assert response.status_code == 200

        # create_pageに渡されたプロパティを確認
        args, _ = mock_create.call_args
        props = args[1]
        content = props["Content"]["rich_text"][0]["text"]["content"]

        # 画像データが除去されていること
        assert "data:image" not in content
        assert "Text with" in content
        assert "image" in content


# ===== 4. GET /api/targets - 環境変数未設定エラー =====


@pytest.mark.asyncio
async def test_targets_no_root_page_error(client):
    """
    NOTION_ROOT_PAGE_IDが未設定の場合、500エラーとエラーメッセージが返ること
    """
    import os

    # 一時的に環境変数を削除
    original_value = os.environ.get("NOTION_ROOT_PAGE_ID")
    if "NOTION_ROOT_PAGE_ID" in os.environ:
        del os.environ["NOTION_ROOT_PAGE_ID"]

    try:
        from fastapi import Request

        mock_request = MagicMock(spec=Request)

        with patch(
            "api.endpoints.rate_limiter.check_rate_limit", new_callable=AsyncMock
        ):
            response = await client.get("/api/targets")

            assert response.status_code == 500
            detail = response.json()["detail"]
            assert "NOTION_ROOT_PAGE_ID" in detail
            assert ".env" in detail or "設定" in detail

    finally:
        # 環境変数を復元
        if original_value:
            os.environ["NOTION_ROOT_PAGE_ID"] = original_value


# ===== 5. AI APIタイムアウト処理 =====


@pytest.mark.asyncio
async def test_analyze_timeout_handling(client):
    """
    /api/analyze でタイムアウトが発生した場合、504エラーが返ること
    """

    with patch("api.endpoints.get_db_schema", new_callable=AsyncMock) as mock_schema:
        with patch(
            "api.notion.fetch_recent_pages", new_callable=AsyncMock
        ) as mock_recent:
            mock_schema.return_value = {}
            mock_recent.return_value = []

            # タイムアウトをシミュレート
            with patch(
                "api.ai.analyze_text_with_ai",
                side_effect=httpx.ReadTimeout("Timeout"),
            ):
                with patch(
                    "api.endpoints.rate_limiter.check_rate_limit",
                    new_callable=AsyncMock,
                ):
                    payload = {
                        "text": "test",
                        "target_db_id": "db-id",
                        "system_prompt": "prompt",
                    }

                    response = await client.post("/api/analyze", json=payload)

                    assert response.status_code == 504
                    detail = response.json()["detail"]
                    assert "error" in detail
                    assert detail["error"] == "Notion API Timeout"


@pytest.mark.asyncio
async def test_chat_timeout_handling(client):
    """
    /api/chat でタイムアウトが発生した場合、504エラーが返ること
    """
    with patch("api.endpoints.get_schema", new_callable=AsyncMock) as mock_schema:
        mock_schema.return_value = {"type": "page", "schema": {}}

        # タイムアウトをシミュレート
        with patch(
            "api.ai.chat_analyze_text_with_ai",
            side_effect=httpx.ReadTimeout("Timeout"),
        ):
            with patch(
                "api.endpoints.rate_limiter.check_rate_limit", new_callable=AsyncMock
            ):
                payload = {
                    "text": "test",
                    "target_id": "page-id",
                }

                response = await client.post("/api/chat", json=payload)

                assert response.status_code == 504
                detail = response.json()["detail"]
                assert "error" in detail


# ===== 6. Page 10000文字超え切り詰め =====


@pytest.mark.asyncio
async def test_save_page_truncation_10000_chars(client):
    """
    Page保存時、10000文字を超えるテキストが切り詰められ、...(Truncated)が付与されること
    """
    with patch("api.notion.append_block", new_callable=AsyncMock) as mock_append:
        mock_append.return_value = True

        # 15000文字のテキスト
        long_text = "a" * 15000

        payload = {
            "target_db_id": "page-id",
            "target_type": "page",
            "properties": {},
            "text": long_text,
        }

        response = await client.post("/api/save", json=payload)
        assert response.status_code == 200

        # append_blockに渡された引数を確認
        args, _ = mock_append.call_args
        saved_text = args[1]

        # 10000文字に切り詰められていること
        assert len(saved_text) <= 10025  # 10000 + "...(Truncated)" 程度
        assert "...(Truncated)" in saved_text or "Truncated" in saved_text
