"""Initialize VEGA memory databases."""

from pathlib import Path
from memory import MemoryManager

def init():
    Path("./data").mkdir(exist_ok=True)
    mm = MemoryManager({})
    mm.procedural._init_db()
    print("[VEGA] Memory databases initialized.")

if __name__ == "__main__":
    init()
