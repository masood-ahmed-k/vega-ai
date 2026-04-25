"""
VEGA AI — MCP Server
Exposes VEGA agents as Model Context Protocol tools so Claude Desktop,
Cline, Zed, and any MCP client can drive VEGA.

Usage:
    python -m mcp_server                    # stdio transport (for Claude Desktop)
    python mcp_server.py --transport=sse    # SSE for web clients

Claude Desktop config (put in %APPDATA%\\Claude\\claude_desktop_config.json):
{
  "mcpServers": {
    "vega": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "C:\\\\Users\\\\masoo\\\\Downloads\\\\Vega_Final_1\\\\Vega_Final"
    }
  }
}
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from core import load_config
from core.command_core import VEGACore


async def run_stdio():
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import Tool, TextContent
    except ImportError:
        print("MCP SDK not installed. Install: pip install mcp", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    vega = VEGACore(config)
    exposed = set(config.get("mcp", {}).get("expose_agents", []))

    server = Server("vega-ai")

    @server.list_tools()
    async def list_tools():
        tools = []
        for agent in vega.registry.get_all().values():
            agent_name = getattr(agent, "name", "")
            if not agent_name:
                continue
            if exposed and agent_name not in exposed:
                continue
            tools.append(Tool(
                name=f"vega_{agent_name}",
                description=f"{agent.description} (capabilities: {', '.join(getattr(agent, 'capabilities', []))})",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "Natural-language task for the agent"},
                        "context": {"type": "object", "description": "Optional context dict"}
                    },
                    "required": ["task"]
                }
            ))
        # Also expose the overall planner
        tools.append(Tool(
            name="vega_ask",
            description="Ask VEGA anything — routes through the planner and chooses the best agent.",
            inputSchema={
                "type": "object",
                "properties": {"task": {"type": "string"}},
                "required": ["task"]
            }
        ))
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        task = arguments.get("task", "")
        context = arguments.get("context", {}) or {}
        if name == "vega_ask":
            result = await vega.process_command(task)
            return [TextContent(type="text", text=str(result.get("output", "")))]
        if name.startswith("vega_"):
            agent_name = name[5:]
            agent = vega.registry.get(agent_name)
            if not agent:
                return [TextContent(type="text", text=f"Agent '{agent_name}' not found")]
            res = await agent.execute(task, context)
            return [TextContent(type="text", text=res.output)]
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
