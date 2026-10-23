"""map module: coordinate lookups for the UI. The drawing lives in web/card.js."""

NS = "map"


def setup(core, module):
    core.store.set(NS, "ready", True)
    core.http.route("/api/coords", lambda q: core.services.edsm_coords((q.get("names") or "").split("|")),
                    tool="get_system_coords", module=module.name,
                    description="Galactic coordinates for one or more systems (EDSM).",
                    params={"names": {"type": "string", "description": "System names separated by |", "required": True}})
