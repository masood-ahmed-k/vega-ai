"""
VEGA AI -- CLI Management Tool
Command-line interface for managing VEGA.

Usage:
    python -m tools.cli start
    python -m tools.cli status
    python -m tools.cli logs
    python -m tools.cli agents
    python -m tools.cli snapshot create "reason"
    python -m tools.cli snapshot list
    python -m tools.cli snapshot rollback <snapshot_id>
    python -m tools.cli evolve <agent_name>
"""

import sys
import json
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def cmd_start():
    print("Starting VEGA AI...")
    subprocess.run([sys.executable, "main.py"], cwd=str(Path(__file__).parent.parent))


def cmd_status():
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8888/api/status", timeout=5)
        data = json.loads(resp.read())
        print("")
        print("  ====================================")
        print("           VEGA AI STATUS")
        print("  ====================================")
        print(f"  Version:    {data.get('version', '?')}")
        print(f"  Uptime:     {data.get('uptime_seconds', 0)} seconds")
        print(f"  Agents:     {len(data.get('agents', []))}")
        print(f"  Skills:     {data.get('skills_loaded', 0)}")
        print(f"  Memories:   {data.get('memory_count', 0)}")
        print(f"  CPU:        {data.get('cpu', 0)}%")
        print(f"  RAM:        {data.get('ram', 0)}%")
        print(f"  Disk:       {data.get('disk', 0)}%")
        print(f"  Evolution:  {'ON' if data.get('evolution_enabled') else 'OFF'}")
        print("  ====================================")
        print("")
    except Exception:
        print("VEGA is not running. Start with: python main.py")


def cmd_agents():
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8888/api/agents", timeout=5)
        data = json.loads(resp.read())
        print("")
        print("  VEGA AI -- Registered Agents")
        print("  " + "=" * 50)
        for a in data.get("agents", []):
            status = "[ACTIVE]" if a.get("is_active") else "[idle]  "
            rate = f"{a.get('success_rate', 0)*100:.0f}%"
            print(f"  {status} {a['name']:<22} tasks: {a.get('total_tasks', 0):<6} success: {rate}")
        print("")
    except Exception:
        print("VEGA is not running.")


def cmd_logs(lines=50):
    log_path = Path(__file__).parent.parent / "logs" / "vega.log"
    if log_path.exists():
        with open(log_path) as f:
            all_lines = f.readlines()
            for line in all_lines[-lines:]:
                print(line, end="")
    else:
        print("No logs found. Start VEGA first.")


def cmd_audit(lines=30):
    log_path = Path(__file__).parent.parent / "logs" / "audit.log"
    if log_path.exists():
        with open(log_path) as f:
            all_lines = f.readlines()
            for line in all_lines[-lines:]:
                print(line, end="")
    else:
        print("No audit log found.")


def cmd_snapshot(action, *args):
    from core import load_config
    from security import SecurityManager
    config = load_config()
    sm = SecurityManager(config.get("security", {}))

    if action == "create":
        reason = args[0] if args else "manual"
        snap_id = sm.snapshots.create_snapshot(reason=reason)
        print(f"  [OK] Snapshot created: {snap_id}")

    elif action == "list":
        snapshots = sm.snapshots.list_snapshots()
        if not snapshots:
            print("  No snapshots found.")
            return
        print("")
        print("  VEGA AI -- Snapshots")
        print("  " + "=" * 60)
        for s in snapshots[:20]:
            print(f"  {s['id']:<30} {s.get('reason', ''):<20} {s.get('datetime', '')[:19]}")
        print("")

    elif action == "rollback":
        if not args:
            print("Usage: snapshot rollback <snapshot_id>")
            return
        success = sm.snapshots.rollback(args[0])
        print(f"  [OK] Rolled back to {args[0]}" if success else f"  [FAIL] Snapshot not found: {args[0]}")

    else:
        print("Usage: snapshot [create|list|rollback] [args]")


def cmd_evolve(agent_name):
    import urllib.request
    try:
        data = json.dumps({"agent": agent_name}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8888/api/evolution/evolve",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read())
        if result.get("success"):
            print(f"  [OK] Agent '{agent_name}' evolved. Snapshot: {result.get('snapshot_id')}")
        else:
            print(f"  [FAIL] Evolution failed: {result.get('reason', 'unknown')}")
    except Exception as e:
        print(f"  Error: {e}")


def cmd_router():
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8888/api/router/stats", timeout=5)
        data = json.loads(resp.read())
        print("")
        print("  VEGA AI -- Router Performance")
        print("  " + "=" * 60)
        for task, models in data.items():
            print(f"\n  Task: {task}")
            for model, stats in models.items():
                print(f"    {model:<30} calls: {stats.get('calls', 0):<6} score: {stats.get('score', 0):.3f}")
        print("")
    except Exception:
        print("VEGA is not running.")


def main():
    if len(sys.argv) < 2:
        print("")
        print("  VEGA AI CLI -- Management Tool")
        print("")
        print("  Commands:")
        print("    start                     Start VEGA AI")
        print("    status                    Show system status")
        print("    agents                    List all agents")
        print("    logs [lines]              Show recent logs")
        print("    audit [lines]             Show audit trail")
        print("    router                    Show model router stats")
        print("    snapshot create [reason]  Create a code snapshot")
        print("    snapshot list             List all snapshots")
        print("    snapshot rollback <id>    Rollback to a snapshot")
        print("    evolve <agent>            Trigger agent evolution")
        print("")
        return

    command = sys.argv[1]

    if command == "start": cmd_start()
    elif command == "status": cmd_status()
    elif command == "agents": cmd_agents()
    elif command == "logs": cmd_logs(int(sys.argv[2]) if len(sys.argv) > 2 else 50)
    elif command == "audit": cmd_audit(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    elif command == "router": cmd_router()
    elif command == "snapshot": cmd_snapshot(sys.argv[2] if len(sys.argv) > 2 else "list", *sys.argv[3:])
    elif command == "evolve":
        if len(sys.argv) < 3: print("Usage: evolve <agent_name>")
        else: cmd_evolve(sys.argv[2])
    else: print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
