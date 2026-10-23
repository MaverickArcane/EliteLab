"""EliteLab: a small, self-hosted live dashboard for Elite Dangerous.

Modules
-------
config   : paths, ports and environment overrides
journal  : turns the game's journal/Status/Cargo/Market files into one state dict
spansh   : thin cached clients for the Spansh and EDSM public APIs
server   : the HTTP server that serves the web UI and the JSON API
"""

__version__ = "0.3.0"
