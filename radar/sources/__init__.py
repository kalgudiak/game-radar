from .appstore import AppStoreSource
from .googleplay import GooglePlaySource
from .igdb import IGDBSource
from .itch import ItchSource
from .steam import SteamSource

REGISTRY = {s.name: s for s in (IGDBSource, SteamSource, AppStoreSource, GooglePlaySource, ItchSource)}
