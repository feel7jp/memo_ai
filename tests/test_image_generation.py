"""
Image Generation Regression Tests

Tests for llm_client.generate_image_response() and
chat_analyze_text_with_ai() の画像生成エラーハンドリングをテスト。

カバー範囲:
- Geminiパス: テキスト付き/なし画像生成、テキストのみ応答、空応答
- OpenAIパス: 空レスポンス、コンテンツポリシー違反
- ai.py統合: 画像生成失敗時のフラグ・メッセージ・セキュリティ
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
        mock_response.usage.model_dump.return_value = {
            "completion_tokens": 1315,
            "prompt_tokens": 15,
            "total_tokens": 1330,
            "completion_tokens_details": {
                "text_tokens": 25,
                "image_tokens": 1290,
            },
            "prompt_tokens_details": {
                "text_tokens": 15,
                "image_tokens": None,
            },
        }

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
        mock_response.usage.model_dump.return_value = {
            "completion_tokens": 1315,
            "prompt_tokens": 15,
            "total_tokens": 1330,
            "completion_tokens_details": {
                "text_tokens": 25,
                "image_tokens": 1290,
            },
            "prompt_tokens_details": {
                "text_tokens": 15,
                "image_tokens": None,
            },
        }

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
        mock_response.usage.model_dump.return_value = {
            "completion_tokens": 800,
            "prompt_tokens": 10,
            "total_tokens": 810,
            "completion_tokens_details": {
                "text_tokens": 0,
                "image_tokens": 800,
            },
            "prompt_tokens_details": {
                "text_tokens": 10,
                "image_tokens": None,
            },
        }

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_ac:
            mock_ac.return_value = mock_response
            with patch("litellm.completion_cost", return_value=0.0):
                result = await generate_image_response(
                    "猫", "gemini/gemini-2.5-flash-image"
                )

        assert result["message"] == "画像を生成しました"
        assert result["image_base64"] == "abc123"

    @pytest.mark.asyncio
    async def test_gemini_text_only_response_raises(self):
        """
        AIがテキストのみ返し画像なし → エラーメッセージにAI応答の要約が含まれること。
        実際のケース: プロンプトが不適切でAIが画像生成せずテキストで応答。
        """
        from api.llm_client import generate_image_response

        mock_message = MagicMock()
        mock_message.content = "申し訳ありませんが、その内容の画像は生成できません。"
        mock_message.images = []  # 画像なし

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = mock_message
        mock_response.usage = MagicMock()
        mock_response.usage.model_dump.return_value = {
            "completion_tokens": 30, "prompt_tokens": 100, "total_tokens": 130,
        }

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_ac:
            mock_ac.return_value = mock_response
            with patch("litellm.completion_cost", return_value=0.0):
                with pytest.raises(RuntimeError) as exc_info:
                    await generate_image_response(
                        "長い要約テキスト...", "gemini/gemini-2.5-flash-image"
                    )

        # 外側のexceptで "Image generation failed: ..." にラップされる
        assert "Image generation failed" in str(exc_info.value)
        # エラーメッセージにAIの応答テキスト要約が含まれる
        assert "AIが画像ではなくテキストで応答しました" in str(exc_info.value)
        assert "画像は生成できません" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_gemini_no_text_no_image_raises(self):
        """AIがテキストも画像も返さない場合 → 適切なエラーメッセージ"""
        from api.llm_client import generate_image_response

        mock_message = MagicMock()
        mock_message.content = None
        mock_message.images = None

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = mock_message
        mock_response.usage = MagicMock()
        mock_response.usage.model_dump.return_value = {
            "completion_tokens": 0, "prompt_tokens": 10, "total_tokens": 10,
        }

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_ac:
            mock_ac.return_value = mock_response
            with patch("litellm.completion_cost", return_value=0.0):
                with pytest.raises(RuntimeError) as exc_info:
                    await generate_image_response(
                        "test", "gemini/gemini-2.5-flash-image"
                    )

        # テキストも画像もない場合のエラーメッセージ
        assert "AIから画像データが返されませんでした" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_openai_empty_response_raises(self):
        """OpenAI DALL-Eが空のレスポンスを返す場合 → RuntimeError"""
        from api.llm_client import generate_image_response

        mock_response = MagicMock()
        mock_response.data = []  # 空の画像データ

        with patch("litellm.aimage_generation", new_callable=AsyncMock) as mock_ig:
            mock_ig.return_value = mock_response
            with pytest.raises(RuntimeError) as exc_info:
                await generate_image_response(
                    "a cute cat", "openai/dall-e-3"
                )

        assert "Image generation failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_openai_content_policy_violation_raises(self):
        """OpenAI DALL-Eのコンテンツポリシー違反 → RuntimeError"""
        from api.llm_client import generate_image_response
        from openai import BadRequestError

        policy_error = BadRequestError(
            message="Your request was rejected due to content policy violation",
            response=MagicMock(status_code=400),
            body={"error": {"code": "content_policy_violation"}},
        )

        with patch("litellm.aimage_generation", new_callable=AsyncMock) as mock_ig:
            mock_ig.side_effect = policy_error
            with pytest.raises(RuntimeError) as exc_info:
                await generate_image_response(
                    "inappropriate content", "openai/dall-e-3"
                )

        assert "Image generation failed" in str(exc_info.value)
        assert "content policy" in str(exc_info.value).lower() or "rejected" in str(exc_info.value).lower()


class TestImageGenFailureInChatAI:
    """chat_analyze_text_with_ai 経由の画像生成失敗テスト"""

    @pytest.mark.asyncio
    async def test_image_gen_failure_returns_flag_and_message(self):
        """画像生成失敗時に _image_gen_failed=True と日本語メッセージを返すこと"""
        from api.ai import chat_analyze_text_with_ai

        error = RuntimeError("Image generation failed: AIが画像ではなくテキストで応答しました")

        with patch("api.llm_client.generate_image_response", new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = error
            result = await chat_analyze_text_with_ai(
                text="猫の絵を描いて",
                schema={"title": {"type": "title"}},
                system_prompt="test",
                image_generation=True,
            )

        assert result["_image_gen_failed"] is True
        assert "画像は生成されませんでした" in result["message"]
        assert result["image_base64"] is None
        # セキュリティ: AIの生応答テキストはレスポンスに含まれない
        assert "_debug_ai_response" not in result
