"""One genre taxonomy across every store, plus sub-genre detection.

Each game gets exactly one primary `genre` (for the daily breakdown) and any number of
`subgenres` (the mechanics a hybrid-casual studio actually cares about: merge, runner,
survivors-like, idle RPG...). When a game maps to several genres, the most specific one
wins, using the order of GENRES below (Roguelike beats Action, Puzzle beats Casual).
"""
import re

GENRES = [
    "Roguelike", "Idle & Incremental", "Visual Novel", "MMO", "Fighting", "Racing", "Sports",
    "Shooter", "Platformer", "Card & Board", "Casino", "Word & Trivia", "Music & Rhythm",
    "Horror", "Survival", "Sandbox", "Puzzle", "Strategy", "RPG", "Simulation", "Adventure",
    "Arcade", "Action", "Casual", "Family & Kids", "Other",
]
PRIORITY = {g: i for i, g in enumerate(GENRES)}

# Lower-cased store genre / tag / theme  ->  canonical genre (None = ignore, e.g. "Indie")
RAW_MAP = {
    # shared / Apple / Google Play
    "action": "Action", "adventure": "Adventure", "arcade": "Arcade", "board": "Card & Board",
    "card": "Card & Board", "casino": "Casino", "casual": "Casual", "dice": "Card & Board",
    "educational": "Family & Kids", "education": "Family & Kids", "family": "Family & Kids",
    "kids": "Family & Kids", "music": "Music & Rhythm", "puzzle": "Puzzle", "racing": "Racing",
    "role playing": "RPG", "role-playing": "RPG", "rpg": "RPG", "simulation": "Simulation",
    "sports": "Sports", "sport": "Sports", "strategy": "Strategy", "trivia": "Word & Trivia",
    "word": "Word & Trivia",
    # Steam genres
    "massively multiplayer": "MMO", "indie": None, "free to play": None, "early access": None,
    # IGDB genres
    "point-and-click": "Adventure", "fighting": "Fighting", "shooter": "Shooter",
    "platform": "Platformer", "real time strategy (rts)": "Strategy",
    "role-playing (rpg)": "RPG", "simulator": "Simulation",
    "turn-based strategy (tbs)": "Strategy", "tactical": "Strategy",
    "hack and slash/beat 'em up": "Action", "quiz/trivia": "Word & Trivia", "pinball": "Arcade",
    "visual novel": "Visual Novel", "card & board game": "Card & Board", "moba": "Strategy",
    # IGDB themes
    "horror": "Horror", "survival": "Survival", "sandbox": "Sandbox", "party": "Casual",
    "business": "Simulation", "4x (explore, expand, exploit, and exterminate)": "Strategy",
    # common Steam user tags
    "roguelike": "Roguelike", "roguelite": "Roguelike", "rogue-like": "Roguelike",
    "rogue-lite": "Roguelike", "action roguelike": "Roguelike", "idler": "Idle & Incremental",
    "clicker": "Idle & Incremental", "incremental": "Idle & Incremental",
    "fps": "Shooter", "third-person shooter": "Shooter", "platformer": "Platformer",
    "2d platformer": "Platformer", "3d platformer": "Platformer", "card game": "Card & Board",
    "board game": "Card & Board", "deckbuilding": "Card & Board",
    "survival horror": "Horror", "city builder": "Simulation", "farming sim": "Simulation",
    "life sim": "Simulation", "tower defense": "Strategy", "metroidvania": "Platformer",
    "souls-like": "Action", "rhythm": "Music & Rhythm", "word game": "Word & Trivia",
    "mmorpg": "MMO", "jrpg": "RPG", "crpg": "RPG", "action rpg": "RPG", "interactive fiction": "Visual Novel",
    "dating sim": "Visual Novel", "open world survival craft": "Survival",
    # itch.io genre slugs (already human words after the source parses them)
    "card-game": "Card & Board", "interactive-fiction": "Visual Novel", "visual-novel": "Visual Novel",
}

# (sub-genre, regex, implied primary genre or None)
SUBGENRES = [
    ("Match-3", r"match[- ]?3|match three", "Puzzle"),
    ("Merge", r"\bmerg(e|ing)\b", "Puzzle"),
    ("Hidden Object", r"hidden[- ]object", "Puzzle"),
    ("Sort & Organise", r"\b(sort|sorting|organi[sz]e)\b puzzle|water sort|ball sort", "Puzzle"),
    ("Runner", r"\b(endless )?runner\b", "Arcade"),
    ("Hyper-casual", r"hyper[- ]?casual|one[- ]tap", "Arcade"),
    ("Hybrid-casual", r"hybrid[- ]?casual", "Casual"),
    (".io", r"\w\.io\b", "Arcade"),
    ("Tower Defense", r"tower[- ]defen[cs]e", "Strategy"),
    ("Auto-battler", r"auto[- ]?(battler|chess)", "Strategy"),
    ("4X", r"\b4x\b", "Strategy"),
    ("RTS", r"real[- ]time strategy|\brts\b", "Strategy"),
    ("Survivors-like", r"survivors?[- ]like|bullet heaven|horde survival", "Roguelike"),
    ("Deckbuilder", r"deck[- ]?build", "Card & Board"),
    ("Roguelite", r"rogue[- ]?(like|lite)", "Roguelike"),
    ("Idle", r"\b(idle|incremental|clicker|afk)\b", "Idle & Incremental"),
    ("Tycoon", r"tycoon|business sim|management sim", "Simulation"),
    ("Cozy & Farming", r"\bcozy\b|\bfarming\b|farm sim|life sim", "Simulation"),
    ("City Builder", r"city[- ]?build|colony sim", "Simulation"),
    ("Gacha / Hero Collector", r"\bgacha\b|hero[- ]collect", "RPG"),
    ("Squad / Idle RPG", r"squad rpg|idle rpg|squad[- ]based rpg", "RPG"),
    ("Metroidvania", r"metroidvania", "Platformer"),
    ("Soulslike", r"souls[- ]?like", "Action"),
    ("Battle Royale", r"battle royale", "Shooter"),
    ("Bullet Hell / Shmup", r"bullet hell|\bshmup\b|shoot ?'?em ?up", "Shooter"),
    ("Physics", r"physics[- ]based|ragdoll", None),
    ("Party", r"party game", "Casual"),
    ("PvP", r"\bpvp\b", None),
    ("Co-op", r"\bco-?op\b", None),
    ("Open World", r"open[- ]world", None),
]
_SUB_RE = [(name, re.compile(rx, re.I), implied) for name, rx, implied in SUBGENRES]
# These are noisy in free-text descriptions ("never sit idle"), so only trust them in
# titles, tags and genres.
_DESCRIPTION_UNSAFE = {"Idle", "Runner", "Co-op", "PvP", "Party", "Cozy & Farming"}


def _map(term):
    return RAW_MAP.get((term or "").strip().lower(), "__unknown__")


def classify(game, max_tags: int = 8):
    """Sets game.genre and game.subgenres in place and returns the game."""
    strong_text = " | ".join([game.title or ""] + list(game.tags) + list(game.raw_genres))
    desc = (game.description or "")[:1200]

    subs, implied = [], []
    for name, rx, imp in _SUB_RE:
        if rx.search(strong_text):
            subs.append(name)
            if imp:
                implied.append(imp)
        elif name not in _DESCRIPTION_UNSAFE and rx.search(desc):
            subs.append(name)

    candidates = []
    for term in list(game.raw_genres) + list(game.tags)[:max_tags]:
        g = _map(term)
        if g and g != "__unknown__":
            candidates.append(g)
    candidates += implied

    game.genre = min(candidates, key=lambda g: PRIORITY[g]) if candidates else "Other"
    game.subgenres = subs
    return game


# ---------------------------------------------------------------- platforms
_PLATFORM_MAP = {
    "pc (microsoft windows)": "PC", "windows": "PC", "pc": "PC", "mac": "Mac", "macos": "Mac",
    "osx": "Mac", "linux": "Linux", "ios": "iOS", "android": "Android",
    "playstation 5": "PS5", "playstation 4": "PS4", "xbox series x|s": "Xbox Series",
    "xbox one": "Xbox One", "nintendo switch": "Switch", "nintendo switch 2": "Switch 2",
    "web browser": "Web", "html5": "Web", "web": "Web", "html": "Web",
}


def norm_platform(name: str) -> str:
    n = (name or "").strip()
    low = n.lower()
    if low in _PLATFORM_MAP:
        return _PLATFORM_MAP[low]
    if "vr" in low.split() or "quest" in low or low.endswith(" vr") or "visionos" in low:
        return "VR"
    return n


def platform_family(p: str) -> str:
    if p in ("PC", "Mac", "Linux"):
        return "PC"
    if p.startswith(("PS", "Xbox", "Switch")) or "playstation" in p.lower():
        return "Console"
    if p in ("iOS", "Android", "Web", "VR"):
        return p
    return "Other"


FAMILIES = ["PC", "Console", "iOS", "Android", "Web", "VR", "Other"]
