import logging

log = logging.getLogger("radar")


class SourceUnavailable(Exception):
    """Raised when a source can't run (missing credentials or library). Logged, not fatal."""


class Source:
    name = ""

    def __init__(self, http, cfg: dict):
        self.http = http
        self.cfg = cfg or {}
        self.skip: set = set()   # source_ids already stored or known to be old: never re-detailed

    def fetch(self, start, end):
        """Yield Game objects for titles that look released in [start, end].
        The pipeline does the final date filtering, so yielding a few extras is fine."""
        raise NotImplementedError

    def refresh(self, ids):
        """Optional: yield Game objects carrying fresh metrics (rating, rating_count,
        installs, price) for already-stored ids, used for daily snapshots."""
        return iter(())


def chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]
