"""EliteLab: a small, self-hosted, modular live dashboard for Elite Dangerous
with an AI-facing API (every route is also an MCP tool).

    elitelab/core/   bus, store, services, http (+SSE), loader, journal watcher
    elitelab/mcp.py  Model Context Protocol server proxying the HTTP API
    modules/<name>/  self-contained features: module.json + module.py + web/
    web/             the browser shell that hosts module cards
"""

__version__ = "0.6.0-beta.1"
# Native metadata needs numeric versions; the dashboard/diagnostics retain the
# complete prerelease identity. Debian uses '~' so beta sorts before stable.
__native_version__ = __version__.split('-', 1)[0]
__debian_version__ = __version__.replace('-beta.', '~beta.')
