"""
Unit tests for api.services module

Tests for business logic helpers extracted during Save Logic Unification refactoring.
"""

from api.services import (
    sanitize_image_data,
    _sanitize_rich_text_field,
    sanitize_notion_properties,
    ensure_title_property,
    create_content_blocks,
)


class TestSanitizeRichTextField:
    """Tests for _sanitize_rich_text_field helper"""

    def test_sanitizes_text_content(self):
        """Should remove Base64 images from text content"""
        items = [
            {"text": {"content": "Hello ![img](data:image/png;base64,abc123) world"}}
        ]
        result = _sanitize_rich_text_field(items, sanitize_image_data)
        assert result[0]["text"]["content"] == "Hello  world"

    def test_chunks_long_content(self):
        """Should split content longer than 2000 chars"""
        long_text = "A" * 2500
        items = [{"text": {"content": long_text}}]
        result = _sanitize_rich_text_field(items, sanitize_image_data)

        # Should be split into 2 chunks (2000 + 500)
        assert len(result) == 2
        assert len(result[0]["text"]["content"]) == 2000
        assert len(result[1]["text"]["content"]) == 500

    def test_handles_empty_list(self):
        """Should handle empty item list"""
        result = _sanitize_rich_text_field([], sanitize_image_data)
        assert result == []

    def test_preserves_items_without_text(self):
        """Should preserve items that don't have text field"""
        items = [{"type": "mention", "mention": {"type": "page"}}]
        result = _sanitize_rich_text_field(items, sanitize_image_data)
        assert len(result) == 1
        assert result[0]["type"] == "mention"


class TestSanitizeNotionProperties:
    """Tests for sanitize_notion_properties helper"""

    def test_sanitizes_rich_text_properties(self):
        """Should sanitize rich_text property values"""
        props = {
            "Description": {
                "rich_text": [
                    {"text": {"content": "Test ![img](data:image/png;base64,xyz) text"}}
                ]
            }
        }
        result = sanitize_notion_properties(props)
        assert "Description" in result
        assert result["Description"]["rich_text"][0]["text"]["content"] == "Test  text"

    def test_sanitizes_title_properties(self):
        """Should sanitize title property values"""
        props = {"Name": {"title": [{"text": {"content": "Title [画像送信] text"}}]}}
        result = sanitize_notion_properties(props)
        assert result["Name"]["title"][0]["text"]["content"] == "Title  text"

    def test_handles_non_dict_values(self):
        """Should skip non-dict property values"""
        props = {
            "ValidProp": {"rich_text": [{"text": {"content": "test"}}]},
            "InvalidProp": "not a dict",
        }
        result = sanitize_notion_properties(props)
        assert "ValidProp" in result
        assert result["InvalidProp"] == "not a dict"

    def test_handles_empty_properties(self):
        """Should handle empty properties dict"""
        result = sanitize_notion_properties({})
        assert result == {}


class TestEnsureTitleProperty:
    """Tests for ensure_title_property helper"""

    def test_preserves_existing_title(self):
        """Should not modify if title already exists"""
        props = {"Title": {"title": [{"text": {"content": "Existing Title"}}]}}
        result = ensure_title_property(props, "Fallback text")
        assert result["Title"]["title"][0]["text"]["content"] == "Existing Title"
        assert "Name" not in result

    def test_generates_title_from_fallback(self):
        """Should generate title from fallback text if missing"""
        props = {"Description": {"rich_text": []}}
        result = ensure_title_property(props, "This is fallback text")
        assert "Name" in result
        assert result["Name"]["title"][0]["text"]["content"] == "This is fallback text"

    def test_truncates_long_titles(self):
        """Should truncate titles longer than 100 chars"""
        long_text = "A" * 150
        props = {}
        result = ensure_title_property(props, long_text)
        assert len(result["Name"]["title"][0]["text"]["content"]) == 100

    def test_uses_first_line_only(self):
        """Should use only first line of multiline text"""
        multiline = "First line\nSecond line\nThird line"
        props = {}
        result = ensure_title_property(props, multiline)
        assert result["Name"]["title"][0]["text"]["content"] == "First line"

    def test_handles_none_fallback(self):
        """Should handle None fallback text"""
        props = {}
        result = ensure_title_property(props, None)
        assert result["Name"]["title"][0]["text"]["content"] == "Untitled"


class TestCreateContentBlocks:
    """Tests for create_content_blocks helper"""

    def test_creates_single_block_for_short_text(self):
        """Should create single paragraph block for text under 2000 chars"""
        text = "This is a short text"
        result = create_content_blocks(text)

        assert len(result) == 1
        assert result[0]["type"] == "paragraph"
        assert result[0]["object"] == "block"
        assert result[0]["paragraph"]["rich_text"][0]["text"]["content"] == text

    def test_chunks_long_text(self):
        """Should split text longer than chunk_size into multiple blocks"""
        text = "A" * 2500
        result = create_content_blocks(text, chunk_size=2000)

        assert len(result) == 2
        assert result[0]["paragraph"]["rich_text"][0]["text"]["content"] == "A" * 2000
        assert result[1]["paragraph"]["rich_text"][0]["text"]["content"] == "A" * 500

    def test_handles_empty_text(self):
        """Should return empty list for empty text"""
        result = create_content_blocks("")
        assert result == []

    def test_handles_none_text(self):
        """Should return empty list for None text"""
        result = create_content_blocks(None)
        assert result == []

    def test_custom_chunk_size(self):
        """Should respect custom chunk_size parameter"""
        text = "A" * 150
        result = create_content_blocks(text, chunk_size=100)

        assert len(result) == 2
        assert len(result[0]["paragraph"]["rich_text"][0]["text"]["content"]) == 100
        assert len(result[1]["paragraph"]["rich_text"][0]["text"]["content"]) == 50
