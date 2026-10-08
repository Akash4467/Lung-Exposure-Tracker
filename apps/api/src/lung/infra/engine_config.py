"""Reads engine/config.yaml once. Kept outside the engine so the engine does no I/O."""

import hashlib
from functools import lru_cache
from importlib.metadata import version
from importlib.resources import files

import yaml

from lung.engine.config import EngineConfig, parse_config
from lung.engine.footprint import FootprintConfig, parse_footprint


@lru_cache
def load_config() -> EngineConfig:
    text = files("lung.engine").joinpath("config.yaml").read_text(encoding="utf-8")
    return parse_config(yaml.safe_load(text))


@lru_cache
def engine_version() -> str:
    """Package version + a hash of config.yaml, stored with every score so scores computed
    with different parameters can be told apart."""
    text = files("lung.engine").joinpath("config.yaml").read_bytes()
    return f"{version('lung')}+{hashlib.sha256(text).hexdigest()[:8]}"


@lru_cache
def load_footprint() -> FootprintConfig:
    text = files("lung.engine").joinpath("footprint.yaml").read_text(encoding="utf-8")
    return parse_footprint(yaml.safe_load(text))
