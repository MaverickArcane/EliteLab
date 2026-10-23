"""EliteLab: a small, self-hosted, modular live dashboard for Elite Dangerous
with an AI-facing API (every route is also an MCP tool).

    elitelab/core/   bus, store, services, http (+SSE), loader, journal watcher
    elitelab/mcp.py  Model Context Protocol server proxying the HTTP API
    modules/<name>/  self-contained features: module.json + module.py + web/
    web/             the browser shell that hosts module cards
"""

__version__ = "0.4.0"
