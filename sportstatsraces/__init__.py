"""Football-stats race pipeline. Reuses races/ render engine via plug-ins."""

from races.sources import REGISTRY as _SOURCE_REGISTRY
from races.assets import REGISTRY as _ASSET_REGISTRY

from .sources.fbref import FbrefPLSource
from .assets.headshots import HeadshotProvider

_SOURCE_REGISTRY['fbref_pl'] = FbrefPLSource
_ASSET_REGISTRY['headshots'] = HeadshotProvider
