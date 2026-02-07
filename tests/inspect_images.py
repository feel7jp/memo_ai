"""
Simple script to inspect message.images structure
"""

import asyncio
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, ".")

from litellm import acompletion


async def inspect_response():
    print("Calling Gemini image generation...")

    response = await acompletion(
        model="gemini/gemini-2.5-flash-image",
        messages=[{"role": "user", "content": "A cute pixel art cat"}],
        modalities=["image", "text"],
        timeout=60,
        drop_params=True,
    )

    message = response.choices[0].message

    print(f"\nmessage.content = {message.content}")
    print(f"hasattr(message, 'images') = {hasattr(message, 'images')}")

    if hasattr(message, "images"):
        print(f"len(message.images) = {len(message.images)}")
        print(f"type(message.images) = {type(message.images)}")

        if len(message.images) > 0:
            img = message.images[0]
            print(f"\ntype(img) = {type(img)}")
            print(f"hasattr(img, 'image_url') = {hasattr(img, 'image_url')}")

            if hasattr(img, "image_url"):
                print(f"type(img.image_url) = {type(img.image_url)}")

                if isinstance(img.image_url, dict):
                    print(f"img.image_url.keys() = {img.image_url.keys()}")
                    url = img.image_url.get("url", "")
                else:
                    print(
                        f"hasattr(img.image_url, 'url') = {hasattr(img.image_url, 'url')}"
                    )
                    if hasattr(img.image_url, "url"):
                        url = img.image_url.url
                    else:
                        url = str(img.image_url)

                print(f"\nurl[:100] = {url[:100]}")
                print(f"'base64,' in url = {'base64,' in url}")

                if "base64," in url:
                    base64_data = url.split("base64,", 1)[1]
                    print(f"len(base64_data) = {len(base64_data)}")
                    print(f"base64_data[:50] = {base64_data[:50]}")


if __name__ == "__main__":
    asyncio.run(inspect_response())
