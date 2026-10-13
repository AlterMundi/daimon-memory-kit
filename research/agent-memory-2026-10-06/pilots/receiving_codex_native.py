"""Compatibility entrypoint for preserved research clients; dispatch is shared."""
import receiving_exchange as exchange  # noqa: F401 - retained pilot compatibility
from codex_memory_provider import DISABLED, command, dispatch  # noqa: F401
