"""
JSON Mode 互換性 統合テスト

画像生成モデルで JSON mode が正しく判定されることを確認する統合テスト。
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestJsonModeIntegration:
    """JSON mode互換性の統合テスト"""

    @pytest.mark.asyncio
    async def test_image_model_automatically_skips_json_mode(self):
        """
        supports_response_schema が False を返すモデルでは、
        自動的に JSON mode がスキップされること
        """
        from api.llm_client import generate_json

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"title": "Generated Image"}'
        mock_response.usage = MagicMock()
        mock_response.usage.model_dump.return_value = {"total_tokens": 50}

        # supports_response_schema を明示的に False にモック
        # （LiteLLMのバージョンによって実際の戻り値が変わるため）
        with patch("api.llm_client.supports_response_schema", return_value=False):
            with patch("api.llm_client.acompletion", new_callable=AsyncMock) as mock_ac:
                mock_ac.return_value = mock_response
                with patch("api.llm_client.completion_cost", return_value=0.0):
                    result = await generate_json(
                        "Describe this image", "gemini/gemini-2.5-flash-image"
                    )

                # acompletion が response_format なしで呼ばれたことを確認
                call_kwargs = mock_ac.call_args.kwargs
                assert "response_format" not in call_kwargs
                assert call_kwargs["drop_params"] is True
                assert result["model"] == "gemini/gemini-2.5-flash-image"

    @pytest.mark.asyncio
    async def test_text_model_automatically_uses_json_mode(self):
        """
        テキストモデルを使用時、自動的に JSON mode が適用されること
        """
        from api.llm_client import generate_json

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"summary": "Test response"}'
        mock_response.usage = MagicMock()
        mock_response.usage.model_dump.return_value = {"total_tokens": 30}

        # 実際の supports_response_schema を使用（モックしない）
        with patch("api.llm_client.acompletion", new_callable=AsyncMock) as mock_ac:
            mock_ac.return_value = mock_response
            with patch("api.llm_client.completion_cost", return_value=0.0):
                # gemini-2.5-flash は自動的に JSON mode を適用するはず
                result = await generate_json(
                    "Summarize this text", "gemini/gemini-2.5-flash"
                )

            # acompletion が response_format 付きで呼ばれたことを確認
            call_kwargs = mock_ac.call_args.kwargs
            assert call_kwargs["response_format"] == {"type": "json_object"}
            assert call_kwargs["drop_params"] is True
            assert result["model"] == "gemini/gemini-2.5-flash"

    def test_model_discovery_sets_correct_json_support(self):
        """
        モデル検出時に正しく supports_json が設定されること
        """
        from api.model_discovery import get_gemini_models

        # 実際のモデル検出を実行
        models = get_gemini_models()

        # モデルが見つかった場合のみテスト
        if models:
            for model in models:
                model_name = model.get("name", "")
                supports_json = model.get("supports_json", True)

                # 画像生成モデルは supports_json=False のはず
                if "image" in model_name.lower():
                    assert supports_json is False, (
                        f"Image model '{model_name}' should have supports_json=False"
                    )
                # 特殊モデル（deep-research等）やembedding系は除外
                elif "deep" in model_name.lower() or "embed" in model_name.lower():
                    # スキップ（特殊用途のモデル）
                    pass
                # 通常のテキストモデルは supports_json=True のはず
                else:
                    assert supports_json is True, (
                        f"Text model '{model_name}' should have supports_json=True"
                    )
