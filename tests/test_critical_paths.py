"""
クリティカルパステスト（統合テスト）

デグレッション検知のため、ユーザーの主要ワークフローを検証します。
現実的で意味のあるテストのみを実装。
"""

import pytest
from unittest.mock import AsyncMock, patch


# ===== 統合テスト: 単純だが重要なワークフロー =====


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
async def test_database_and_page_save_different_structures(client):
    """
    デグレ検知: Database保存とPage保存で異なるプロパティ構造を正しく処理
    """
    # Database保存（properties）
    with patch("api.notion.create_page", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = "https://notion.so/db-page"

        db_save_resp = await client.post(
            "/api/save",
            json={
                "target_db_id": "db-1",
                "target_type": "database",
                "properties": {
                    "Title": {"title": [{"text": {"content": "Database Entry"}}]}
                },
            },
        )
        assert db_save_resp.status_code == 200
        assert "url" in db_save_resp.json()

    # Page保存（children）
    with patch("api.notion.append_block", new_callable=AsyncMock) as mock_append:
        mock_append.return_value = {"results": [{"id": "block-1"}]}

        page_save_resp = await client.post(
            "/api/save",
            json={
                "target_db_id": "page-1",
                "target_type": "page",
                "properties": {
                    "children": [
                        {
                            "paragraph": {
                                "rich_text": [{"text": {"content": "Page Content"}}]
                            }
                        }
                    ]
                },
            },
        )
        assert page_save_resp.status_code == 200
        assert "url" in page_save_resp.json()
