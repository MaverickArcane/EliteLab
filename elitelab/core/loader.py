"""Module discovery and loading.

A module is a folder under ``modules/`` containing ``module.json`` and
``module.py``. The manifest declares ``requires`` (namespaces it reads) and
``provides`` (namespaces it writes); modules load in dependency order and a
missing or circular dependency fails loudly at startup rather than silently
at runtime. ``module.py`` exposes ``setup(core, module)``.
"""
import importlib.util
import json
import logging
import os

from . import config

log = logging.getLogger("elitelab.loader")


class ModuleInfo:
    def __init__(self, name, path, manifest):
        self.name, self.path, self.manifest = name, path, manifest
        self.requires = list(manifest.get("requires", []))
        self.provides = list(manifest.get("provides", []))
        self.cards = list(manifest.get("cards", []))
        self.order = int(manifest.get("order", 100))
        self.web_dir = os.path.join(path, "web")
        self.instance = None

    def to_json(self):
        return {"name": self.name, "version": self.manifest.get("version"), "description": self.manifest.get("description", ""),
                "requires": self.requires, "provides": self.provides, "order": self.order,
                "cards": [{**c, "script": f"/modules/{self.name}/{c['script']}"} for c in self.cards],
                "has_web": os.path.isdir(self.web_dir)}


def discover(modules_dir=None):
    modules_dir = modules_dir or config.MODULES_DIR
    found = {}
    if not os.path.isdir(modules_dir):
        return found
    for name in sorted(os.listdir(modules_dir)):
        path = os.path.join(modules_dir, name)
        mf = os.path.join(path, "module.json")
        if not os.path.isfile(mf) or not os.path.isfile(os.path.join(path, "module.py")):
            continue
        if name in config.DISABLED_MODULES:
            log.info("module %s disabled by ELITELAB_DISABLE", name)
            continue
        with open(mf, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        if manifest.get("name", name) != name:
            raise RuntimeError(f"module folder '{name}' has manifest name '{manifest.get('name')}'; they must match")
        found[name] = ModuleInfo(name, path, manifest)
    return found


def resolve_order(mods):
    """Topological sort on ``requires``; raises RuntimeError on missing/circular deps."""
    provided_by = {}
    for m in mods.values():
        for ns in m.provides:
            provided_by[ns] = m.name
    order, state = [], {}     # state: 1 = visiting, 2 = done

    def visit(m, chain):
        if state.get(m.name) == 2:
            return
        if state.get(m.name) == 1:
            raise RuntimeError("circular module dependency: " + " -> ".join(chain + [m.name]))
        state[m.name] = 1
        for ns in m.requires:
            dep = provided_by.get(ns)
            if dep is None:
                raise RuntimeError(f"module '{m.name}' requires '{ns}' but no module provides it")
            visit(mods[dep], chain + [m.name])
        state[m.name] = 2
        order.append(m)

    for m in sorted(mods.values(), key=lambda x: (x.order, x.name)):
        visit(m, [])
    return order


def load_all(core):
    mods = discover()
    ordered = resolve_order(mods)
    for m in ordered:
        spec = importlib.util.spec_from_file_location(f"elitelab_modules.{m.name}", os.path.join(m.path, "module.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "setup"):
            raise RuntimeError(f"module '{m.name}' has no setup(core, module) function")
        m.instance = module
        module.setup(core, m)
        if os.path.isdir(m.web_dir):
            core.http.mount(f"/modules/{m.name}/", m.web_dir)
        core.modules[m.name] = m
        log.info("loaded module %s (requires=%s provides=%s)", m.name, m.requires, m.provides)
    return ordered
