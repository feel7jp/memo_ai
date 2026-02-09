"""
Image Generation Regression Tests

Tests for llm_client.generate_image_response() to prevent regressions.
Specifically covers the case where Gemini generates an image without text.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestGenerateImageResponse:
    """generate_image_response 関数のテスト"""

    @pytest.mark.asyncio
    async def test_gemini_image_generation_with_text(self):
        """Gemini画像生成: テキストメッセージ付き画像"""
        from api.llm_client import generate_image_response

        mock_message = MagicMock()
        mock_message.content = "Here's a cute dog!"
        mock_message.images = [
            {"image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANS"}}
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = mock_message
        mock_response.usage = MagicMock()
        mock_response.usage.model_dump.return_value = {"total_tokens": 100}

        # NOTE: generate_image_response does `from litellm import acompletion` locally,
        # so we must mock `litellm.acompletion`, not `api.llm_client.acompletion`
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_ac:
            mock_ac.return_value = mock_response
            with patch("litellm.completion_cost", return_value=0.01):
                result = await generate_image_response(
                    "dog", "gemini/gemini-2.5-flash-image"
                )

        assert result["message"] == "Here's a cute dog!"
        assert result["image_base64"] == "iVBORw0KGgoAAAANS"
        assert "usage" in result
        assert "cost" in result

    @pytest.mark.asyncio
    async def test_gemini_image_generation_without_text(self):
        """
        REGRESSION TEST: Gemini画像生成でテキストなしの場合、
        デフォルトメッセージ「画像を生成しました」を返すこと。
        """
        from api.llm_client import generate_image_response

        mock_message = MagicMock()
        mock_message.content = ""  # Empty text - the bug case
        mock_message.images = [
            {"image_url": {"url": "data:image/png;base64,testbase64data"}}
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = mock_message
        mock_response.usage = MagicMock()
        mock_response.usage.model_dump.return_value = {"total_tokens": 100}

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_ac:
            mock_ac.return_value = mock_response
            with patch("litellm.completion_cost", return_value=0.01):
                result = await generate_image_response(
                    "犬", "gemini/gemini-2.5-flash-image"
                )

        # CRITICAL: message should NOT be empty even if content is empty
        assert result["message"], (
            "Message should have default value when image is generated"
        )
        assert result["message"] == "画像を生成しました"
        assert result["image_base64"] == "testbase64data"

    @pytest.mark.asyncio
    async def test_gemini_image_generation_none_content(self):
        """
        REGRESSION TEST: message.content が None の場合もデフォルトメッセージを返すこと。
        """
        from api.llm_client import generate_image_response

        mock_message = MagicMock()
        mock_message.content = None  # None content
        mock_message.images = [{"image_url": {"url": "data:image/png;base64,abc123"}}]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = mock_message
        mock_response.usage = MagicMock()
        mock_response.usage.model_dump.return_value = {"total_tokens": 50}

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_ac:
            mock_ac.return_value = mock_response
            with patch("litellm.completion_cost", return_value=0.0):
                result = await generate_image_response(
                    "猫", "gemini/gemini-2.5-flash-image"
                )

        assert result["message"] == "画像を生成しました"
        assert result["image_base64"] == "abc123"
