"""
VEGA AI — HUD Web Interface Server
Serves the futuristic desktop HUD and handles WebSocket communication.
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import structlog

logger = structlog.get_logger("vega.hud")

UI_DIR = Path(__file__).parent


def setup_hud(app: FastAPI):
    """Mount the HUD static files and template route on the FastAPI app."""
    
    static_dir = UI_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    (static_dir / "css").mkdir(exist_ok=True)
    (static_dir / "js").mkdir(exist_ok=True)

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def serve_hud():
        template_path = UI_DIR / "templates" / "hud.html"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        return "<h1>VEGA HUD - Template not found</h1>"

    logger.info("hud_mounted")
