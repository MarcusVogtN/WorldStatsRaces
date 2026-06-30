from .base import DataSource, SourceResult
from .world_bank import WorldBankSource
from .csv_source import CsvSource
from .ssa_names import SsaNamesSource

REGISTRY = {
    'world_bank': WorldBankSource,
    'csv': CsvSource,
    'ssa_names': SsaNamesSource,
}


def build_source(cfg: dict) -> DataSource:
    kind = cfg.get('type', 'world_bank')
    if kind not in REGISTRY:
        raise ValueError(f"Unknown source type: {kind}")
    return REGISTRY[kind](cfg)
