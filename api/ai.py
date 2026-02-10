"""
AI プロンプト構築モジュール (AI Prompt Construction)

Notionへのデータ登録やチャット応答のために、AI（LLM）に送信するプロンプトを作成するロジックを担当します。
データベースのスキーマ構造や過去のデータ例をコンテキストとして組み込むことで、
AIが適切なJSON形式で回答できるように誘導します。
"""

import json
from typing import Dict, Any, List, Optional

from api.llm_client import generate_json, prepare_multimodal_prompt
from api.models import select_model_for_input
from api.services import extract_plain_text
from api.logger import setup_logger

logger = setup_logger(__name__)


def _format_schema_for_prompt(schema: Dict[str, Any]) -> Dict[str, str]:
    """
    スキーマをAIプロンプト用の簡略表現に変換

    Notionの複雑なスキーマオブジェクトをAIが理解しやすい形式に整形します。
    select/multi_selectタイプの場合は選択肢も含めます。

    Args:
        schema: Notionデータベース/ページのスキーマ情報

    Returns:
        簡略化されたスキーマ辞書 (e.g., {"Status": "select options: ['未着手', '進行中']"})
    """
    info = {}
    for k, v in schema.items():
        if not isinstance(v, dict) or "type" not in v:
            continue
        info[k] = v["type"]
        if v["type"] == "select" and "select" in v:
            info[k] += f" options: {[o['name'] for o in v['select']['options']]}"
        elif v["type"] == "multi_select" and "multi_select" in v:
            info[k] += f" options: {[o['name'] for o in v['multi_select']['options']]}"
    return info


def construct_prompt(
    text: str,
    schema: Dict[str, Any],
    recent_examples: List[Dict[str, Any]],
    system_prompt: str,
) -> str:
    """
    タスク抽出・プロパティ推定のための完全なプロンプトを構築します。

    Args:
        text (str): ユーザーの入力テキスト
        schema (Dict): 対象Notionデータベースのスキーマ情報
        recent_examples (List): データベースの直近の登録データ（Few-shot学習用）
        system_prompt (str): AIへの役割指示（システムプロンプト）

    Returns:
        str: LLMに送信するプロンプト文字列全体
    """
    # 1. スキーマ情報の整形
    schema_info = _format_schema_for_prompt(schema)

    # 2. 過去データの整形 (Few-shot prompting)
    # 過去のデータ例を提示することで、AIに入力の傾向や期待するフォーマットを学習させます。
    examples_text = ""
    if recent_examples:
        for ex in recent_examples:
            props = ex.get("properties", {})
            simple_props = {}
            # プロパティの型に応じて値を抽出・簡略化
            for k, v in props.items():
                p_type = v.get("type")
                val = "N/A"
                if p_type == "title":
                    val = extract_plain_text(v.get("title", []))
                elif p_type == "rich_text":
                    val = extract_plain_text(v.get("rich_text", []))
                elif p_type == "select":
                    val = v.get("select", {}).get("name") if v.get("select") else None
                elif p_type == "multi_select":
                    val = [o.get("name") for o in v.get("multi_select", [])]
                elif p_type == "date":
                    val = v.get("date", {}).get("start") if v.get("date") else None
                elif p_type == "checkbox":
                    val = v.get("checkbox")
                simple_props[k] = val
            examples_text += f"- {json.dumps(simple_props, ensure_ascii=False)}\n"

    # プロンプトの組み立て
    # システムプロンプト + スキーマ定義 + データ例 + ユーザー入力 を結合
    prompt = f"""
{system_prompt}

Target Database Schema:
{json.dumps(schema_info, indent=2, ensure_ascii=False)}

Recent Examples:
{examples_text}

User Input:
{text}

Output JSON format strictly. NO markdown code blocks.
"""
    return prompt


def validate_and_fix_json(json_str: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    AIのJSON応答を解析・検証・修正する関数

    LLMは時にMarkdownコードブロックを含んだり、不正なJSONを返したりするため、
    それらをクリーニングしてPython辞書として安全に取り出します。
    さらに、スキーマ定義に従って型変換（キャスト）を行い、Notion APIでエラーにならない形式に整えます。
    """
    # 1. Markdown記法の除去
    # ```json ... ``` のような装飾を取り除きます。
    json_str = json_str.strip()
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    if json_str.startswith("```"):
        json_str = json_str[3:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    json_str = json_str.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # JSONパース失敗時の簡易リトライ
        # 余計な接頭辞/接尾辞がある場合に、最初の中括弧 { と最後の中括弧 } の間を抽出して再試行します。
        start = json_str.find("{")
        end = json_str.rfind("}") + 1
        if start != -1 and end != -1:
            try:
                data = json.loads(json_str[start:end])
            except Exception:
                # 復旧不能な場合は空の辞書を返して安全に終了
                return {}
        else:
            return {}

    # 2. プロパティの型検証とキャスト (Robust Property Validation)
    # Notion APIは型に厳格なため、スキーマ情報を基に各値を適切な形式に変換します。
    validated = {}
    for k, v in data.items():
        if k not in schema:
            continue

        target_type = schema[k]["type"]

        # 型ごとの詳細な処理
        if target_type == "select":
            # Select型: 文字列に変換
            if isinstance(v, dict):
                v = v.get("name")
            if v:
                validated[k] = {"select": {"name": str(v)}}

        elif target_type == "multi_select":
            # Multi-Select型: 文字列のリストに変換
            if not isinstance(v, list):
                v = [v]
            opts = []
            for item in v:
                if isinstance(item, dict):
                    item = item.get("name")
                if item:
                    opts.append({"name": str(item)})
            validated[k] = {"multi_select": opts}

        elif target_type == "status":
            # Status型
            if isinstance(v, dict):
                v = v.get("name")
            if v:
                validated[k] = {"status": {"name": str(v)}}

        elif target_type == "date":
            # Date型: YYYY-MM-DD 文字列を期待
            if isinstance(v, dict):
                v = v.get("start")
            if v:
                validated[k] = {"date": {"start": str(v)}}

        elif target_type == "checkbox":
            # Checkbox型: 真偽値
            validated[k] = {"checkbox": bool(v)}

        elif target_type == "number":
            # Number型: 数値変換
            try:
                if v is not None:
                    validated[k] = {"number": float(v)}
            except (ValueError, TypeError):
                # 数値変換に失敗した場合はスキップ
                # 例: "abc" -> float() は ValueError
                pass

        elif target_type == "title":
            # Title型: Rich Text オブジェクト構造
            if isinstance(v, list):
                v = extract_plain_text(v)
            validated[k] = {"title": [{"text": {"content": str(v)}}]}

        elif target_type == "rich_text":
            # Rich Text型
            if isinstance(v, list):
                v = extract_plain_text(v)
            validated[k] = {"rich_text": [{"text": {"content": str(v)}}]}

        elif target_type == "people":
            # ユーザーIDが必要なため、現在は無視（実装難易度高）
            pass

        elif target_type == "files":
            # ファイルアップロードは複雑なため無視
            pass

    return validated


# --- NEW: High-level entry points ---


async def analyze_text_with_ai(
    text: str,
    schema: Dict[str, Any],
    recent_examples: List[Dict[str, Any]],
    system_prompt: str,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    テキスト分析とプロパティ抽出のメイン関数

    1. 最適なモデルの選択（テキストのみ/画像あり）
    2. プロンプトの構築
    3. LLMの呼び出し
    4. 結果の解析とプロパティのクリーニング
    を一括して行います。

    Args:
        text: ユーザー入力テキスト
        schema: Notionデータベーススキーマ
        recent_examples: 最近の登録データ（コンテキスト用）
        system_prompt: システムからの指示
        model: モデルの明示的な指定（省略時は自動選択）

    Returns:
        {
            "properties": {...},  # Notion登録用プロパティ
            "usage": {...},       # トークン使用量
            "cost": float,        # 推定コスト
            "model": str          # 使用されたモデル名
        }
    """
    # モデルの自動選択（この関数はテキスト入力のみを想定）
    selected_model = select_model_for_input(has_image=False, user_selection=model)

    # プロンプトの構築
    prompt = construct_prompt(text, schema, recent_examples, system_prompt)

    try:
        # LLM呼び出し
        result = await generate_json(prompt, model=selected_model)

        # プロパティの検証と修正
        properties = validate_and_fix_json(result["content"], schema)

        return {
            "properties": properties,
            "usage": result["usage"],
            "cost": result["cost"],
            "model": result["model"],
        }

    except Exception as e:
        logger.error("AI Analysis Failed: %s", e, exc_info=True)

        # エラー時のフォールバック処理
        # AI分析に失敗しても、ユーザーの入力テキストをタイトルとして保存できるように
        # 最低限のプロパティ構造を作成して返します。
        fallback = {}
        for k, v in schema.items():
            if v["type"] == "title":
                fallback[k] = {"title": [{"text": {"content": text}}]}
                break

        return {
            "properties": fallback,
            "usage": {},
            "cost": 0.0,
            "model": selected_model,
            "error": str(e),
        }


async def chat_analyze_text_with_ai(
    text: str,
    schema: Dict[str, Any],
    system_prompt: str,
    session_history: Optional[List[Dict[str, str]]] = None,
    image_data: Optional[str] = None,
    image_mime_type: Optional[str] = None,
    model: Optional[str] = None,
    image_generation: bool = False,
) -> Dict[str, Any]:
    """
    インタラクティブチャット分析のメイン関数 (画像対応・画像生成対応)

    テキストだけでなく、画像データ（Base64）を含めたマルチモーダルな対話を処理します。
    会話履歴を考慮し、ユーザーとの自然な対話を行いながら、必要に応じてタスク情報（properties）を抽出します。
    また、image_generation=Trueの場合は画像生成モードとして動作します。

    Args:
        text: ユーザー入力テキスト
        schema: Notionの対象スキーマ
        system_prompt: システム指示
        session_history: 過去の会話履歴
        image_data: Base64エンコードされた画像データ（任意）
        image_mime_type: 画像のMIMEタイプ（任意）
        model: モデル指定
        image_generation: 画像生成モード（True: 画像を生成, False: テキスト応答）

    Returns:
        dict: メッセージ、精製テキスト、抽出プロパティ、メタデータを含む辞書
    """
    # 画像生成モードの処理
    if image_generation:
        from api.llm_client import generate_image_response

        logger.info("[Chat AI] Image generation mode activated")

        # 画像生成用モデル選択
        requested_model = model or "auto"
        selected_model = select_model_for_input(
            has_image=False, user_selection=model, image_generation=True
        )

        logger.info("[Chat AI] Selected image generation model: %s", selected_model)

        try:
            result = await generate_image_response(
                prompt=text or "Generate an image", model=selected_model
            )

            # 画像生成レスポンスの整形
            return {
                "message": result["message"],
                "image_base64": result["image_base64"],
                "properties": None,  # 画像生成時はNotion保存なし
                "usage": result["usage"],
                "cost": result["cost"],
                "model": result["model"],
                "model_selection": {
                    "requested": requested_model,
                    "used": selected_model,
                    "fallback_occurred": bool(model and model != selected_model),
                },
            }

        except Exception as e:
            error_msg = str(e)
            # RuntimeError("Image generation failed: ...") のラッパー部分を除去
            if "Image generation failed: " in error_msg:
                error_msg = error_msg.replace("Image generation failed: ", "")

            return {
                "message": f"⚠️ 画像は生成されませんでした\n{error_msg}",
                "image_base64": None,
                "properties": None,
                "usage": {},
                "cost": 0.0,
                "model": selected_model,
                "_image_gen_failed": True,
                "model_selection": {
                    "requested": requested_model,
                    "used": selected_model,
                    "fallback_occurred": False,
                },
            }

    # 通常のテキスト/画像認識モードの処理（既存ロジック）
    # 画像の有無に基づくモデル自動選択
    has_image = bool(image_data and image_mime_type)
    logger.debug("[Chat AI] Has image: %s, User model selection: %s", has_image, model)

    # モデル選択の透明性: リクエストされたモデルと実際に使用されたモデルを記録
    requested_model = model or "auto"
    selected_model = select_model_for_input(has_image=has_image, user_selection=model)
    model_fallback_occurred = bool(model and model != selected_model)

    logger.debug("[Chat AI] Selected model: %s", selected_model)
    if model_fallback_occurred:
        logger.info(
            "[Chat AI] Model fallback occurred: requested '%s' -> using '%s'",
            model,
            selected_model,
        )

    # 会話履歴の準備
    logger.debug(
        "[Chat AI] Constructing messages, schema keys: %d, history length: %d",
        len(schema),
        len(session_history) if session_history else 0,
    )

    # スキーマ情報の整形
    schema_info = _format_schema_for_prompt(schema)

    # システムプロンプトの構築
    system_message_content = f"""{system_prompt}

Target Schema:
{json.dumps(schema_info, indent=2, ensure_ascii=False)}

Restraints:
- You are a helpful AI assistant.
- Your output must be valid JSON ONLY.
- Structure:
{{
  "message": "Response to the user (required)",
  "properties": {{ "Property Name": "Value" }} // Only if user intends to save data
}}
- If the user is just chatting, "properties" should be null.
- If the user wants to save/add data, fill "properties" according to the Schema."""

    # メッセージ配列の構築
    messages = [{"role": "system", "content": system_message_content}]

    # 会話履歴を追加（画像データは含まれない、テキストのみ）
    if session_history:
        messages.extend(session_history)

    # 現在のユーザー入力を追加
    if has_image:
        # マルチモーダル: 画像データを含むコンテンツパーツを作成
        logger.debug("[Chat AI] Preparing multimodal message with image")
        current_user_content = prepare_multimodal_prompt(
            text or "(No text provided)", image_data, image_mime_type
        )
        messages.append({"role": "user", "content": current_user_content})
    else:
        # テキストのみ
        messages.append({"role": "user", "content": text or "(No text provided)"})

    # LLMの呼び出し（messages配列を渡す）
    logger.info(
        "[Chat AI] Calling LLM: %s with %d messages", selected_model, len(messages)
    )

    try:
        result = await generate_json(messages, model=selected_model)
        logger.debug(
            "[Chat AI] LLM response received, length: %d", len(result["content"])
        )
        json_resp = result["content"]

    except Exception as e:
        logger.error("[Chat AI] LLM generation failed: %s", e, exc_info=True)
        # エラーメッセージをユーザーに返す
        error_msg = str(e)
        user_msg = "申し訳ありません。AIの応答生成中にエラーが発生しました。"

        # APIキー関連のエラーの場合のヒント
        if "API key" in error_msg or "auth" in error_msg.lower():
            user_msg += "\n(APIキーが設定されていないか、正しくない可能性があります)"

        return {
            "message": user_msg,
            "raw_error": error_msg,
            "properties": None,
            "usage": {},
            "cost": 0.0,
            "model": selected_model,
            "model_selection": {
                "requested": requested_model,
                "used": selected_model,
                "fallback_occurred": model_fallback_occurred,
            },
        }

    # 応答データの解析
    try:
        data = json.loads(json_resp)

        # 文字列が返ってきた場合の対応（LLMがJSON形式を返さなかった場合）
        if isinstance(data, str):
            logger.warning("[Chat AI] Response is a string, wrapping in message dict")
            data = {"message": data}

        # リスト形式で返ってきた場合の対応（一部のモデルの挙動）
        elif isinstance(data, list):
            logger.warning("[Chat AI] Response is a list, extracting first element")
            if data and isinstance(data[0], dict):
                data = data[0]
            else:
                data = {}

        if not data:
            data = {"message": "AIから有効な応答が得られませんでした。"}

    except json.JSONDecodeError:
        logger.warning(
            "[Chat AI] JSON decode failed, attempting recovery from: %s",
            json_resp[:200],
        )
        data = None

        # リカバリ1: 余計な接頭辞/接尾辞がある場合に {} の間を抽出して再試行
        start = json_resp.find("{")
        end = json_resp.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(json_resp[start:end])
                logger.info("[Chat AI] Recovered via brace extraction: %s", data)
                data["_json_recovered"] = True
            except Exception:
                pass

        # リカバリ2: 中括弧なしのJSON断片（例: "message": "..."）を {} で囲んで再試行
        if data is None:
            try:
                data = json.loads("{" + json_resp.strip() + "}")
                logger.info("[Chat AI] Recovered via brace wrapping: %s", data)
                data["_json_recovered"] = True
            except Exception as e:
                logger.error("[Chat AI] All recovery attempts failed: %s", e, exc_info=True)
                data = {
                    "message": "AIの応答を解析できませんでした。",
                    "raw_response": json_resp,
                }

    # フロントエンド向けのメッセージフィールド保証
    if "message" not in data or not data["message"]:
        logger.warning("[Chat AI] Message missing or empty, generating fallback")

        # プロパティが直接返された場合のフォールバックメッセージ生成
        has_properties = any(key in data for key in ["Title", "Content", "properties"])

        if has_properties:
            title_val = data.get(
                "Title", (data.get("properties") or {}).get("Title", "")
            )
            data["message"] = (
                f"内容を整理しました: {title_val}"
                if title_val
                else "プロパティを抽出しました。"
            )
        else:
            data["message"] = "（応答完了）"
        logger.info("[Chat AI] Fallback message: %s", data["message"])

    # データの正規化: AIがプロパティをトップレベルキーとして返した場合の修正
    if "properties" not in data:
        schema_keys = set(schema.keys())
        data_keys = set(data.keys())
        # メッセージ等以外のキーで、スキーマと一致するものをプロパティとみなす
        property_keys = data_keys.intersection(schema_keys)

        if property_keys:
            logger.info("[Chat AI] Normalizing direct properties: %s", property_keys)
            properties = {key: data[key] for key in property_keys}
            # トップレベルから削除して properties キー配下に移動
            for key in property_keys:
                del data[key]
            data["properties"] = properties

    # プロパティの詳細検証
    if "properties" in data and data["properties"]:
        data["properties"] = validate_and_fix_json(
            json.dumps(data["properties"]), schema
        )

    # メタデータの付与
    data["usage"] = result["usage"]
    data["cost"] = result["cost"]
    data["model"] = result["model"]

    # モデル選択の透明性情報を追加
    data["model_selection"] = {
        "requested": requested_model,
        "used": selected_model,
        "fallback_occurred": model_fallback_occurred,
    }

    # Thinkingコンテンツ（デバッグ用）
    # ユーザーには表示しないが、デバッグパネルで確認可能
    if result.get("thinking"):
        data["thinking"] = result["thinking"]

    return data
