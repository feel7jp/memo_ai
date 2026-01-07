import os
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import json
from pathlib import Path
from dotenv import load_dotenv

from contextlib import asynccontextmanager
import httpx
from api.notion import fetch_config_db, get_db_schema, fetch_recent_pages, create_page, fetch_children_list, get_page_info, safe_api_call, append_block
from api.ai import analyze_text_with_ai, chat_analyze_text_with_ai
from api.models import get_available_models, get_text_models, get_vision_models
from api.config import DEFAULT_TEXT_MODEL, DEFAULT_MULTIMODAL_MODEL


load_dotenv()

# Global state
APP_CONFIG = {"config_db_id": None}

@asynccontextmanager
async def lifespan(app: FastAPI):
    import socket
    try:
        # Get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        print(f"\n📱 Mobile Access: http://{local_ip}:8000\n")
    except Exception:
        print("\nCould not determine local IP for mobile access.\n")

    if not os.environ.get("NOTION_ROOT_PAGE_ID"):
        print("WARNING: NOTION_ROOT_PAGE_ID not set.")
    
    yield
    # Shutdown

app = FastAPI(lifespan=lifespan)

# Allow CORS for local testing and Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helper Functions ---

def sanitize_image_data(text: str) -> str:
    """
    Remove base64 image data from text content.
    Removes Markdown images, HTML img tags, and image markers.
    """
    import re
    # Remove Markdown images with data URIs: ![...](data:image/...)
    text = re.sub(r'!\[.*?\]\(data:image\/.*?\)', '', text, flags=re.DOTALL)
    # Remove HTML img tags with data URIs: <img src="data:image/..." ...>
    text = re.sub(r'<img[^>]+src=["\']data:image\/[^"\']+["\'][^>]*>', '', text, flags=re.DOTALL)
    # Remove image markers
    text = text.replace("[画像送信]", "").strip()
    return text

# --- Pydantic Models ---
class AnalyzeRequest(BaseModel):
    text: str
    target_db_id: str
    system_prompt: str
    model: Optional[str] = None

class SaveRequest(BaseModel):
    target_db_id: str
    target_type: Optional[str] = "database" # 'database' or 'page'
    properties: Dict[str, Any]
    text: Optional[str] = None # For Page Append

class ChatRequest(BaseModel):
    text: Optional[str] = ""  # Allow empty text for image-only uploads
    target_id: str
    system_prompt: Optional[str] = None
    session_history: Optional[List[Dict[str, str]]] = None
    reference_context: Optional[str] = None
    image_data: Optional[str] = None # Base64 encoded
    image_mime_type: Optional[str] = None
    model: Optional[str] = None

# --- Endpoints ---

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/config")
async def get_config():
    """
    Returns the list of apps from the Notion Config DB.
    """
    config_db_id = APP_CONFIG["config_db_id"] or os.environ.get("NOTION_CONFIG_DB_ID")
    
    if not config_db_id:
        # Fallback for when setup failed or env not set
        # If we really want to be strict, we raise 500.
        # But per previous logic, let's keep the Demo logic ONLY if connection failed?
        # Actually, user wants "If empty, create data". Ensure setup does that.
        # So if we are here and have no ID, it's a critical error (unless we default to empty).
        raise HTTPException(status_code=500, detail="Configuration Database ID not found (Setup failed?)")
    
    configs = await fetch_config_db(config_db_id)
    return {"configs": configs}

@app.get("/api/models")
async def get_models():
    """
    Returns the list of available AI models.
    Categorized by capability (text-only vs vision-capable).
    """
    try:
        all_models = get_available_models()
        text_only = get_text_models()
        vision_capable = get_vision_models()
        
        return {
            "all": all_models,
            "text_only": text_only,
            "vision_capable": vision_capable,
            "defaults": {
                "text": DEFAULT_TEXT_MODEL,
                "multimodal": DEFAULT_MULTIMODAL_MODEL
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/targets")
async def get_targets():
    """
    Returns the list of Pages and Databases under the Root Page.
    """
    root_id = os.environ.get("NOTION_ROOT_PAGE_ID")
    if not root_id:
        raise HTTPException(status_code=500, detail="NOTION_ROOT_PAGE_ID not set")
    
    children = await fetch_children_list(root_id)
    targets = []
    
    # We might need to fetch details for linked items in parallel for speed
    tasks = []

    async def process_block(block):
        b_type = block.get("type")
        
        if b_type == "child_database":
            info = block.get("child_database", {})
            return {
                "id": block["id"],
                "type": "database",
                "title": info.get("title", "Untitled Database")
            }
        elif b_type == "child_page":
            info = block.get("child_page", {})
            return {
                "id": block["id"],
                "type": "page",
                "title": info.get("title", "Untitled Page")
            }
        elif b_type == "link_to_page":
            info = block.get("link_to_page", {})
            target_type = info.get("type")
            target_id = info.get(target_type)
            
            # Resolve details
            if target_type == "page_id":
                page = await get_page_info(target_id)
                if page:
                    # Title logic for page
                    props = page.get("properties", {})
                    title_plain = "Untitled Linked Page"
                    # Usually "title" property has key "title" or "Name"
                    for k, v in props.items():
                        if v["type"] == "title" and v["title"]:
                            title_plain = v["title"][0]["plain_text"]
                            break
                    return {
                        "id": target_id,
                        "type": "page",
                        "title": title_plain + " (Link)"
                    }
            elif target_type == "database_id":
                # Fetch DB details
                db = await safe_api_call("GET", f"databases/{target_id}")
                if db:
                    title_obj = db.get("title", [])
                    title_plain = title_obj[0]["plain_text"] if title_obj else "Untitled Linked DB"
                    return {
                        "id": target_id,
                        "type": "database",
                        "title": title_plain + " (Link)"
                    }
        return None

    results = await asyncio.gather(*[process_block(block) for block in children])
    targets = [res for res in results if res]
            
    return {"targets": targets}

@app.get("/api/schema/{target_id}")
async def get_schema(target_id: str):
    """
    Returns the schema of a target (Page or Database).
    Enhanced with detailed error reporting.
    """
    db_error = None
    page_error = None
    
    # Try to fetch as Database first
    try:
        db = await get_db_schema(target_id)
        return {
            "type": "database",
            "schema": db
        }
    except ValueError as e:
        # Expected if it's a page (400 Bad Request matches "Not a database")
        db_error = str(e)
    except Exception as e:
        db_error = str(e)
        print(f"[Schema Fetch] Database fetch error: {e}")
    
    # Try as Page
    try:
        page = await get_page_info(target_id)
        if page:
            # Fallback for Page
            return {
                "type": "page",
                "schema": {
                    "Title": {"type": "title"},
                    "Content": {"type": "rich_text"}
                }
            }
        else:
            # Page API returned None
            page_error = f"Target {target_id} not found as Page (returned None)"
    except Exception as e:
        page_error = str(e)
        print(f"[Schema Fetch] Page fetch error: {e}")
    
    # If we reach here, both attempts failed
    print(f"[Schema Fetch] Both database and page fetch failed for {target_id}")
    raise HTTPException(
        status_code=404,
        detail={
            "error": "Schema fetch failed",
            "target_id": target_id,
            "attempted": ["database", "page"],
            "database_error": db_error or "Unknown",
            "page_error": page_error or "Unknown",
            "suggestions": [
                "Notion APIキーの権限を確認してください",
                "ターゲットIDが正しいか確認してください",
                "Notionでこのページ/DBが削除されていないか確認してください"
            ]
        }
    )


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest):
    """
    Analyze text using Gemini with context from Notion.
    """
    target_db_id = request.target_db_id
    
    # 1. Fetch Schema and Recent Examples in parallel
    # This addresses the 10s Vercel timeout constraint
    try:
        results = await asyncio.gather(
            get_db_schema(target_db_id),
            fetch_recent_pages(target_db_id, limit=3),
            return_exceptions=True
        )
        
        schema = results[0]
        recent_examples = results[1]
        
        # Handle errors gracefully
        if isinstance(schema, Exception):
            print(f"Error fetching schema: {schema}")
            schema = {} # Fallback? Maybe we should error. AI handles empty schema gracefully (just makes title).
        if isinstance(recent_examples, Exception):
            print(f"Error fetching recent examples: {recent_examples}")
            recent_examples = []
            
    except Exception as e:
        print(f"Parallel fetch failed: {e}")
        schema = {}
        recent_examples = []

    # 2. SystemPrompt
    # Frontend now handles SystemPrompt storage and passes it.
    system_prompt = request.system_prompt
    if not system_prompt:
        system_prompt = "You are a helpful assistant." # Fallback just in case

    # 3. Call AI
    try:
        # Call updated function
        result = await analyze_text_with_ai(
            text=request.text,
            schema=schema,
            recent_examples=recent_examples,
            system_prompt=system_prompt,
            model=request.model
        )
        # Return full result including usage/cost
        return result
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail={
                "error": "Notion API Timeout",
                "message": "Notion APIの応答がタイムアウトしました。しばらく待ってから再試行してください。",
                "suggestions": ["Notionのステータスを確認してください", "しばらく待ってから再試行してください"]
            }
        )
    except Exception as e:
        print(f"[AI Analysis Error] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "AI analysis failed",
                "message": str(e),
                "type": type(e).__name__,
                "suggestions": [
                    "GEMINI_API_KEYが正しく設定されているか確認してください",
                    "Gemini APIの利用制限に達していないか確認してください",
                    "入力テキストが長すぎないか確認してください"
                ]
            }
        )

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Interactive Chat AI endpoint.
    Enhanced with detailed error reporting.
    """
    print(f"[Chat] Request received for target: {request.target_id}")
    print(f"[Chat] Has image: {bool(request.image_data)}")
    print(f"[Chat] Text length: {len(request.text) if request.text else 0}")
    
    try:
        target_id = request.target_id
        
        # Fetch schema and config
        print(f"[Chat] Fetching schema for target: {target_id}")
        try:
            schema_result = await get_schema(target_id)
            schema = schema_result.get("schema", {})
            target_type = schema_result.get("type", "database")
            print(f"[Chat] Schema fetched, type: {target_type}, properties: {len(schema)}")
        except Exception as schema_error:
            print(f"[Chat] Schema fetch error: {schema_error}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Schema fetch failed",
                    "message": str(schema_error),
                    "suggestions": [
                        "ターゲットIDが正しいか確認してください",
                        "Notion APIキーの権限を確認してください"
                    ]
                }
            )
        
        # SystemPrompt
        # Frontend provided.
        system_prompt = request.system_prompt
        if not system_prompt:
             # Basic default if missing
             system_prompt = """優秀な秘書として、ユーザーのタスクを明確にする手伝いをすること。
明確な実行できる タスク名に言い換えて。先頭に的確な絵文字を追加して
画像の場合は、そこから何をしようとしているのか推定して、タスクにして。"""
        
        # 参考情報を会話履歴の先頭に追加
        session_history = request.session_history or []
        if request.reference_context:
            # 先頭にシステムメッセージとして追加
            session_history = [
                {"role": "system", "content": request.reference_context}
            ] + session_history
        
        # Call Chat AI
        print(f"[Chat] Calling AI with model: {request.model or 'auto'}")
        try:
            result = await chat_analyze_text_with_ai(
                text=request.text,
                schema=schema,
                system_prompt=system_prompt,
                session_history=session_history,
                image_data=request.image_data,
                image_mime_type=request.image_mime_type,
                model=request.model
            )
            print(f"[Chat] AI response received, model used: {result.get('model')}")
            return result
        except httpx.ReadTimeout:
            raise HTTPException(
                status_code=504,
                detail={
                    "error": "Notion API Timeout",
                    "message": "Notion APIの応答がタイムアウトしました。",
                    "type": "ReadTimeout"
                }
            )
        except Exception as ai_error:
            print(f"[Chat AI Error] {type(ai_error).__name__}: {ai_error}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Chat AI failed",
                    "message": str(ai_error),
                    "type": type(ai_error).__name__,
                    "suggestions": [
                        "GEMINI_API_KEYが正しく設定されているか確認してください",
                        "Gemini APIの利用制限に達していないか確認してください"
                    ]
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Chat Endpoint Error] {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Unexpected error",
                "message": str(e),
                "type": type(e).__name__
            }
        )

@app.post("/api/save")
async def save(request: SaveRequest):
    """
    Save the approved properties to Notion.
    """
    try:
        if request.target_type == "page":
            # Append text block
            content = request.text or "No content"
            # If properties has Content, prefer that (from Form)
            if "Content" in request.properties:
                 # Flatten rich_text structure
                 c_obj = request.properties["Content"]
                 if "rich_text" in c_obj:
                     content = c_obj["rich_text"][0]["text"]["content"]
            
            # --- Sanitization ---
            content = sanitize_image_data(content)

            # 5. Handle excessively long text gracefully
            # Although append_block chunks logic handles splitting, 
            # we want to avoid processing inadvertent huge pastes (e.g. 100k+ chars garbage).
            # User said "5000+ is NOT an error", so we should process it, but maybe warn or just proceed.
            # We will rely on append_block's chunking, but let's log if it's huge.
            if len(content) > 100000:
                print(f"[Save] Warning: Extremely large content ({len(content)} chars). Truncating to 100k.")
                content = content[:100000] + "\n...(Truncated)..."

            success = await append_block(request.target_db_id, content)
            if not success:
               pass # append_block usually returns True or False, or raises.
               # If it returned False (e.g. partial failure), we might want to warn but not 500.
            
            return {"status": "success", "url": ""} # URL unknown for block
        else:
            # Create DB Page
            # Need to sanitize properties too if they contain rich_text with images
            sanitized_props = request.properties.copy()
            
            def sanitize_val(val):
                if isinstance(val, str):
                    return sanitize_image_data(val)
                return val

            # Deep sanitize specific rich_text fields and handle 2000 char limit
            for key, val in sanitized_props.items():
                if isinstance(val, dict):
                    # Handle rich_text
                    if "rich_text" in val and val["rich_text"]:
                        new_rich_text = []
                        for item in val["rich_text"]:
                            if "text" in item:
                                content = sanitize_val(item["text"]["content"])
                                # Split into 2000-char chunks
                                if len(content) > 2000:
                                    for i in range(0, len(content), 2000):
                                        new_item = item.copy()
                                        new_item["text"] = item["text"].copy()
                                        new_item["text"]["content"] = content[i:i+2000]
                                        new_rich_text.append(new_item)
                                else:
                                    item["text"]["content"] = content
                                    new_rich_text.append(item)
                            else:
                                new_rich_text.append(item)
                        val["rich_text"] = new_rich_text
                    
                    # Handle title (similar logic, usually title is shorter but safe to handle)
                    if "title" in val and val["title"]:
                        new_title = []
                        for item in val["title"]:
                            if "text" in item:
                                content = sanitize_val(item["text"]["content"])
                                # Split into 2000-char chunks
                                if len(content) > 2000:
                                    for i in range(0, len(content), 2000):
                                        new_item = item.copy()
                                        new_item["text"] = item["text"].copy()
                                        new_item["text"]["content"] = content[i:i+2000]
                                        new_title.append(new_item)
                                else:
                                    item["text"]["content"] = content
                                    new_title.append(item)
                            else:
                                new_title.append(item)
                        val["title"] = new_title

            url = await create_page(request.target_db_id, sanitized_props)
            return {"status": "success", "url": url}
    except Exception as e:
        print(f"[Save Error] {e}")
        # Even if it fails, we shouldn't crash client if possible, but 500 is appropriate for actual failure.
        # But user said "don't treat 5000+ string as error". 
        # By sanitizing above, we avoid the main cause of "long string error" (base64).
        # If it is just text, append_block handles it.
        raise HTTPException(status_code=500, detail=f"Failed to save to Notion: {str(e)}")


@app.post("/api/pages/create")
async def create_new_page(request: dict):
    """
    Create a new page under the root page.
    """
    try:
        page_name = request.get("page_name", "").strip()
        
        if not page_name:
            raise HTTPException(status_code=400, detail="ページ名が必要です")
        
        root_id = os.environ.get("NOTION_ROOT_PAGE_ID")
        if not root_id:
            raise HTTPException(status_code=500, detail="NOTION_ROOT_PAGE_ID not set")
        
        # Create new page using Notion API
        from .notion import safe_api_call
        
        new_page = await safe_api_call("POST", "pages", json={
            "parent": {"type": "page_id", "page_id": root_id},
            "properties": {
                "title": {
                    "title": [{"text": {"content": page_name}}]
                }
            }
        })
        
        if not new_page:
            raise Exception("Failed to create page")
        
        return {
            "id": new_page["id"],
            "title": page_name,
            "type": "page"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Create Page Error] {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"ページ作成に失敗しました: {str(e)}")


# --- Content Preview ---

@app.get("/api/content/page/{page_id}")
async def get_page_content(page_id: str):
    """
    Fetches blocks of a page and returns them in a simplified format.
    """
    from .notion import fetch_children_list
    
    try:
        results = await fetch_children_list(page_id)
        blocks = []
        
        for block in results:
            b_type = block.get("type")
            content = ""
            
            # Extract plain text based on block type
            if b_type in block:
                info = block[b_type]
                if "rich_text" in info:
                    content = "".join([t.get("plain_text", "") for t in info["rich_text"]])
                elif b_type == "child_page":
                    content = info.get("title", "")
                elif b_type == "child_database":
                    content = info.get("title", "")
            
            blocks.append({
                "type": b_type,
                "content": content
            })
            
        return {"type": "page", "blocks": blocks}
    except Exception as e:
        print(f"[Page Content Error] {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch page content: {str(e)}")

@app.get("/api/content/database/{database_id}")
async def get_database_content(database_id: str):
    """
    Queries a database and returns its entries in a simplified table format.
    """
    from .notion import query_database
    
    try:
        results = await query_database(database_id, limit=15)
        if not results:
            return {"type": "database", "columns": [], "rows": []}
            
        # Get columns from the first result's properties
        # (Alternatively, we could fetch the schema, but results are more direct)
        columns = list(results[0]["properties"].keys())
        
        rows = []
        for entry in results:
            row = {"id": entry["id"]}
            props = entry["properties"]
            
            for col in columns:
                p = props.get(col, {})
                p_type = p.get("type")
                val = ""
                
                # Simplified extraction
                if p_type == "title" and p.get("title"):
                    val = "".join([t.get("plain_text", "") for t in p["title"]])
                elif p_type == "rich_text" and p.get("rich_text"):
                    val = "".join([t.get("plain_text", "") for t in p["rich_text"]])
                elif p_type == "date" and p.get("date"):
                    val = p["date"].get("start", "")
                elif p_type == "select" and p.get("select"):
                    val = p["select"].get("name", "")
                elif p_type == "multi_select" and p.get("multi_select"):
                    val = ", ".join([o.get("name", "") for o in p["multi_select"]])
                elif p_type == "checkbox":
                    val = "✓" if p.get("checkbox") else "☐"
                elif p_type == "number":
                    val = str(p.get("number", ""))
                elif p_type == "people" and p.get("people"):
                    val = ", ".join([u.get("name", "Unknown") for u in p["people"]])
                elif p_type == "status" and p.get("status"):
                    val = p["status"].get("name", "")
                
                row[col] = val
            rows.append(row)
            
        return {
            "type": "database",
            "columns": columns,
            "rows": rows
        }
    except Exception as e:
        print(f"[DB Content Error] {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch database content: {str(e)}")

# Serve static files from the public directory at the root
# We mount this LAST so that any defined routes (like /api/*) take precedence.
app.mount("/", StaticFiles(directory="public", html=True), name="static")
