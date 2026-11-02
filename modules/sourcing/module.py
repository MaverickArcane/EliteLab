"""Nearby commodity source tool; shared search implementation lives in core."""
from elitelab.core.commodity_sources import Sourcing


def setup(core, module):
    sourcing = Sourcing(core)
    core.http.route("/api/sourcing/commodity", sourcing.find, tool="find_commodity_sources", module=module.name,
        description="Find reported commodity sellers within a strict radius of your ship or a named system, including fleet carriers. Sorted by verified distance; shows stock age and unknown docking access. Never silently widens radius.",
        params={"commodity": {"type": "string", "required": True, "description": "Commodity name, e.g. Modular Terminals"},
                "reference": {"type": "string", "description": "Origin system; default current ship system (not carrier)"},
                "quantity": {"type": "integer", "default": 25, "description": "Minimum stock and purchase quantity"},
                "max_distance_ly": {"type": "integer", "default": 25, "description": "Strict radius 1-500 Ly; never widened automatically"},
                "max_days": {"type": "integer", "default": 2, "description": "Maximum market report age, 1-30 days"},
                "carriers": {"type": "string", "enum": ["include", "only", "exclude"], "default": "include"},
                "pad": {"type": "string", "enum": ["S", "M", "L"], "default": "L"},
                "limit": {"type": "integer", "default": 20}})
