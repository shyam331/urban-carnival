import shutil
import urllib.request
from pathlib import Path


def download(url, dest, timeout=120):
    """Download url to dest (skips if present). Raises on HTTP / proxy errors."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=timeout) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    tmp.rename(dest)
    return dest


def probe(url, timeout=20):
    """Return (live: bool, detail: str, last_modified: str|None) for a URL."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "adu-campaign/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"HTTP {r.status}", r.headers.get("Last-Modified")
    except urllib.error.HTTPError as e:
        if e.code in (403, 405) and "Tunnel" not in str(e):
            # some servers reject HEAD; retry a ranged GET
            try:
                g = urllib.request.Request(url, headers={"Range": "bytes=0-0", "User-Agent": "adu-campaign/1.0"})
                with urllib.request.urlopen(g, timeout=timeout) as r:
                    return True, f"HTTP {r.status}", r.headers.get("Last-Modified")
            except Exception as e2:  # noqa: BLE001
                return False, f"{type(e2).__name__}: {e2}"[:160], None
        return False, f"HTTP {e.code}", None
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "Tunnel connection failed: 403" in msg:
            msg = "BLOCKED by this environment's network policy (proxy 403)"
        return False, msg[:160], None
