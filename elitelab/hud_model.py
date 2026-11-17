"""Content contract shared by activity providers and the native HUD shell."""
from dataclasses import dataclass, field
import math


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def number(value, suffix=''):
    return f'{value:g}{suffix}' if finite(value) else '--'


@dataclass(frozen=True)
class Card:
    title: str
    context: str = ''
    status: str = 'WAITING'
    primary: str = '--'
    primary_label: str = ''
    secondary: str = ''
    metric: str = '--'
    metric_label: str = ''
    stats: tuple = ()
    note: str = ''
    warning: str = ''
    tone: str = 'amber'
    visual: dict = field(default_factory=lambda: {'kind': 'badge', 'label': 'HUD', 'text': '--'})


@dataclass(frozen=True)
class Mode:
    label: str
    endpoint: str
    required_key: str
    build: object
    group: str = 'Mining'
    interval: float = 1
