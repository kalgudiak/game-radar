import logging
import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("radar")

# Seconds between requests to the same host. Conservative on purpose:
# Steam appdetails tolerates ~200 calls / 5 min, Apple's iTunes endpoints ~20/min.
HOST_INTERVALS = {
    "store.steampowered.com": 1.6,
    "steamspy.com": 1.0,
    "itunes.apple.com": 3.1,
    "api.igdb.com": 0.3,
    "itch.io": 1.5,
    "www.appbrain.com": 6.0,   # AppBrain answers 429 after ~20 fast requests
    "play.google.com": 0.7,
}


# Lighter endpoints on the same hosts can go faster than the host default.
PATH_INTERVALS = [
    ("store.steampowered.com", "/appreviews/", 0.4),   # review summaries: far more lenient than appdetails
    ("itunes.apple.com", "/rss/", 1.0),                # chart feeds: CDN-served, unlike the Lookup API
]


class Http:
    def __init__(self, user_agent: str, default_interval: float = 1.0, timeout: int = 30):
        s = requests.Session()
        retry = Retry(total=5, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(["GET", "POST"]), respect_retry_after_header=True)
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://", HTTPAdapter(max_retries=retry))
        s.headers["User-Agent"] = user_agent
        self.s, self.timeout, self.default_interval = s, timeout, default_interval
        self._last = {}

    def _throttle(self, url):
        u = urlparse(url)
        key, gap = u.netloc, HOST_INTERVALS.get(u.netloc, self.default_interval)
        for host, fragment, interval in PATH_INTERVALS:
            if u.netloc == host and fragment in u.path:
                key, gap = host + fragment, interval
                break
        wait = gap - (time.monotonic() - self._last.get(key, 0.0))
        if wait > 0:
            time.sleep(wait)
        self._last[key] = time.monotonic()

    def get(self, url, **kw):
        self._throttle(url)
        r = self.s.get(url, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r

    def post(self, url, **kw):
        self._throttle(url)
        r = self.s.post(url, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r
