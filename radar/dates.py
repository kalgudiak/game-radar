from datetime import date, datetime, timezone

_FORMATS = [
    "%d %b, %Y", "%b %d, %Y", "%d %B, %Y", "%B %d, %Y", "%d %b %Y", "%B %d %Y",
    "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d %H:%M:%S",
]


def parse_date(v):
    """Best-effort parse of the date formats the stores use. Returns date or None.
    Month-only or 'Coming soon' style values return None on purpose."""
    if v is None or v == "":
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc).date()
    s = str(v).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for f in _FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None
