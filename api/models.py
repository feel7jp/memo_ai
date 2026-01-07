"""
AI Model Definitions and Selection Logic
Manages model metadata and intelligent model selection
Dynamically fetches available models from LiteLLM
"""
from typing import List, Dict, Any, Optional
import litellm
from api.config import (
    is_provider_available,
    DEFAULT_TEXT_MODEL,
    DEFAULT_MULTIMODAL_MODEL
)

# Cache for model registry
_MODEL_CACHE = None

def _build_model_registry() -> List[Dict[str, Any]]:
    """
    Builds model registry from LiteLLM's model_cost dictionary.
    Automatically detects and separates providers (Gemini API vs Vertex AI).
    """
    registry = []
    
    # Get LiteLLM's model cost map
    model_cost_map = litellm.model_cost
    
    # Provider display name mapping
    # Maps LiteLLM provider names to human-readable display names
    PROVIDER_DISPLAY_NAMES = {
        "gemini": "Gemini API",
        "vertex_ai": "Vertex AI", 
        "vertex_ai-vision": "Vertex AI",
        "google": "Gemini API",
        "openai": "OpenAI",
        "azure": "Azure OpenAI",
        "anthropic": "Anthropic",
    }
    
    # Iterate through ALL models in LiteLLM's registry
    for model_id, model_info in model_cost_map.items():
        # Get provider from LiteLLM metadata
        litellm_provider = model_info.get("litellm_provider")
        
        # Auto-detect provider from model_id if not in metadata
        if not litellm_provider:
            if model_id.startswith("gemini/"):
                litellm_provider = "gemini"
            elif model_id.startswith("vertex_ai/"):
                litellm_provider = "vertex_ai"
            elif model_id.startswith("openai/") or model_id.startswith("gpt"):
                litellm_provider = "openai"
            elif model_id.startswith("anthropic/") or model_id.startswith("claude"):
                litellm_provider = "anthropic"
            else:
                # Skip unknown providers
                continue
        
        # Only include providers we have display names for
        if litellm_provider not in PROVIDER_DISPLAY_NAMES:
            continue
        
        provider_display = PROVIDER_DISPLAY_NAMES[litellm_provider]
        
        # Determine capabilities from LiteLLM metadata
        supports_vision = model_info.get("supports_vision", False)
        
        # Fallback: Check model name for known vision model patterns
        if not supports_vision:
            vision_patterns = [
                "gpt-4o", "gpt-4-vision",
                "claude-3", "claude-3-5-sonnet",
                "gemini-1.5", "gemini-2.0", "gemini-pro-vision"
            ]
            for pattern in vision_patterns:
                if pattern in model_id.lower():
                    supports_vision = True
                    break
        
        # JSON support (most modern models support this)
        supports_json = model_info.get("supports_response_schema", True)
        
        # Get cost information
        input_cost = model_info.get("input_cost_per_token", 0.0)
        output_cost = model_info.get("output_cost_per_token", 0.0)
        
        # Build registry entry
        entry = {
            "id": model_id,
            "name": model_id.split("/")[-1],  # Extract model name
            "provider": provider_display,  # Human-readable provider name
            "litellm_provider": litellm_provider,  # Actual LiteLLM provider for routing
            "supports_vision": supports_vision,
            "supports_json": supports_json,
            "cost_per_1k_tokens": {
                "input": input_cost * 1000 if input_cost else 0.0,
                "output": output_cost * 1000 if output_cost else 0.0
            }
        }
        
        # Optional: Keep rate limit notes
        if "rate_limit_note" in model_info:
            entry["rate_limit_note"] = model_info["rate_limit_note"]
        
        registry.append(entry)
    
    # Sort by provider then name for cleaner UI
    registry.sort(key=lambda x: (x["provider"], x["name"]))
    
    return registry

def get_model_registry() -> List[Dict[str, Any]]:
    """
    Returns the model registry, building it on first call and caching.
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = _build_model_registry()
    return _MODEL_CACHE





def get_available_models() -> List[Dict[str, Any]]:
    """
    Returns a list of models that have configured credentials.
    Only returns models whose provider has valid authentication.
    Uses litellm_provider field to accurately check credentials.
    """
    available = []
    registry = get_model_registry()
    
    for model in registry:
        # Use litellm_provider (e.g., "gemini", "vertex_ai") for credential check
        # Not the display name (e.g., "Gemini API", "Vertex AI")
        litellm_provider = model.get("litellm_provider")
        
        if litellm_provider and is_provider_available(litellm_provider):
            available.append(model)
    
    return available



def get_models_by_capability(supports_vision: bool = None) -> List[Dict[str, Any]]:
    """
    Returns available models filtered by capability.
    
    Args:
        supports_vision: If True, only vision models. If False, only text-only models.
                        If None, all available models.
    
    Returns:
        List of model metadata dictionaries
    """
    models = get_available_models()
    
    if supports_vision is None:
        return models
    
    return [m for m in models if m.get("supports_vision") == supports_vision]


def get_model_metadata(model_id: str) -> Optional[Dict[str, Any]]:
    """
    Returns metadata for a specific model ID.
    
    Args:
        model_id: Model identifier (e.g., "gemini/gemini-2.5-flash")
    
    Returns:
        Model metadata dict or None if not found
    """
    registry = get_model_registry()
    for model in registry:
        if model["id"] == model_id:
            return model
    return None



def select_model_for_input(
    has_image: bool = False,
    user_selection: Optional[str] = None
) -> str:
    """
    Intelligently selects the best model based on input type.
    
    Logic:
    1. If user explicitly selected a model, use that (highest priority)
    2. If input has image, select from vision-capable models
    3. If text-only, select from text-only models (or default text model)
    
    Args:
        has_image: Whether the input contains an image
        user_selection: User's explicitly selected model (optional)
    
    Returns:
        Model ID to use
    """
    # Priority 1: User's explicit selection
    if user_selection:
        # Validate that the selected model is available
        metadata = get_model_metadata(user_selection)
        if metadata and is_provider_available(metadata["provider"]):
            # If user selected a text-only model but input has image, warn but respect choice
            if has_image and not metadata.get("supports_vision"):
                print(f"WARNING: Selected model '{user_selection}' does not support images. "
                      f"This request may fail.")
            return user_selection
        else:
            print(f"WARNING: Selected model '{user_selection}' is not available. "
                  f"Falling back to default.")
    
    # Priority 2: Auto-select based on input type
    if has_image:
        # Need a vision-capable model
        
        # Define fallback vision models in order of preference
        FALLBACK_VISION_MODELS = [
            DEFAULT_MULTIMODAL_MODEL,
            "gemini/gemini-2.0-flash-exp",
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-pro",
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "anthropic/claude-3-5-sonnet-20241022"
        ]
        
        vision_models = get_models_by_capability(supports_vision=True)
        if vision_models:
            vision_model_ids = [m["id"] for m in vision_models]
            
            # Try fallback models in order
            for fallback_model in FALLBACK_VISION_MODELS:
                if fallback_model in vision_model_ids:
                    if fallback_model != DEFAULT_MULTIMODAL_MODEL:
                        print(f"INFO: Using fallback vision model '{fallback_model}' (default '{DEFAULT_MULTIMODAL_MODEL}' not available)")
                    return fallback_model
            
            # If no fallback found, use first available vision model
            print(f"INFO: Using first available vision model '{vision_models[0]['id']}'")
            return vision_models[0]["id"]
        else:
            raise RuntimeError("No vision-capable models available. Please configure an API key.")
    
    else:
        # Text-only input
        
        # Define fallback models in order of preference (known stable models)
        FALLBACK_TEXT_MODELS = [
            DEFAULT_TEXT_MODEL,
            "gemini/gemini-2.0-flash-exp",
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-pro",
            "openai/gpt-4o-mini",
            "anthropic/claude-3-5-haiku-20241022"
        ]
        
        # 1. Try fallback models in order
        available_ids = [m["id"] for m in get_available_models()]
        for fallback_model in FALLBACK_TEXT_MODELS:
            if fallback_model in available_ids:
                if fallback_model != DEFAULT_TEXT_MODEL:
                    print(f"INFO: Using fallback model '{fallback_model}' (default '{DEFAULT_TEXT_MODEL}' not available)")
                return fallback_model
            
        # 2. If no fallback found, prefer text-only models
        text_models = get_models_by_capability(supports_vision=False)
        if text_models:
            print(f"INFO: Using first available text model '{text_models[0]['id']}'")
            return text_models[0]["id"]
            
        # 3. Fallback: use any available model
        if available_ids:
            print(f"INFO: Using first available model '{available_ids[0]}'")
            return available_ids[0]
        else:
            raise RuntimeError("No AI models available. Please configure an API key.")


# Convenience functions for frontend
def get_text_models() -> List[Dict[str, Any]]:
    """Returns available text-only models"""
    return get_models_by_capability(supports_vision=False)


def get_vision_models() -> List[Dict[str, Any]]:
    """Returns available vision-capable models"""
    return get_models_by_capability(supports_vision=True)
