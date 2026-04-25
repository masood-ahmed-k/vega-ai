# Changelog

All notable changes to VEGA AI are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [1.2.0] — 2026-04-25

### Added
- **Dynamic HUD name** — reads `system.user` from `config/settings.yaml`, no hardcoded names
- **GitHub Actions CI** — lint + pytest + gitleaks on every PR
- **CONTRIBUTING.md** — agent authoring guide, code style, test instructions
- **Issue templates** — bug report and feature request forms
- **SECURITY.md** — responsible disclosure policy
- Real-time token streaming confirmed working (~3s first token on RTX 4060)
- `preload_on_start: true` default — model pre-warmed on boot

### Changed
- README completely rewritten with badges, screenshots, full configuration reference, API docs
- Default `user` changed from hardcoded name to `"Hunter"` placeholder
- `scripts/start.bat` and `install.bat` — fixed `VEGA_ROOT` path bug after `cd /d "%~dp0.."`

### Fixed
- `start.bat` path resolution when launched from outside the `scripts/` directory
- `install.bat` typo: `Scriptsctivate` → `Scripts\activate`

---

## [1.1.0] — 2026-04-10

### Added
- **Text-to-video** — 8 FREE providers (Wan2, CogVideoX, LTX, AnimateDiff + 4 cloud)
- **Browser Agent** — Playwright-powered autonomous browsing
- **RAG** — local file indexing with `nomic-embed-text` Ollama embeddings
- **MCP Server** — expose VEGA agents to Claude Desktop
- **Voice** — wake word + Whisper STT + pyttsx3 TTS
- **Self-Evolution** — auto-generates skill files after 3 similar requests

### Changed
- Upgraded to Qwen3 (8B / 30B-A3B / 32B) from Llama3
- Streaming latency improved from ~60s → ~3s first token

---

## [1.0.0] — 2026-03-01

### Added
- Initial release
- 14 specialized agents: Planner, Research, Code, Browser, Image, Video, Resume, Job, Study, Email, Finance, Health, Memory, SystemMonitor
- Solo Leveling RPG HUD (single HTML file)
- FastAPI + WebSocket backend
- ChromaDB episodic memory + SQLite procedural memory + NetworkX knowledge graph
- SDXL Turbo + Flux.1-schnell image generation
