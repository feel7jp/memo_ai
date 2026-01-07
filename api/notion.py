import os
import asyncio
import httpx
from typing import Dict, List, Optional, Any

# Notion API Configuration
NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"

async def safe_api_call(
    method, 
    endpoint, 
    ignore_errors: Optional[List[int]] = None, 
    max_retries: int = 3, 
    timeout: float = 30.0,
    **kwargs
):
    """
    Robust API wrapper with exponential backoff retry.
    """
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        raise ValueError("NOTION_API_KEY is not set")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    
    url = f"{BASE_URL}/{endpoint}"
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                await asyncio.sleep(0.35)  # Rate limit prevention
                
                response = await client.request(method, url, headers=headers, **kwargs)
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 2))
                    print(f"Rate limited, waiting {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue
                
                # Check ignored errors
                if ignore_errors and response.status_code in ignore_errors:
                    return None
                
                response.raise_for_status()
                return response.json()
                
        except httpx.ReadTimeout:
            if attempt < max_retries - 1:
                backoff = 2 ** attempt  # Exponential: 1s, 2s, 4s
                print(f"Timeout on {endpoint}, retry {attempt + 1}/{max_retries} after {backoff}s")
                await asyncio.sleep(backoff)
            else:
                print(f"Final timeout on {endpoint} after {max_retries} attempts")
                raise
                
        except httpx.NetworkError as e:
            if attempt < max_retries - 1:
                backoff = 2 ** attempt
                print(f"Network error on {endpoint}, retry {attempt + 1}/{max_retries} after {backoff}s")
                await asyncio.sleep(backoff)
            else:
                print(f"Network error on {endpoint} after {max_retries} attempts: {e}")
                raise
                
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            print(f"HTTP {status} on {method} {endpoint}")
            if status >= 500 and attempt < max_retries - 1:
                # Retry server errors
                backoff = 2 ** attempt
                print(f"Server error, retry {attempt + 1}/{max_retries} after {backoff}s")
                await asyncio.sleep(backoff)
            else:
                raise
                
        except Exception as e:
            print(f"Unexpected error on {endpoint}: {type(e).__name__} - {e}")
            import traceback
            traceback.print_exc()
            raise
    
    return None

async def get_page_info(page_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches details of a specific page.
    """
    return await safe_api_call("GET", f"pages/{page_id}")
            
async def fetch_config_db(config_db_id: str) -> List[Dict[str, str]]:
    """
    Fetches configuration from the Notion Config Database.
    """
    # Use POST /databases/{id}/query
    response = await safe_api_call("POST", f"databases/{config_db_id}/query")
    if not response:
        return []
        
    configs = []
    for page in response.get("results", []):
        try:
            props = page["properties"]
            # Extract plain text from various types robustly
            def get_text(p):
                if not p: return ""
                t_type = p.get("type")
                if t_type == "title" and p.get("title"):
                    return p["title"][0].get("plain_text", "")
                if t_type == "rich_text" and p.get("rich_text"):
                    return p["rich_text"][0].get("plain_text", "")
                return ""

            name = get_text(props.get("Name"))
            target_id = get_text(props.get("TargetDB_ID"))
            prompt = get_text(props.get("SystemPrompt"))
            
            if not name: continue # Drop invalid entries
            
            configs.append({
                "name": name,
                "target_db_id": target_id.strip(),
                "system_prompt": prompt
            })
        except (KeyError, IndexError):
            continue
    return configs

async def get_db_schema(target_db_id: str) -> Dict[str, Any]:
    """
    Fetches the schema (properties) of the target database.
    """
    # Use GET /databases/{id}
    # Ignore 400 because if it's a Page ID, Notion returns 400.
    response = await safe_api_call("GET", f"databases/{target_db_id}", ignore_errors=[400])
    if response is None:
        raise ValueError("Not a database")
    
    return response.get("properties", {})

async def fetch_recent_pages(target_db_id: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Fetches recent pages from the target database for Few-shot examples.
    """
    # Use POST /databases/{id}/query
    body = {
        "page_size": limit,
        "sorts": [{"timestamp": "created_time", "direction": "descending"}]
    }
    response = await safe_api_call("POST", f"databases/{target_db_id}/query", json=body)
    if not response:
        return []
    
    results = []
    for page in response.get("results", []):
        results.append(page.get("properties", {}))
    return results

async def create_page(target_db_id: str, properties: Dict[str, Any]) -> str:
    """
    Creates a new page in the target database.
    """
    body = {
        "parent": {"database_id": target_db_id},
        "properties": properties
    }
    # Use POST /pages
    response = await safe_api_call("POST", "pages", json=body)
    if response and "url" in response:
        return response["url"]
    
    raise Exception("Failed to create page")

    return None

async def search_child_database(parent_page_id: str, title_query: str) -> Optional[Dict[str, Any]]:
    """
    Searches for a database with a specific title under a parent page.
    Uses fetch_children_list.
    """
    children = await fetch_children_list(parent_page_id)
    
    for block in children:
        if block.get("type") == "child_database":
            db_info = block.get("child_database", {})
            title = db_info.get("title", "")
            
            if title == title_query:
                db_id = block["id"]
                return await safe_api_call("GET", f"databases/{db_id}")
    return None

async def fetch_children_list(parent_page_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetches the children blocks of a page/block.
    Useful for discovering Pages and Databases under the Root Page.
    """
    response = await safe_api_call("GET", f"blocks/{parent_page_id}/children?page_size={limit}")
    if not response:
        return []
    results = response.get("results", [])
    # Filter out archived (deleted) blocks
    return [b for b in results if not b.get("archived")]

async def create_database(parent_page_id: str, title: str, properties: Dict[str, Any]) -> str:
    """
    Creates a new database under the specified parent page.
    """
    body = {
        "parent": {
            "type": "page_id",
            "page_id": parent_page_id
        },
        "title": [
            {
                "type": "text",
                "text": {
                    "content": title,
                    "link": None
                }
            }
        ],
        "properties": properties
    }
    
    response = await safe_api_call("POST", "databases", json=body)
    if response and "id" in response:
        return response["id"]
        
    raise Exception(f"Failed to create database '{title}'")

async def append_block(page_id: str, content: str) -> bool:
    """
    Appends a paragraph block to a page.
    Handles text > 2000 characters by chunking.
    """
    MAX_CHARS = 2000
    
    # Chunk the content
    chunks = [content[i:i+MAX_CHARS] for i in range(0, len(content), MAX_CHARS)]
    
    children = []
    for chunk in chunks:
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}]
            }
        })
    
    # Notion API allows up to 100 blocks in one request.
    # If we somehow have massive content (>200k chars), we might need batching logic here too.
    # But for now, just sending 'children' list is likely fine for normal AI responses.
    
    # We can batch by 100 blocks just to be safe
    BATCH_SIZE = 100
    success = True
    
    for i in range(0, len(children), BATCH_SIZE):
        batch = children[i:i+BATCH_SIZE]
        response = await safe_api_call("PATCH", f"blocks/{page_id}/children", json={"children": batch})
        if not response:
            success = False
            
    return success

async def query_database(database_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Queries a database for its entries.
    """
    body = {
        "page_size": limit,
        "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}]
    }
    response = await safe_api_call("POST", f"databases/{database_id}/query", json=body, timeout=60.0)
    if not response:
        return []
    return response.get("results", [])
