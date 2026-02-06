"""
スキーマ検証テスト (Response Schema Validation)

APIレスポンスの形式が変わっていないことを保証し、
後方互換性を維持するためのテストです。

現実的で意味のあるテストのみ実装。
"""

import pytest
from unittest.mock import AsyncMock, patch


# ===== Phase 3: レスポンススキーマ検証（重要なもののみ） =====


@pytest.mark.regression
@pytest.mark.asyncio
async def test_config_response_schema(client):
    """
    デグレ検知: /api/config のレスポンス形式
    """
    response = await client.get("/api/config")
    data = response.json()

    # 必須キーの存在確認
    required_keys = ["configs", "debug_mode", "default_system_prompt"]
    for key in required_keys:
        assert key in data, f"Missing required key: {key}"

    # 型検証
    assert isinstance(data["configs"], list), "configs should be a list"
    assert isinstance(data["debug_mode"], bool), "debug_mode should be a boolean"
    assert isinstance(data["default_system_prompt"], str), (
        "default_system_prompt should be a string"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_models_response_schema(client):
    """
    デグレ検知: /api/models のレスポンス形式
    """
    response = await client.get("/api/models")
    data = response.json()

    # 必須キーの存在確認
    required_keys = ["all", "text_only", "vision_capable", "defaults"]
    for key in required_keys:
        assert key in data, f"Missing required key: {key}"

    # defaults構造の検証
    assert "text" in data["defaults"], "defaults.text is required"
    assert "multimodal" in data["defaults"], "defaults.multimodal is required"

    # 配列型の検証
    assert isinstance(data["all"], list), "all should be a list"
    assert isinstance(data["text_only"], list), "text_only should be a list"
    assert isinstance(data["vision_capable"], list), "vision_capable should be a list"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_save_response_schema(client):
    """
    デグレ検知: /api/save のレスポンス形式
    """
    with patch("api.notion.create_page", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = "https://notion.so/test-page"

        response = await client.post(
            "/api/save",
            json={
                "target_db_id": "test-db",
                "target_type": "database",
                "properties": {"Title": {"title": [{"text": {"content": "Test"}}]}},
            },
        )
        data = response.json()

        # 必須キーの存在確認
        assert "url" in data, "Missing required key: url"
        assert isinstance(data["url"], str), "url should be a string"
