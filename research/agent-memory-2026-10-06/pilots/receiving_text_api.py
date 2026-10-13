"""Compatibility entrypoint for preserved research clients; dispatch is shared."""
import receiving_exchange as exchange  # noqa: F401 - retained pilot compatibility
from text_memory_provider import ENDPOINTS, MODELS, parameters, dispatch  # noqa: F401
