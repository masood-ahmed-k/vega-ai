@echo off
REM VEGA AI — MCP Server (expose VEGA to Claude Desktop)

cd /d "%~dp0.."

echo.
echo ============================================================
echo   VEGA AI — MCP Server Dependencies
echo ============================================================
echo.
echo Installs the Model Context Protocol SDK so Claude Desktop
echo and other MCP clients can drive VEGA.
echo.
pause

python -m pip install mcp>=1.0.0

echo.
echo [OK] MCP SDK installed.
echo.
echo Next step — add to Claude Desktop config at:
echo   %%APPDATA%%\Claude\claude_desktop_config.json
echo.
echo {
echo   "mcpServers": {
echo     "vega": {
echo       "command": "python",
echo       "args": ["-m", "mcp_server"],
echo       "cwd": "%CD%"
echo     }
echo   }
echo }
echo.
pause
