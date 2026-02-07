"""
Test script to inspect Gemini image generation response structure
"""

import asyncio
import json
from litellm import acompletion
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def test_gemini_image_gen():
    # Ensure API key is set
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set")
        return

    print("Testing Gemini image generation...")

    try:
        response = await acompletion(
            model="gemini/gemini-2.5-flash-image",
            messages=[{"role": "user", "content": "a cute cat"}],
            modalities=["image", "text"],
            timeout=30,
            drop_params=True,
        )

        print("\n=== Response type:", type(response))
        print("\n=== Response attributes:")
        print([attr for attr in dir(response) if not attr.startswith("_")])

        print("\n=== response.choices[0]:")
        choice = response.choices[0]
        print("Type:", type(choice))
        print("Attributes:", [attr for attr in dir(choice) if not attr.startswith("_")])

        print("\n=== response.choices[0].message:")
        message = choice.message
        print("Type:", type(message))
        print(
            "Attributes:", [attr for attr in dir(message) if not attr.startswith("_")]
        )
        print(
            "Content:", message.content if hasattr(message, "content") else "No content"
        )

        # Check for hidden attributes
        print("\n=== Checking for hidden/private attributes:")
        if hasattr(response, "_hidden_params"):
            print(
                "_hidden_params:",
                response._hidden_params.keys()
                if isinstance(response._hidden_params, dict)
                else response._hidden_params,
            )

        if hasattr(response, "model_extra"):
            print("model_extra:", response.model_extra)

        if hasattr(choice, "_raw_response"):
            print("choice._raw_response:", choice._raw_response)

        # Try to convert to dict
        print("\n=== Response as dict:")
        try:
            response_dict = (
                response.model_dump()
                if hasattr(response, "model_dump")
                else dict(response)
            )
            print(json.dumps(response_dict, indent=2, default=str)[:1000])
        except Exception as e:
            print(f"Could not convert to dict: {e}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_gemini_image_gen())
