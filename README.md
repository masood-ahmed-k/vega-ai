# VEGA AI — Autonomous AI Operating System for Windows

> A Jarvis-style AI assistant that runs as an intelligent operating layer on your Windows computer.
> Multi-agent architecture, self-evolving intelligence, voice control, screen vision, computer automation, and a futuristic HUD.

## Features

### Core Intelligence
- **Multi-Agent System** — Planner, Research, Resume, Job, Automation, Study, Memory, Code, Email, Finance, Health, System Monitor agents
- **Multi-Model Router** — Auto-selects between OpenAI, Claude, Gemini, and local Ollama models based on task type, cost, and learned performance
- **Self-Evolution Engine** — VEGA rewrites its own agents, skills, and strategies. Snapshots before every change for rollback safety.
- **ReAct Planning Loop** — Reason → Act → Observe → Repeat with self-correction

### Capabilities
- **Voice Interface** — Wake word detection, speech recognition (Whisper), text-to-speech with multiple voices
- **Screen Vision** — Screenshot capture, UI element detection, visual analysis via AI
- **Computer Automation** — Mouse/keyboard control, app launching, workflow automation
- **Browser Automation** — Playwright-based web automation
- **Memory System** — Working (RAM), Episodic (ChromaDB vectors), Procedural (SQLite), Knowledge Graph
- **Skill System** — Hot-loadable plugins, skill chaining, auto-generated skills
- **Scheduler** — Cron-style recurring tasks, reminders, daily automations

### Interface
- **Desktop HUD** — Futuristic web-based dashboard with real-time stats, gamification (XP/levels), task timeline, agent activity feed
- **REST API** — External tools can trigger VEGA actions
- **CLI Tools** — `vega start`, `vega stop`, `vega status`, `vega logs`

### Safety
- **Snapshot System** — Git-like versioning before every self-modification
- **Action Approval** — Single-click confirmation for destructive OS actions
- **Encrypted Key Vault** — API keys stored securely, never in plaintext config
- **Audit Logging** — Every action logged with timestamps

---

## Quick Start

### Prerequisites
- Python 3.11+
- Windows 10/11
- Ollama installed (optional, for local models)

### Installation

```bash
# Clone or copy the VEGA_AI folder
cd VEGA_AI

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
python -m tools.setup_keys

# Initialize memory database
python -m memory.init_db

# Start VEGA
python main.py
```

### First Run
1. VEGA will open the HUD in your default browser at `http://localhost:8888`
2. Say "Hey VEGA" or type a command in the HUD
3. Try: "Search for Python developer jobs in Berlin"
4. Try: "Take a screenshot and describe what you see"
5. Try: "Create a study plan for machine learning"

---

## Configuration

Edit `config/settings.yaml`:

```yaml
models:
  default_cloud: "gpt-4o"
  default_local: "llama3"
  enable_ollama: true

voice:
  wake_word: "hey vega"
  tts_voice: "nova"
  continuous_mode: false

hud:
  port: 8888
  theme: "cyberpunk"

security:
  require_approval_for:
    - delete_files
    - send_email
    - run_scripts
  auto_snapshot: true

evolution:
  enabled: true
  auto_optimize_router: true
  auto_generate_skills: true
```

---

## Architecture

```
USER → VOICE/HUD → COMMAND CORE → PLANNER (ReAct Loop)
                                       ↓
                               AGENT REGISTRY
                          ↓         ↓         ↓
                     Research   Automation   Code   ...
                          ↓         ↓         ↓
                    TOOLS + MODELS + COMPUTER CONTROL
                               ↓
                        RESULT SYNTHESIS
                               ↓
                     MEMORY + EVOLUTION ENGINE
                               ↓
                             USER
```

---

## License
Private — built for Masood.
