"""Turns any URL into a labelled link and orders a game's links: stores first,
then the official website, then community / video pages."""
from urllib.parse import urlparse

# (domain suffix, label, group) - group 0 = store, 1 = website, 2 = community
_DOMAINS = [
    ("store.steampowered.com", "Steam", 0), ("steamcommunity.com", "Steam Community", 2),
    ("apps.apple.com", "App Store", 0), ("itunes.apple.com", "App Store", 0),
    ("play.google.com", "Google Play", 0), ("itch.io", "itch.io", 0),
    ("store.epicgames.com", "Epic Games Store", 0), ("epicgames.com", "Epic Games Store", 0),
    ("gog.com", "GOG", 0), ("store.playstation.com", "PlayStation Store", 0),
    ("xbox.com", "Xbox Store", 0), ("apps.microsoft.com", "Microsoft Store", 0),
    ("nintendo.com", "Nintendo eShop", 0), ("meta.com", "Meta Quest Store", 0),
    ("oculus.com", "Meta Quest Store", 0), ("taptap.io", "TapTap", 0), ("crazygames.com", "CrazyGames", 0),
    ("poki.com", "Poki", 0), ("igdb.com", "IGDB", 2), ("youtube.com", "YouTube", 2),
    ("youtu.be", "YouTube", 2), ("discord.gg", "Discord", 2), ("discord.com", "Discord", 2),
    ("twitter.com", "X", 2), ("x.com", "X", 2), ("reddit.com", "Reddit", 2),
    ("twitch.tv", "Twitch", 2), ("tiktok.com", "TikTok", 2), ("instagram.com", "Instagram", 2),
    ("facebook.com", "Facebook", 2), ("wikipedia.org", "Wikipedia", 2), ("fandom.com", "Wiki", 2),
]
_GROUP = {}


def label_for(url: str):
    host = (urlparse(url).netloc or "").lower().split(":")[0]
    for dom, label, group in _DOMAINS:
        if host == dom or host.endswith("." + dom):
            return label, group
    return "Website", 1


def add_link(links: dict, url: str, label: str = None):
    """Adds url to the links dict (label -> url) unless that label is already taken."""
    if not url or not str(url).startswith(("http://", "https://")):
        return links
    lab = label or label_for(url)[0]
    links.setdefault(lab, url)
    return links


def ordered(links: dict) -> dict:
    return dict(sorted(links.items(), key=lambda kv: (label_for(kv[1])[1], kv[0] == "IGDB")))
