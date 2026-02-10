"""
Unit tests for extract_plain_text helper function

散在していた plain_text 抽出パターンの
共通ヘルパーが正しく動作することを検証します。
"""

from api.services import extract_plain_text


class TestExtractPlainText:
    """extract_plain_text 関数のテスト"""

    def test_basic_extraction(self):
        """基本的な rich_text 配列からテキストを抽出"""
        items = [
            {"plain_text": "Hello "},
            {"plain_text": "World"},
        ]
        assert extract_plain_text(items) == "Hello World"

    def test_empty_list(self):
        """空リストは空文字列を返す"""
        assert extract_plain_text([]) == ""

    def test_none_input(self):
        """None入力は空文字列を返す"""
        assert extract_plain_text(None) == ""

    def test_items_without_plain_text_key(self):
        """plain_text キーがない要素は空文字として扱われる"""
        items = [
            {"plain_text": "Hello"},
            {"type": "mention"},  # plain_text キーなし
            {"plain_text": " World"},
        ]
        assert extract_plain_text(items) == "Hello World"

    def test_single_item(self):
        """単一要素の配列"""
        items = [{"plain_text": "単独テキスト"}]
        assert extract_plain_text(items) == "単独テキスト"

    def test_empty_plain_text(self):
        """plain_text が空文字の要素"""
        items = [
            {"plain_text": ""},
            {"plain_text": "text"},
        ]
        assert extract_plain_text(items) == "text"
