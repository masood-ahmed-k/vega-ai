"""
VEGA AI -- Main Entry Point
Boots up all subsystems: core, HUD, voice, scheduler, API, and evolution.
"""

import asyncio
import os
import sys
import webbrowser
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file if it exists
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ[key.strip()] = value.strip()

from core import load_config
from core.logger import setup_logging
from core.command_core import VEGACore
from api import create_api
from ui import setup_hud
from voice import VoiceInterface
import structlog

logger = structlog.get_logger("vega.main")


async def main():
    """Boot VEGA AI."""
    print("")
    print("  ===================================================")
    print("   V   V  EEEEE  GGGG   AAA")
    print("   V   V  E      G      A   A")
    print("   V   V  EEEE   G  GG  AAAAA")
    print("    V V   E      G   G  A   A")
    print("     V    EEEEE  GGGG   A   A")
    print("")
    print("        AUTONOMOUS AI OPERATING SYSTEM")
    print("                  v1.1.0")
    print("     Qwen3 | Text-to-Video | Persistent Memory")
    print("  ===================================================")
    print("")

    # Load configuration
    config = load_config()
    setup_logging(log_level=config.get("system", {}).get("log_level", "INFO"))
    logger.info("config_loaded")

    # Create data directories
    Path("./data").mkdir(exist_ok=True)
    Path("./data/screenshots").mkdir(exist_ok=True)
    Path("./snapshots").mkdir(exist_ok=True)
    Path("./logs").mkdir(exist_ok=True)

    # Initialize VEGA Core
    vega = VEGACore(config)
    logger.info("core_initialized")

    # Warm up default model so first response is instant
    if config.get("models", {}).get("hardware", {}).get("preload_on_start", False):
        if hasattr(vega.router, "preload_model"):
            try:
                await vega.router.preload_model()
                logger.info("default_model_preloaded")
            except Exception as e:
                logger.warning("preload_failed", error=str(e))

    # Create API + HUD server
    app = create_api(vega)
    setup_hud(app)

    # Setup voice interface
    voice_config = config.get("voice", {})
    voice = VoiceInterface(voice_config)

    async def handle_voice_command(command: str) -> str:
        result = await vega.process_command(command)
        return result.get("output", "")

    voice.set_command_handler(handle_voice_command)

    # Setup scheduled tasks
    if config.get("scheduler", {}).get("enabled", True):
        if config.get("evolution", {}).get("enabled", True):
            vega.scheduler.add_task(
                name="evolution_cycle",
                callback=lambda data: asyncio.ensure_future(vega.run_evolution_cycle()),
                interval_seconds=21600
            )
        vega.scheduler.add_task(
            name="system_health_check",
            callback=lambda data: asyncio.ensure_future(
                vega.registry.get("system_monitor").execute("system status check", {})
                if vega.registry.get("system_monitor") else asyncio.sleep(0)
            ),
            interval_seconds=300
        )

    # Start all async services
    hud_config = config.get("hud", {})
    host = hud_config.get("host", "127.0.0.1")
    port = hud_config.get("port", 8888)

    # Open browser
    if hud_config.get("open_browser", True):
        webbrowser.open(f"http://{host}:{port}")

    # Run uvicorn
    import uvicorn
    uvi_config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="warning",
        ws_max_size=16 * 1024 * 1024,
    )
    server = uvicorn.Server(uvi_config)

    tasks = [
        server.serve(),
        vega.scheduler.start(),
    ]

    if voice_config.get("enabled", False):
        tasks.append(voice.voice_loop())

    logger.info("vega_online", hud=f"http://{host}:{port}")
    print(f"  [OK] HUD:       http://{host}:{port}")
    print(f"  [OK] API:       http://{host}:{port}/api/")
    print(f"  [OK] Agents:    {len(vega.registry.list_agents())} online")
    print(f"  [OK] Voice:     {'enabled' if voice_config.get('enabled') else 'disabled'}")
    print(f"  [OK] Evolution: {'enabled' if config.get('evolution', {}).get('enabled') else 'disabled'}")
    print(f"  [OK] Models:    Ollama ({config.get('models', {}).get('default_local', 'qwen3:30b-a3b')})")
    print(f"  [OK] Video:     {len(config.get('video', {}).get('providers', {}))} providers ready")
    print(f"  [OK] Memory:    persistent chats {'on' if config.get('memory', {}).get('chat_persistence', {}).get('enabled') else 'off'}")
    print("")
    print("  VEGA is ready. Open the HUD or type commands via API.")
    print("  Press Ctrl+C to shutdown.")
    print("")

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    finally:
        await vega.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  VEGA shutting down...")
