"""
AI Prompt Construction
Handles prompt building logic for Notion data entry
"""
import json
from typing import Dict, Any, List, Optional

from api.llm_client import generate_json, prepare_multimodal_prompt
from api.models import select_model_for_input


def construct_prompt(
    text: str,
    schema: Dict[str, Any],
    recent_examples: List[Dict[str, Any]],
    system_prompt: str
) -> str:
    """
    Constructs the full prompt for the AI.
    """
    # 1. Schema Info
    # Simplify schema for prompt
    schema_info = {}
    for k, v in schema.items():
        schema_info[k] = v['type']
        if v['type'] == 'select':
            schema_info[k] += f" options: {[o['name'] for o in v['select']['options']]}"
        elif v['type'] == 'multi_select':
            schema_info[k] += f" options: {[o['name'] for o in v['multi_select']['options']]}"
            
    # 2. Examples Info
    examples_text = ""
    if recent_examples:
        for ex in recent_examples:
            props = ex.get("properties", {})
            simple_props = {}
            for k, v in props.items():
                p_type = v.get("type")
                val = "N/A"
                if p_type == "title":
                    val = "".join([t.get("plain_text", "") for t in v.get("title", [])])
                elif p_type == "rich_text":
                    val = "".join([t.get("plain_text", "") for t in v.get("rich_text", [])])
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


def construct_chat_prompt(
    text: str,
    schema: Dict[str, Any],
    system_prompt: str,
    session_history: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Constructs the prompt for the Chat AI.
    """
    schema_info = {}
    target_type = "database"
    
    # Check if schema looks like a DB schema or Page schema
    # DB schema has keys like "Property Name": {"type": "..."}
    # Page schema we defined as {"Title": {"type": "title"}, ...}
    
    for k, v in schema.items():
        if isinstance(v, dict) and "type" in v:
             schema_info[k] = v['type']
             if v['type'] == 'select' and 'select' in v:
                schema_info[k] += f" options: {[o['name'] for o in v['select']['options']]}"
             elif v['type'] == 'multi_select' and 'multi_select' in v:
                schema_info[k] += f" options: {[o['name'] for o in v['multi_select']['options']]}"
    
    # Session History
    history_text = ""
    if session_history:
        for msg in session_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                # Special handling for reference context or system msgs
                 history_text += f"[System Info]: {content}\n"
            else:
                 history_text += f"{role.upper()}: {content}\n"

    prompt = f"""
{system_prompt}

Target Schema:
{json.dumps(schema_info, indent=2, ensure_ascii=False)}

Session History:
{history_text}

Current User Input:
{text if text else "(No text provided)"}

Restraints:
- You are a helpful AI assistant.
- Your output must be valid JSON ONLY.
- Structure:
{{
  "message": "Response to the user",
  "refined_text": "Refined version of the input, if applicable (or null)",
  "properties": {{ "Property Name": "Value" }} // Only if user intends to save data
}}
- If the user is just chatting, "properties" should be null.
- If the user wants to save/add data, fill "properties" according to the Schema.
"""
    return prompt


def validate_and_fix_json(json_str: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses JSON and robustly validates against schema.
    """
    # 1. Clean Markdown
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
        # Simple retry: sometimes it has extra text
        start = json_str.find("{")
        end = json_str.rfind("}") + 1
        if start != -1 and end != -1:
            try:
                data = json.loads(json_str[start:end])
            except Exception:
                # Fatal
                return {}
        else:
             return {}

    # 2. Validate/Cast Properties
    validated = {}
    for k, v in data.items():
        if k not in schema:
            continue
            
        target_type = schema[k]["type"]
        
        # Basic casting
        if target_type == "select":
            # Ensure value is string
            if isinstance(v, dict): v = v.get("name")
            if v:
                validated[k] = {"select": {"name": str(v)}}
                
        elif target_type == "multi_select":
            # Ensure array of strings
            if not isinstance(v, list): v = [v]
            opts = []
            for item in v:
               if isinstance(item, dict): item = item.get("name")
               if item: opts.append({"name": str(item)})
            validated[k] = {"multi_select": opts}
            
        elif target_type == "status":
             if isinstance(v, dict): v = v.get("name")
             if v:
                 validated[k] = {"status": {"name": str(v)}}
                 
        elif target_type == "date":
            # Expect YYYY-MM-DD
            if isinstance(v, dict): v = v.get("start")
            if v:
                validated[k] = {"date": {"start": str(v)}}
                
        elif target_type == "checkbox":
            validated[k] = {"checkbox": bool(v)}
            
        elif target_type == "number":
             try:
                 if v is not None:
                     validated[k] = {"number": float(v)}
             except:
                 pass
                 
        elif target_type == "title":
             if isinstance(v, list): v = "".join([t.get("plain_text","") for t in v if "plain_text" in t])
             validated[k] = {"title": [{"text": {"content": str(v)}}]}
             
        elif target_type == "rich_text":
             if isinstance(v, list): v = "".join([t.get("plain_text","") for t in v if "plain_text" in t])
             validated[k] = {"rich_text": [{"text": {"content": str(v)}}]}
             
        elif target_type == "people":
            # Ignore for now (requires user IDs)
            pass
            
        elif target_type == "files":
             # Ignore
             pass

    return validated


# --- NEW: High-level entry points ---

async def analyze_text_with_ai(
    text: str,
    schema: Dict[str, Any],
    recent_examples: List[Dict[str, Any]],
    system_prompt: str,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyzes text and returns properties with usage/cost information.
    
    Args:
        text: User input text
        schema: Notion database schema
        recent_examples: Recent database entries for context
        system_prompt: System instructions
        model: Optional explicit model selection (overrides auto-selection)
    
    Returns:
        {
            "properties": {...},  # Notion-compatible properties
            "usage": {...},       # Token usage
            "cost": float,        # Estimated cost
            "model": str          # Model used
        }
    """
    # Auto-select model (text-only input)
    selected_model = select_model_for_input(has_image=False, user_selection=model)
    
    # Construct prompt
    prompt = construct_prompt(text, schema, recent_examples, system_prompt)
    
    try:
        # Call LLM
        result = await generate_json(prompt, model=selected_model)
        
        # Validate and clean properties
        properties = validate_and_fix_json(result["content"], schema)
        
        return {
            "properties": properties,
            "usage": result["usage"],
            "cost": result["cost"],
            "model": result["model"]
        }
    
    except Exception as e:
        print(f"AI Analysis Failed: {e}")
        
        # Fallback: Just return title
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
            "error": str(e)
        }


async def chat_analyze_text_with_ai(
    text: str,
    schema: Dict[str, Any],
    system_prompt: str,
    session_history: Optional[List[Dict[str, str]]] = None,
    image_data: Optional[str] = None,
    image_mime_type: Optional[str] = None,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyzes text interactively with optional image input.
    
    Args:
        text: User input text
        schema: Notion database/page schema
        system_prompt: System instructions
        session_history: Previous conversation turns
        image_data: Base64-encoded image (optional)
        image_mime_type: MIME type of image (optional)
        model: Optional explicit model selection
    
    Returns:
        {
            "message": str,
            "refined_text": str,
            "properties": {...},
            "usage": {...},
            "cost": float,
            "model": str
        }
    """
    # Auto-select model based on image presence
    has_image = bool(image_data and image_mime_type)
    print(f"[Chat AI] Has image: {has_image}, User model selection: {model}")
    selected_model = select_model_for_input(has_image=has_image, user_selection=model)
    print(f"[Chat AI] Selected model: {selected_model}")
    
    # Construct prompt
    print(f"[Chat AI] Constructing prompt, schema keys: {len(schema)}, history length: {len(session_history) if session_history else 0}")
    prompt_text = construct_chat_prompt(text or "", schema, system_prompt, session_history)
    
    # Add explicit image indicator if image is present
    if has_image:
        prompt_text += "\n\n[IMPORTANT: The user has attached an image. Please analyze the image content and respond based on what you see in the image.]"
    
    # Prepare multimodal input if image present
    print(f"[Chat AI] Preparing {'multimodal' if has_image else 'text-only'} prompt")
    if has_image:
        prompt = prepare_multimodal_prompt(prompt_text, image_data, image_mime_type)
    else:
        prompt = prompt_text
    
    # Call LLM
    print(f"[Chat AI] Calling LLM: {selected_model}")
    result = await generate_json(prompt, model=selected_model)
    print(f"[Chat AI] LLM response received, length: {len(result['content'])}")
    json_resp = result["content"]
    
    # Parse response
    try:
        data = json.loads(json_resp)
        
        # DEBUG: Log raw parsed data
        print(f"[Chat AI] Raw parsed response type: {type(data)}")
        print(f"[Chat AI] Raw parsed response: {data}")
        
        # Handle list response (some models/prompts might return an array)
        if isinstance(data, list):
            print(f"[Chat AI] Response is a list, extracting first element")
            if data and isinstance(data[0], dict):
                data = data[0]
            else:
                data = {}

        if not data:
            data = {"message": "AIから有効な応答が得られませんでした。"}
            
        # DEBUG: Log after list handling
        print(f"[Chat AI] After list handling: {data}")
        print(f"[Chat AI] Message field: {data.get('message')}")
        
    except json.JSONDecodeError:
        print(f"[Chat AI] JSON decode failed, attempting recovery from: {json_resp[:200]}")
        try:
            start = json_resp.find("{")
            end = json_resp.rfind("}") + 1
            data = json.loads(json_resp[start:end])
            print(f"[Chat AI] Recovered data: {data}")
        except Exception as e:
            print(f"[Chat AI] Recovery failed: {e}")
            data = {
                "message": "AIの応答を解析できませんでした。",
                "raw_response": json_resp
            }
    
    # Ensure message key exists for frontend
    if "message" not in data or not data["message"]:
        print(f"[Chat AI] Message missing or empty, generating fallback")
        
        # Check if data contains properties-like keys (Title, Content, etc.)
        has_properties = any(key in data for key in ["Title", "Content", "properties"])
        
        if "refined_text" in data and data["refined_text"]:
            data["message"] = f"タスク名を「{data['refined_text']}」に提案します。"
        elif has_properties:
            # If AI returned properties directly without 'properties' wrapper
            if "Title" in data or "Content" in data:
                title_val = data.get("Title", "")
                data["message"] = f"内容を整理しました: {title_val}" if title_val else "プロパティを抽出しました。"
            elif "properties" in data and data["properties"]:
                data["message"] = "プロパティを抽出しました。"
            else:
                data["message"] = "プロパティを抽出しました。"
        else:
            data["message"] = "（応答完了）"
        print(f"[Chat AI] Fallback message: {data['message']}")

    
    # Normalize: If AI returned properties directly (Title, Content, etc.) without 'properties' wrapper
    # Move them into a 'properties' key for consistent handling
    if "properties" not in data:
        # Check if data has schema-like keys
        schema_keys = set(schema.keys())
        data_keys = set(data.keys())
        # Find keys that match schema (excluding 'message', 'refined_text', etc.)
        property_keys = data_keys.intersection(schema_keys)
        
        if property_keys:
            print(f"[Chat AI] Normalizing direct properties: {property_keys}")
            # Extract properties into separate dict
            properties = {key: data[key] for key in property_keys}
            # Remove from top level
            for key in property_keys:
                del data[key]
            # Add to properties
            data["properties"] = properties
            print(f"[Chat AI] Normalized properties: {data['properties']}")
    
    # Validate properties
    if "properties" in data and data["properties"]:
        data["properties"] = validate_and_fix_json(
            json.dumps(data["properties"]),
            schema
        )
    
    # Add metadata
    data["usage"] = result["usage"]
    data["cost"] = result["cost"]
    data["model"] = result["model"]
    
    print(f"[Chat AI] Final response data: {data}")
    
    return data

