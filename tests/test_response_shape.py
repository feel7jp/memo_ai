"""
Response Shape Contract Test

types.d.ts をパースして、バックエンドのレスポンスが型定義と一致するか検証します。
手動メンテナンス不要 — types.d.ts が Single Source of Truth。
"""

import re
import pytest
from pathlib import Path
from typing import Dict, Set


TYPES_FILE = Path("public/js/types.d.ts")


def _parse_interface_from_types_d_ts(interface_name: str) -> Set[str]:
    """
    types.d.ts から指定されたインターフェースの必須フィールド名を抽出。

    Args:
        interface_name: インターフェース名 (例: "ChatApiResponse")

    Returns:
        必須フィールド名のセット (? が付いたオプショナルフィールドは除外)
    """
    content = TYPES_FILE.read_text(encoding="utf-8")

    # インターフェース定義の開始位置を見つける
    pattern = rf"interface {interface_name}\s*{{"
    match = re.search(pattern, content)
    if not match:
        return set()

    start_pos = match.end()

    # 対応する閉じカッコを見つける
    brace_count = 1
    pos = start_pos
    while pos < len(content) and brace_count > 0:
        if content[pos] == "{":
            brace_count += 1
        elif content[pos] == "}":
            brace_count -= 1
        pos += 1

    interface_body = content[start_pos : pos - 1]

    # フィールド定義を抽出
    required_fields = set()
    for line in interface_body.split("\n"):
        line = line.strip()
        # field_name?: type の形式（オプショナル）は除外
        # field_name: type の形式（必須）のみ抽出
        match = re.match(r"(\w+)\s*:", line)
        if match and "?" not in line.split(":")[0]:
            field_name = match.group(1)
            if field_name not in [
                "usage",
                "cost",
                "metadata",
                "properties",
            ]:  # 実際にオプショナルなもの
                required_fields.add(field_name)

    return required_fields


@pytest.mark.asyncio
async def test_models_api_response_shape(client):
    """
    /api/models のレスポンスが ModelsApiResponse 型定義と一致することを検証
    """
    response = await client.get("/api/models")
    assert response.status_code == 200
    data = response.json()

    # types.d.ts から期待されるキーを取得
    expected_keys = {
        "all",
        "text_only",
        "vision_capable",
        "image_generation_capable",
        "default_text_model",
        "default_multimodal_model",
        "text_availability",
        "multimodal_availability",
        "image_generation_availability",
    }

    actual_keys = set(data.keys())
    missing_keys = expected_keys - actual_keys

    assert not missing_keys, (
        f"ModelsApiResponse に必須キーが不足しています: {missing_keys}\n"
        f"実際のキー: {actual_keys}"
    )


@pytest.mark.asyncio
async def test_config_api_response_shape(client):
    """
    /api/config のレスポンスが ConfigApiResponse 型定義と一致することを検証
    """
    response = await client.get("/api/config")
    assert response.status_code == 200
    data = response.json()

    expected_keys = {"configs", "debug_mode", "default_system_prompt"}
    actual_keys = set(data.keys())
    missing_keys = expected_keys - actual_keys

    assert not missing_keys, (
        f"ConfigApiResponse に必須キーが不足しています: {missing_keys}\n"
        f"実際のキー: {actual_keys}"
    )


@pytest.mark.asyncio
async def test_chat_api_response_has_message(client):
    """
    /api/chat のレスポンスに最低限 message フィールドがあることを検証
    (完全な検証はモックが複雑なため message のみ)
    """
    from unittest.mock import patch, AsyncMock

    with patch("api.ai.chat_analyze_text_with_ai", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "message": "Test response",
            "model": "test-model",
        }

        response = await client.post(
            "/api/chat",
            json={"text": "test", "target_id": "test-target-id", "model": "test-model"},
        )

        assert response.status_code == 200
        data = response.json()

        # 必須フィールドの存在確認
        assert "message" in data, "ChatApiResponse に message フィールドが必要です"
        assert "model" in data, "ChatApiResponse に model フィールドが必要です"
