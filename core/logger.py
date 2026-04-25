"""
VEGA AI — Logging Setup
Structured logging with rotation, levels, and audit trail.
"""

import sys
import structlog
from pathlib import Path
from logging import getLogger, StreamHandler, FileHandler, Formatter, DEBUG, INFO
from logging.handlers import RotatingFileHandler


def setup_logging(log_level: str = "INFO", log_dir: str = "./logs"):
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    level = getattr(__import__("logging"), log_level.upper(), INFO)

    # Console handler
    console = StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(Formatter("%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S"))

    # Main log file (rotating)
    main_file = RotatingFileHandler(log_path / "vega.log", maxBytes=10_000_000, backupCount=5)
    main_file.setLevel(DEBUG)
    main_file.setFormatter(Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s"))

    # Audit log (append-only, never rotated — tracks all actions)
    audit_file = FileHandler(log_path / "audit.log")
    audit_file.setLevel(INFO)
    audit_file.setFormatter(Formatter("%(asctime)s | %(message)s"))

    # Configure root logger
    root = getLogger()
    root.setLevel(DEBUG)
    root.addHandler(console)
    root.addHandler(main_file)

    # Configure audit logger
    audit = getLogger("vega.audit")
    audit.addHandler(audit_file)
    audit.propagate = False

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if level <= DEBUG else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def audit_log(action: str, agent: str = "system", details: str = "", status: str = "ok"):
    logger = getLogger("vega.audit")
    logger.info(f"ACTION={action} | AGENT={agent} | STATUS={status} | {details}")
