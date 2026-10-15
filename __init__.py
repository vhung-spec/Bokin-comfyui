"""Bokin: Shakker-style image upscaling for ComfyUI."""

import logging

from .bokin.nodes_upscale import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

try:
    from .bokin import app_routes  # noqa: F401  (registers the /bokin page)
except Exception as e:  # the nodes still work without the page
    logging.getLogger("Bokin").warning("Bokin Upscaler page not available: %s", e)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
