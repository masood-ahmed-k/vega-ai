"""
VEGA AI -- API Key Setup Wizard
Run: python tools/setup_keys.py
"""

import os
import sys
from pathlib import Path
from getpass import getpass

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def setup():
    print("")
    print("  ======================================")
    print("       VEGA AI -- API Key Setup")
    print("  ======================================")
    print("")
    print("  Configure your AI provider API keys.")
    print("  Press Enter to skip any provider.")
    print("  (You can run Ollama locally for free)")
    print("")

    keys = {}

    key = getpass("  OpenAI API Key (sk-...): ").strip()
    if key:
        keys["OPENAI_API_KEY"] = key
        print("  > OpenAI key configured")

    key = getpass("  Anthropic API Key (sk-ant-...): ").strip()
    if key:
        keys["ANTHROPIC_API_KEY"] = key
        print("  > Anthropic key configured")

    key = getpass("  Google/Gemini API Key: ").strip()
    if key:
        keys["GOOGLE_API_KEY"] = key
        print("  > Google key configured")

    if not keys:
        print("")
        print("  No keys provided -- that is fine!")
        print("  VEGA will use Ollama (local) by default.")
        print("  Make sure Ollama is running: ollama serve")
        print("  And pull a model:            ollama pull llama3")
        print("")
        print("  You can add keys later by editing .env file.")
        return

    env_path = PROJECT_ROOT / ".env"
    with open(env_path, "w") as f:
        for k, v in keys.items():
            f.write(f"{k}={v}\n")

    print(f"")
    print(f"  > Keys saved to {env_path}")

    gitignore_path = PROJECT_ROOT / ".gitignore"
    if not gitignore_path.exists():
        with open(gitignore_path, "w") as f:
            f.write(".env\n__pycache__/\n*.pyc\ndata/\nlogs/\nsnapshots/\nvenv/\n.venv/\n")

    print("  > Setup complete! Start VEGA with: start.bat")
    print("")


if __name__ == "__main__":
    setup()
