"""
Test the fixed image generation function
"""

import asyncio
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, ".")

from api.llm_client import generate_image_response


async def test_image_gen():
    print("Testing Gemini image generation fix...")

    try:
        result = await generate_image_response(
            prompt="A cute pixel art cat", model="gemini/gemini-2.5-flash-image"
        )

        print("✅ Success!")
        print(f"  Message: {result['message'][:100] if result['message'] else 'None'}")
        print(
            f"  Image base64 length: {len(result['image_base64']) if result.get('image_base64') else 0}"
        )
        print(f"  Model: {result['model']}")
        print(f"  Cost: ${result['cost']:.4f}")

        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_image_gen())
    sys.exit(0 if success else 1)
