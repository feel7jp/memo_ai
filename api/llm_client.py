"""
LLM Client
Handles communication with AI providers via LiteLLM
"""
import json
import asyncio
from typing import Dict, Any, Optional
from litellm import acompletion, completion_cost
import litellm

from api.config import LITELLM_VERBOSE, LITELLM_TIMEOUT, LITELLM_MAX_RETRIES

# Configure LiteLLM
litellm.set_verbose = LITELLM_VERBOSE


async def generate_json(
    prompt: Any,
    model: str,
    retries: int = None
) -> Dict[str, Any]:
    """
    Calls LiteLLM to generate JSON responses.
    
    Args:
        prompt: Text prompt or multimodal content list
        model: Model ID to use (e.g., "gemini/gemini-2.5-flash")
        retries: Number of retries on failure (default: from config)
    
    Returns:
        {
            "content": str,      # JSON response content
            "usage": {...},      # Token usage stats
            "cost": float,       # Estimated cost in USD
            "model": str         # Model used
        }
    
    Raises:
        RuntimeError: If generation fails after all retries
    """
    if retries is None:
        retries = LITELLM_MAX_RETRIES
    
    for attempt in range(retries + 1):
        try:
            # Prepare messages
            if isinstance(prompt, list):
                # Multimodal: list of content parts
                messages = [{"role": "user", "content": prompt}]
            else:
                # Text-only: simple string
                messages = [{"role": "user", "content": prompt}]
            
            # Call LiteLLM
            response = await acompletion(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                timeout=LITELLM_TIMEOUT
            )
            
            # Extract content
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("Empty AI response")
            
            # Extract usage and cost
            usage = response.usage.dict() if hasattr(response, 'usage') else {}
            cost = 0.0
            
            try:
                cost = completion_cost(completion_response=response)
            except Exception as e:
                print(f"Cost calculation failed: {e}")
            
            return {
                "content": content,
                "usage": usage,
                "cost": cost,
                "model": model
            }
            
        except Exception as e:
            if attempt == retries:
                print(f"Generation failed after {retries} retries: {e}")
                raise RuntimeError(f"AI generation failed: {str(e)}")
            
            # Exponential backoff
            await asyncio.sleep(2 * (attempt + 1))


def prepare_multimodal_prompt(text: str, image_data: str, image_mime_type: str) -> list:
    """
    Prepares a multimodal prompt for LiteLLM (OpenAI-compatible format).
    
    Args:
        text: Text prompt
        image_data: Base64-encoded image data
        image_mime_type: MIME type (e.g., "image/jpeg")
    
    Returns:
        List of content parts for multimodal input
    """
    image_url = f"data:{image_mime_type};base64,{image_data}"
    
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": image_url}}
    ]
