"""
.env セキュリティチェックスクリプト

pre-commit フックから呼び出され、.env ファイルに実際のAPIキーが
含まれた状態でコミットされることを防止します。

チェック対象:
- NOTION_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY
- その他 _KEY, _SECRET, _TOKEN を含む変数名
"""

import sys
from pathlib import Path

# チェック対象の .env ファイルパス
ENV_FILE = Path(".env")

# 値が入っていたら警告する変数名パターン
SENSITIVE_SUFFIXES = ("_KEY", "_SECRET", "_TOKEN")

# 明示的にチェックする変数（値が空でなければ警告）
SENSITIVE_VARS = {
    "NOTION_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
}

# 値が入っていても許可するもの（プレースホルダーや安全な値）
SAFE_VALUES = {"", "False", "True", "false", "true"}

# 安全であることが明らかな変数（非秘密情報）
SAFE_VARS = {
    "DEBUG_MODE",
    "RATE_LIMIT_ENABLED",
    "RATE_LIMIT_GLOBAL_PER_HOUR",
    "LITELLM_VERBOSE",
    "LITELLM_TIMEOUT",
    "LITELLM_MAX_RETRIES",
    "VERTEX_AI_LOCATION",
}


def is_sensitive_var(var_name: str) -> bool:
    """変数名がセンシティブかどうか判定"""
    if var_name in SAFE_VARS:
        return False
    if var_name in SENSITIVE_VARS:
        return True
    return any(var_name.endswith(suffix) for suffix in SENSITIVE_SUFFIXES)


def check_env_file() -> list[str]:
    """
    .env ファイルをチェックし、実際の秘密情報が含まれている変数を返す。

    Returns:
        警告メッセージのリスト（空なら問題なし）
    """
    if not ENV_FILE.exists():
        return []

    warnings = []

    for line_num, line in enumerate(
        ENV_FILE.read_text(encoding="utf-8").splitlines(), 1
    ):
        # コメント行・空行をスキップ
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # KEY=VALUE の形式を解析
        if "=" not in stripped:
            continue

        var_name, _, var_value = stripped.partition("=")
        var_name = var_name.strip()
        var_value = var_value.strip()

        # コメント付きの値を処理（例: value  # comment）
        if "  #" in var_value:
            var_value = var_value.split("  #")[0].strip()

        # センシティブな変数に実際の値が入っているか
        if is_sensitive_var(var_name) and var_value and var_value not in SAFE_VALUES:
            warnings.append(
                f"  L{line_num}: {var_name} に値が設定されています（コミットしないでください）"
            )

    return warnings


def main() -> int:
    warnings = check_env_file()

    if warnings:
        print("❌ .env に実際の秘密情報が含まれています:")
        print()
        for w in warnings:
            print(w)
        print()
        print("💡 対処法:")
        print("  1. git reset HEAD .env  （ステージから除外）")
        print("  2. .gitignore に .env が含まれていることを確認")
        print("  3. 本当にコミットする場合: git commit --no-verify")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
