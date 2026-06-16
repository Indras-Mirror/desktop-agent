"""
Vision fallback for desktop-agent via OpenRouter.

When AT-SPI + OCR give poor results (low confidence, empty output,
or explicitly requested), this module sends screenshots to a vision
model (default: x-ai/grok-4.3) for natural language description.

Uses the same OpenRouter key as the visionproxy MCP server.

Usage:
    from modular.vision_fallback import describe_screen, is_available

    if is_available():
        description = describe_screen("/tmp/screenshot.png")

Credentials: Reads OPENROUTER_API_KEY from environment.
The visionproxy MCP server already has this in its env config.
"""

import base64
import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests

# ── Configuration ────────────────────────────────────────────────────────

# Same key as visionproxy MCP
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Default model: Grok 4.3 — same as visionproxy
OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "x-ai/grok-4.3"
)

# Fallback models to try if primary fails
FALLBACK_MODELS = [
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4-20250514",
]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# MIME type detection
_MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def is_available() -> bool:
    """Check if vision fallback is configured and reachable."""
    return bool(OPENROUTER_API_KEY)


def _get_mime_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return _MIME_MAP.get(ext, "image/png")


def describe_image(
    image_path: str,
    prompt: str = "Describe this screenshot in detail. "
                  "What UI elements, text, buttons, menus, and content are visible?",
    model: Optional[str] = None,
    timeout: int = 30,
) -> str:
    """Send an image to OpenRouter for vision description.

    Args:
        image_path: Path to screenshot/image file
        prompt: What to ask the vision model
        model: OpenRouter model ID (default: x-ai/grok-4.3)
        timeout: Request timeout in seconds

    Returns:
        Natural language description of the image

    Raises:
        FileNotFoundError: If image_path doesn't exist
        RuntimeError: If API key is not set or API call fails
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. "
            "Set it in your environment or run via visionproxy config."
        )

    expanded = os.path.expanduser(image_path)
    if not os.path.exists(expanded):
        raise FileNotFoundError(f"Image not found: {expanded}")

    # Read and encode
    with open(expanded, "rb") as f:
        image_bytes = f.read()

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    mime = _get_mime_type(expanded)

    chosen_model = model or OPENROUTER_MODEL
    models_to_try = [chosen_model] + [
        m for m in FALLBACK_MODELS if m != chosen_model
    ]

    last_error = None

    for attempt_model in models_to_try:
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": attempt_model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime};base64,{image_b64}"
                                },
                            },
                        ],
                    }],
                },
                timeout=timeout,
            )

            if response.status_code == 200:
                data = response.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                if not content:
                    raise RuntimeError(
                        f"Empty response from {attempt_model}"
                    )
                return content

            # Non-200: try next model
            last_error = RuntimeError(
                f"OpenRouter {attempt_model}: HTTP {response.status_code} "
                f"— {response.text[:200]}"
            )

        except requests.exceptions.Timeout:
            last_error = RuntimeError(
                f"OpenRouter {attempt_model}: timeout after {timeout}s"
            )
        except requests.exceptions.ConnectionError as e:
            last_error = RuntimeError(
                f"OpenRouter {attempt_model}: connection failed — {e}"
            )

    raise last_error or RuntimeError("All vision models failed")


def describe_screen(
    image_path: Optional[str] = None,
    prompt: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 30,
) -> dict:
    """Describe the current screen using vision AI.

    This is the primary API for desktop-agent. Takes a screenshot
    if no path is given, then asks the vision model to describe it.

    Args:
        image_path: Screenshot path (auto-captures if None)
        prompt: Custom prompt (uses screen-analysis default if None)
        model: OpenRouter model (default: x-ai/grok-4.3)
        timeout: Request timeout

    Returns:
        Dict with keys:
            success: bool
            description: str (the model's response)
            model: str (which model responded)
            error: str (if failed)
    """
    if not is_available():
        return {
            "success": False,
            "description": "",
            "model": "",
            "error": "OPENROUTER_API_KEY not configured",
        }

    # Auto-capture screenshot if no path given
    if image_path is None:
        from .input import screenshot as take_screenshot

        image_path = "/tmp/desktop-agent-vision.png"
        take_screenshot(image_path)

    if prompt is None:
        prompt = (
            "You are analyzing a Linux desktop screenshot for automation purposes. "
            "Describe in detail:\n"
            "1. What application/window is in focus?\n"
            "2. What UI elements are visible (buttons, menus, text fields, lists)?\n"
            "3. What text content is displayed?\n"
            "4. What is the overall state of the screen?\n"
            "Be specific about positions (top-left, center, bottom-right, etc.) "
            "and mention any interactive elements and their labels."
        )

    try:
        desc = describe_image(image_path, prompt, model=model, timeout=timeout)
        return {
            "success": True,
            "description": desc,
            "model": model or OPENROUTER_MODEL,
            "error": "",
        }
    except Exception as e:
        return {
            "success": False,
            "description": "",
            "model": model or OPENROUTER_MODEL,
            "error": str(e),
        }


def ask_vision(
    question: str,
    image_path: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 30,
) -> str:
    """Ask a specific question about the screen.

    Shorthand for describe_screen with a custom prompt.

    Args:
        question: What to ask about the screen
        image_path: Screenshot path (auto-captures if None)
        model: OpenRouter model
        timeout: Request timeout

    Returns:
        The model's answer, or error message prefixed with "Error: "
    """
    result = describe_screen(
        image_path=image_path,
        prompt=question,
        model=model,
        timeout=timeout,
    )
    if result["success"]:
        return result["description"]
    return f"Error: {result['error']}"


# ── Self-test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python vision_fallback.py <image_path> [question]")
        print(f"  API key: {'configured' if is_available() else 'MISSING'}")
        print(f"  Model: {OPENROUTER_MODEL}")
        sys.exit(1)

    path = sys.argv[1]
    question = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(path):
        print(f"Error: file not found: {path}")
        sys.exit(1)

    if question:
        answer = ask_vision(question, path)
        print(answer)
    else:
        result = describe_screen(path)
        if result["success"]:
            print(f"Model: {result['model']}")
            print(f"---")
            print(result["description"])
        else:
            print(f"Error: {result['error']}")
            sys.exit(1)
