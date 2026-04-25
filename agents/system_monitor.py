"""
VEGA AI — System Monitor Agent
Watches CPU, RAM, disk, network, and alerts on anomalies.
"""

import asyncio
from agents import BaseAgent, AgentResult
from core.event_bus import event_bus, Event
import structlog

logger = structlog.get_logger("vega.sysmon")


class SystemMonitorAgent(BaseAgent):
    name = "system_monitor"
    description = "Monitors system resources (CPU, RAM, disk, network) and alerts on anomalies"
    capabilities = ["system", "monitor", "cpu", "memory_usage", "disk", "network", "processes"]

    async def run(self, task: str, context: dict) -> AgentResult:
        stats = await self._get_system_stats()

        if "status" in task.lower() or "monitor" in task.lower() or "system" in task.lower():
            # Return formatted system status
            output = self._format_stats(stats)
            
            # Check for anomalies
            alerts = self._check_alerts(stats)
            if alerts:
                output += "\n\n!! ALERTS:\n" + "\n".join(alerts)
                for alert in alerts:
                    await event_bus.publish(Event(type="system.alert", data={"alert": alert}, source=self.name))

            return AgentResult(success=True, output=output, data=stats)
        else:
            # Use AI to interpret the request
            response = await self.router.query(
                prompt=f"System stats: {stats}\n\nUser request: {task}",
                system="You are a system monitoring assistant. Analyze the stats and answer the user's question.",
                task_type="fast"
            )
            return AgentResult(success=True, output=response.text, data=stats)

    async def _get_system_stats(self) -> dict:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            net = psutil.net_io_counters()
            
            # Top processes by CPU
            procs = []
            for p in sorted(psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
                           key=lambda p: p.info.get("cpu_percent", 0) or 0, reverse=True)[:5]:
                procs.append({
                    "name": p.info["name"],
                    "cpu": p.info.get("cpu_percent", 0),
                    "memory": round(p.info.get("memory_percent", 0), 1)
                })

            return {
                "cpu_percent": cpu,
                "ram_total_gb": round(mem.total / (1024**3), 1),
                "ram_used_gb": round(mem.used / (1024**3), 1),
                "ram_percent": mem.percent,
                "disk_total_gb": round(disk.total / (1024**3), 1),
                "disk_used_gb": round(disk.used / (1024**3), 1),
                "disk_percent": round(disk.used / disk.total * 100, 1),
                "net_sent_mb": round(net.bytes_sent / (1024**2), 1),
                "net_recv_mb": round(net.bytes_recv / (1024**2), 1),
                "top_processes": procs,
            }
        except ImportError:
            return {"error": "psutil not installed"}

    def _format_stats(self, stats: dict) -> str:
        if "error" in stats:
            return f"System monitoring unavailable: {stats['error']}"
        
        lines = [
            "=== VEGA SYSTEM MONITOR ===",
            f"CPU:  {stats['cpu_percent']}%",
            f"RAM:  {stats['ram_used_gb']}GB / {stats['ram_total_gb']}GB ({stats['ram_percent']}%)",
            f"DISK: {stats['disk_used_gb']}GB / {stats['disk_total_gb']}GB ({stats['disk_percent']}%)",
            f"NET:  UP {stats['net_sent_mb']}MB  DN {stats['net_recv_mb']}MB",
            "",
            "Top Processes:",
        ]
        for p in stats.get("top_processes", []):
            lines.append(f"  {p['name']:<25} CPU: {p['cpu']}%  RAM: {p['memory']}%")
        
        return "\n".join(lines)

    def _check_alerts(self, stats: dict) -> list[str]:
        alerts = []
        if stats.get("cpu_percent", 0) > 90:
            alerts.append(f"CPU usage critical: {stats['cpu_percent']}%")
        if stats.get("ram_percent", 0) > 90:
            alerts.append(f"RAM usage critical: {stats['ram_percent']}%")
        if stats.get("disk_percent", 0) > 95:
            alerts.append(f"Disk space critical: {stats['disk_percent']}% used")
        return alerts
