import asyncio
import os
import httpx
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_ROOT_PAGE_ID = os.environ.get("NOTION_ROOT_PAGE_ID")
BASE_URL = "https://api.notion.com/v1"

VERSIONS_TO_TEST = ["2022-06-28", "2025-09-03"]


async def call_notion(method, endpoint, version, json_body=None):
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": version,
        "Content-Type": "application/json",
    }
    url = f"{BASE_URL}/{endpoint}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method, url, headers=headers, json=json_body
            )
            # print(f"[{version}] {method} {endpoint}: {response.status_code}")
            return response.status_code, response.json()
        except Exception as e:
            return 0, str(e)


async def main():
    if not NOTION_API_KEY or not NOTION_ROOT_PAGE_ID:
        print("❌ NOTION_API_KEY or NOTION_ROOT_PAGE_ID not found in .env")
        return

    print(f"Testing with Root Page ID: {NOTION_ROOT_PAGE_ID}")

    # 1. Find a database from root page children
    print("\n--- Finding a Database ---")
    # We use the OLD version to find the DB, assuming it works
    status, data = await call_notion(
        "GET", f"blocks/{NOTION_ROOT_PAGE_ID}/children", "2022-06-28"
    )

    if status != 200:
        print(f"Failed to fetch children: {status} {data}")
        return

    target_db_id = None
    target_db_title = "Unknown"

    for block in data.get("results", []):
        if block["type"] == "child_database":
            target_db_id = block["id"]
            target_db_title = block["child_database"].get("title", "Untitled")
            break
        elif block["type"] == "child_page":
            pass  # Skip pages

    if not target_db_id:
        print(
            "⚠️ No child database found directly under root page. Cannot test database endpoints."
        )
        # Try to see if there are any other accessible DBs?
        # For this test, if we can't find a DB, we can't fully test breaking changes.
        return

    print(f"Found Database: {target_db_title} ({target_db_id})")

    # 2. Test Get Database (Schema)
    print("\n--- Testing 'Retrieve a database' (get_db_schema) ---")
    results_schema = {}
    for ver in VERSIONS_TO_TEST:
        status, data = await call_notion("GET", f"databases/{target_db_id}", ver)
        results_schema[ver] = (status, data)
        print(f"[{ver}] Status: {status}")
        if status == 200:
            props = data.get("properties", {})
            print(f"    Properties count: {len(props)}")
        else:
            print(f"    Error: {data.get('message')}")

    # 3. Test Query Database
    print("\n--- Testing 'Query a database' (fetch_recent_pages) ---")
    results_query = {}
    body = {"page_size": 1}
    for ver in VERSIONS_TO_TEST:
        status, data = await call_notion(
            "POST", f"databases/{target_db_id}/query", ver, json_body=body
        )
        results_query[ver] = (status, data)
        print(f"[{ver}] Status: {status}")
        if status == 200:
            results = data.get("results", [])
            print(f"    Results count: {len(results)}")
            if results:
                # Check structure of the first result
                first_res = results[0]
                print(f"    Result keys: {list(first_res.keys())}")
        else:
            print(f"    Error: {data.get('message')}")

    # 4. Check Valid Versions (Trick)
    print("\n--- Checking Valid Versions ---")
    status, data = await call_notion(
        "GET", f"users/me", "2099-01-01"
    )  # Invalid version
    print(f"[2099-01-01] Status: {status}")
    if status == 400:
        print(f"    Error: {data.get('message')}")

    # 5. Compare
    print("\n--- Comparison ---")
    if (
        results_schema["2022-06-28"][0] == 200
        and results_schema["2025-09-03"][0] == 200
    ):
        print("✅ retrieve_database works on both.")
    else:
        print("❌ retrieve_database failed on one or both.")

    if results_query["2022-06-28"][0] == 200 and results_query["2025-09-03"][0] == 200:
        print("✅ query_database works on both.")
    else:
        print("❌ query_database failed on one or both.")


if __name__ == "__main__":
    asyncio.run(main())
