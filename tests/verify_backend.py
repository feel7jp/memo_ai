import asyncio
import os
from dotenv import load_dotenv
from api.index import get_config, analyze
from api.index import AnalyzeRequest

# Load env
load_dotenv()

async def verify():
    print("--- 1. Verifying Environment ---")
    if not os.environ.get("NOTION_API_KEY"):
        print("FAIL: NOTION_API_KEY missing")
        return
    print("OK: Env vars detected")

    print("\n--- 2. Verifying /api/config ---")
    try:
        config_res = await get_config()
        print(f"OK: Config fetched: {len(config_res['configs'])} apps found")
        if len(config_res['configs']) > 0:
            app_config = config_res['configs'][0]
            print(f"    Target App: {app_config['name']}")
        else:
            print("WARN: No apps found in config DB")
            return
    except Exception as e:
        print(f"FAIL: /api/config error: {e}")
        return

    print("\n--- 3. Verifying /api/analyze (Dry Run) ---")
    # We will try to analyze a simple text
    try:
        req = AnalyzeRequest(
            text="テスト: 明日の10時に会議",
            target_db_id=app_config['target_db_id'],
            system_prompt=app_config['system_prompt']
        )
        # Note: This calls Gemini and Notion.
        res = await analyze(req)
        print("OK: Analysis successful")
        print("    Properties generated:")
        for k, v in res["properties"].items():
            print(f"    - {k}: {v}")
            
    except Exception as e:
        print(f"FAIL: /api/analyze error: {e}")

if __name__ == "__main__":
    asyncio.run(verify())
