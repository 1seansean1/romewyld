"""Source registry."""
from __future__ import annotations

from .base import Source
from .remotive import RemotiveSource
from .remoteok import RemoteOKSource
from .arbeitnow import ArbeitnowSource
from .themuse import TheMuseSource
from .jobicy import JobicySource
from .hackernews import HackerNewsSource
from .adzuna import AdzunaSource
from .usajobs import USAJobsSource
from .greenhouse import GreenhouseSource
from .lever import LeverSource
from .ashby import AshbySource

_REGISTRY: dict[str, type[Source]] = {
    cls.name: cls
    for cls in [
        RemotiveSource, RemoteOKSource, ArbeitnowSource, TheMuseSource,
        JobicySource, HackerNewsSource, AdzunaSource, USAJobsSource,
        GreenhouseSource, LeverSource, AshbySource,
    ]
}

ALL_SOURCES = list(_REGISTRY.keys())


def get_source(name: str) -> Source:
    if name not in _REGISTRY:
        raise KeyError(f"unknown source '{name}'. available: {', '.join(ALL_SOURCES)}")
    return _REGISTRY[name]()
