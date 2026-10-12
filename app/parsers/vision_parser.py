"""Vision parser using unified Qwen2.5-VL engine."""
import sys

if "/app" not in sys.path:
    sys.path.append("/app")

from llm import get_vlm_engine


def parse_image(path: str) -> list[dict]:
    """Extract text from an image using the unified Qwen2.5-VL engine."""
    engine = get_vlm_engine()
    return engine.parse_image(path)


def unload_vlm():
    """No-op: unified Qwen2.5-VL remains resident in memory for textual reasoning."""
    pass
