# Contributing to VEGA AI

Thank you for your interest in contributing to VEGA! This document covers how to get set up and submit changes.

---

## Quick Start

```bash
git clone https://github.com/masood-ahmed-k/vega-ai.git
cd vega-ai
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## How to Contribute

### 🐛 Reporting Bugs

1. Check [existing issues](https://github.com/masood-ahmed-k/vega-ai/issues) first
2. Open a new issue with:
   - OS, GPU, VRAM, Python version
   - Steps to reproduce
   - Expected vs actual behaviour
   - Relevant log output

### 💡 Feature Requests

Open an issue with the `enhancement` label. Describe the use case — *why* you need it, not just *what* you want.

### 🔧 Pull Requests

1. Fork the repo and create a branch from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
2. Make your changes and add tests if applicable
3. Run the test suite:
   ```bash
   python -m pytest tests/ -v
   ```
4. Commit with a descriptive message
5. Open a PR against `main`

---

## Adding a New Agent

1. Create `agents/my_agent.py` following the base pattern:

```python
from agents.base import BaseAgent, AgentResult

class MyAgent(BaseAgent):
    name = "my_agent"
    description = "What this agent does"

    async def execute(self, task: str, context: dict) -> AgentResult:
        # your logic here
        return AgentResult(success=True, output="Done", agent=self.name)
```

2. Register in `core/command_core.py` → `_register_agents()`
3. Add to `config/settings.yaml` under `mcp.expose_agents` if you want MCP access

---

## Code Style

- Python 3.10+ type hints preferred
- Max line length: 120 chars
- Async-first: use `async def` for any I/O-bound operations
- Log with `structlog`: `logger = structlog.get_logger("vega.mymodule")`

---

## Running Tests

```bash
# Full suite
python -m pytest tests/ -v

# Specific test class
python -m pytest tests/test_core.py::TestMemory -v

# Without pytest installed
python tests/test_core.py
```

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
