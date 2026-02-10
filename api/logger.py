"""
ロギングインフラ

全APIモジュールで使用する統一ロガーを提供します。
DEBUG_MODEに応じてログレベルを自動調整します。

[ANSI対策について]
LiteLLM (v1.x系) は内部loggerでANSIカラーコード付きのログを出力する。
例: "[92m03:54:19 - LiteLLM:INFO - completion() model=gemini...[0m"
Vercelのログ監視ツールはこの [92m (緑色コード) をエラーとして誤分類する。

対策: Vercel環境のみ StripAnsiFormatter でカラーコードを除去。
ログ自体は抑制せず内容を維持する（set_verbose=Falseとは別の問題）。

カラーコードがない文字列には何も起きないため、将来LiteLLMが
ANSI出力を止めた場合もこのコードは無害（除去対象がなくなるだけ）。
LiteLLMがANSI出力しなくなったことを確認できたら、このコードは削除可能。
"""

import logging
import os
import re
import sys
from api.config import DEBUG_MODE

# ANSIエスケープシーケンス除去用の正規表現
# LiteLLM等の外部ライブラリがカラーコード付きでログ出力するケースに対応
_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
IS_VERCEL = os.environ.get("VERCEL") == "1"


class StripAnsiFormatter(logging.Formatter):
    """
    ANSIカラーコードを除去するFormatter

    LiteLLMが出力する "[92m..." 等のエスケープシーケンスを除去し、
    Vercelのログ画面でエラー誤分類されることを防ぐ。
    カラーコードがない場合は何もしない（将来LiteLLMが修正されても安全）。
    """

    def format(self, record):
        formatted = super().format(record)
        return _ANSI_ESCAPE_RE.sub("", formatted)


def setup_logger(name: str) -> logging.Logger:
    """
    モジュール別ロガーのセットアップ

    Args:
        name: ロガー名（通常は__name__）

    Returns:
        設定済みLogger
    """
    logger = logging.getLogger(name)

    # ログレベル設定
    logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)

    # 既存ハンドラーがあればスキップ（重複防止）
    if logger.handlers:
        return logger

    # StreamHandler作成
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)

    # フォーマッター設定
    # Vercel環境ではANSIカラーコードを除去してログ誤分類を防止
    fmt_string = "[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    if IS_VERCEL:
        formatter = StripAnsiFormatter(fmt_string, datefmt=datefmt)
    else:
        formatter = logging.Formatter(fmt_string, datefmt=datefmt)
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False  # ルートロガーへの伝播を防止（重複出力防止）
    return logger


def configure_third_party_loggers():
    """
    外部ライブラリ（LiteLLM等）のロガーにANSIストリップFormatterを適用

    [背景]
    LiteLLMは独自のlogger ("LiteLLM", "litellm") でカラーコード付きログを出力する。
    Vercelのログ画面で [92m をエラーとして誤分類するため、Formatterで除去する。

    [不要になる条件]
    LiteLLMがANSIカラーコードをログに含めなくなった場合、この関数は不要。
    ただし残しておいても無害（除去対象がない場合は何もしない）。
    """
    if not IS_VERCEL:
        return

    fmt_string = "[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = StripAnsiFormatter(fmt_string, datefmt=datefmt)

    for logger_name in ("LiteLLM", "litellm"):
        lib_logger = logging.getLogger(logger_name)
        # 既存ハンドラーのFormatterを差し替え
        for handler in lib_logger.handlers:
            handler.setFormatter(formatter)
        # ハンドラーがなければ新規追加
        if not lib_logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(formatter)
            lib_logger.addHandler(handler)
            lib_logger.propagate = False

