"""
ロギングインフラ

全APIモジュールで使用する統一ロガーを提供します。
DEBUG_MODEに応じてログレベルを自動調整します。
"""

import logging
import sys
from api.config import DEBUG_MODE


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
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False  # ルートロガーへの伝播を防止（重複出力防止）
    return logger
