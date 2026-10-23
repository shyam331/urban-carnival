"""Zillow Research ZHVI (ZIP, single-family, smoothed, seasonally adjusted) for cross-checking Redfin sale prices."""
import pandas as pd

from . import config as C
from .util import download


def load(data_dir=None):
    """Return (DataFrame[zip, zhvi_sfr, zhvi_month, redfin_vs_zhvi later], meta)."""
    dest = (data_dir or C.DATA_DIR) / "zillow" / C.ZILLOW_ZHVI_ZIP_URL.rsplit("/", 1)[-1]
    try:
        download(C.ZILLOW_ZHVI_ZIP_URL, dest, timeout=300)
    except Exception as e:  # noqa: BLE001
        msg = "BLOCKED by this environment's network policy" if "403" in str(e) else str(e)[:120]
        return pd.DataFrame(), {"note": f"NOT USED - {msg}; cross-check pending", "coverage": "0%", "vintage": "unverified"}
    z = pd.read_csv(dest, dtype={"RegionName": str})
    z = z[z.State == "CA"]
    months = [c for c in z.columns if c[:2] in ("19", "20")]
    last = months[-1]
    out = pd.DataFrame({"zip": z.RegionName.str.zfill(5), "zhvi_sfr": z[last]})
    return out, {"note": f"USED for cross-check (ZHVI {last})", "coverage": f"{len(out)} CA ZIPs", "vintage": last}
