"""Redfin Data Center ZIP market tracker -> trailing-12-month ZIP market table for California."""
import pandas as pd

from . import config as C
from .util import download

RAW = "zip_code_market_tracker.tsv000.gz"
CA_PARQUET = "redfin_zip_ca.parquet"


def load_ca(data_dir=None):
    d = (data_dir or C.DATA_DIR) / "redfin"
    pq_path = d / CA_PARQUET
    if not pq_path.exists():
        raw = download(C.REDFIN_ZIP_TRACKER_URL, d / RAW)
        parts = [ch[ch.STATE_CODE == "CA"] for ch in pd.read_csv(raw, sep="\t", chunksize=500_000, low_memory=False)]
        pd.concat(parts).to_parquet(pq_path)
    return pd.read_parquet(pq_path)


def trailing_windows(df):
    """Latest PERIOD_END and the non-overlapping 90-day windows that tile the trailing year."""
    ends = sorted(pd.to_datetime(df.PERIOD_END.unique()))
    latest = ends[-1]
    n = C.TRAILING_MONTHS // 3
    wanted = [(latest - pd.DateOffset(months=3 * i)) + pd.offsets.MonthEnd(0) for i in range(n)]
    return [w.strftime("%Y-%m-%d") for w in wanted]


def _agg(g):
    w = g.HOMES_SOLD.fillna(0)
    ok = g.MEDIAN_PPSF.notna() & (w > 0)
    def wavg(col):
        m = ok & g[col].notna()
        return (g.loc[m, col] * w[m]).sum() / w[m].sum() if w[m].sum() > 0 else float("nan")
    latest = g.sort_values("PERIOD_END").iloc[-1]
    return pd.Series({
        "median_ppsf_12m": wavg("MEDIAN_PPSF"),
        "median_sale_price_12m": wavg("MEDIAN_SALE_PRICE"),
        "homes_sold_12m": w.sum(),
        "windows_with_data": int(ok.sum()),
        "latest_qtr_ppsf": latest.MEDIAN_PPSF,
        "latest_qtr_ppsf_yoy": latest.MEDIAN_PPSF_YOY,
        "metro": latest.PARENT_METRO_REGION,
    })


def zip_market(df=None):
    df = load_ca() if df is None else df
    wins = trailing_windows(df)
    df = df[df.PERIOD_END.isin(wins) & (df.PERIOD_DURATION == 90)].copy()
    df["zip"] = df.REGION.str.extract(r"(\d{5})")[0]
    out = {}
    for pt, tag in [(C.REDFIN_PROPERTY_TYPE, "sfr"), (C.REDFIN_FALLBACK_PROPERTY_TYPE, "all")]:
        sub = df[df.PROPERTY_TYPE == pt]
        out[tag] = sub.groupby("zip").apply(_agg, include_groups=False).add_prefix(f"{tag}_")
    m = out["sfr"].join(out["all"], how="outer")
    use_sfr = m.sfr_median_ppsf_12m.notna()
    m["ppsf_12m"] = m.sfr_median_ppsf_12m.where(use_sfr, m.all_median_ppsf_12m)
    m["sale_price_12m"] = m.sfr_median_sale_price_12m.where(use_sfr, m.all_median_sale_price_12m)
    m["homes_sold_12m"] = m.sfr_homes_sold_12m.where(use_sfr, m.all_homes_sold_12m)
    m["ppsf_basis"] = use_sfr.map({True: "SFR", False: "All Residential (SFR missing)"})
    m["metro"] = m.sfr_metro.where(use_sfr, m.all_metro)
    m["thin_sample"] = m.homes_sold_12m < C.MIN_HOMES_SOLD_12M
    m["tier"], m["tier_label"], m["tier_weight"] = assign_tiers(m.ppsf_12m)
    meta = {"windows": wins, "last_updated": df.LAST_UPDATED.max(), "latest_period_end": max(wins)}
    return m.reset_index(), meta


def assign_tiers(ppsf):
    tier = pd.Series(pd.NA, index=ppsf.index, dtype="Int64")
    label = pd.Series("Below $%d/sf" % C.PRICE_TIERS[-1]["min_ppsf"], index=ppsf.index, dtype=object)
    weight = pd.Series(0, index=ppsf.index)
    for t in reversed(C.PRICE_TIERS):  # low -> high so the highest met floor wins
        hit = ppsf >= t["min_ppsf"]
        tier[hit], label[hit], weight[hit] = t["tier"], t["label"], t["weight"]
    label[ppsf.isna()] = "No Redfin data"
    return tier, label, weight
