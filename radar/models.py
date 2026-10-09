from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Game:
    source: str                      # igdb | steam | appstore | googleplay | itch
    source_id: str
    title: str
    release_date: Optional[str] = None   # ISO yyyy-mm-dd (first release)
    platforms: list = field(default_factory=list)
    raw_genres: list = field(default_factory=list)   # genres as the store reports them
    tags: list = field(default_factory=list)         # user tags / keywords, most relevant first
    game_modes: list = field(default_factory=list)
    developer: Optional[str] = None
    publisher: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    is_free: Optional[bool] = None
    has_iap: Optional[bool] = None
    rating: Optional[float] = None       # normalised 0-100
    rating_count: Optional[int] = None
    installs: Optional[int] = None
    description: str = ""
    url: str = ""
    icon_url: str = ""
    content_rating: Optional[str] = None
    languages: list = field(default_factory=list)
    links: dict = field(default_factory=dict)         # label -> url (store pages, website, socials)
    extra: dict = field(default_factory=dict)
    # filled by the classifier
    genre: str = "Other"
    subgenres: list = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Game":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)
