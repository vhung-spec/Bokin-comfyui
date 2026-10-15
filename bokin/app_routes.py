"""Serve the Bokin Upscaler page at /bokin on the ComfyUI server.

The page is plain HTML/JS: it uploads the image, queues a Bokin workflow and
follows its progress through ComfyUI's own HTTP and WebSocket API.
"""

from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web
from server import PromptServer

PAGE = Path(__file__).resolve().parent.parent / "web_app" / "index.html"

routes = PromptServer.instance.routes


@routes.get("/bokin")
async def bokin_page(request):
    return web.FileResponse(PAGE, headers={"Cache-Control": "no-cache"})


@routes.get("/bokin/")
async def bokin_page_slash(request):
    raise web.HTTPFound("/bokin")


logging.getLogger("Bokin").info("Bokin Upscaler: open /bokin on this ComfyUI server")
