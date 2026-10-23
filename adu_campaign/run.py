"""End-to-end pipeline: python -m adu_campaign.run [--skip-footprints]

1. Source inventory (live probe of every URL)
2. Redfin trailing-12-month ZIP market table + $/sf tiers
3. ZCTA boundaries -> county / city / neighborhoods; Overture footprint stats per ZIP
4. Parcels (every county whose source is reachable or provided locally): SFR filter,
   lot >= MIN_LOT_SQFT, footprint join, buildable area
5. ZIP aggregation, ranking, workbook + inventory
"""
import argparse
import json
import warnings

import pandas as pd

from . import config as C
from . import geo, parcels, redfin, zillow
from .county_sources import (ALL_COUNTIES, COUNTY_SOURCES, NO_FREE_SOURCE, OTHER_COUNTY_NOTES,
                             STATEWIDE_SOURCES)
from .util import probe
from .workbook import write_workbook

warnings.filterwarnings("ignore", category=UserWarning)


def source_inventory(meta):
    rows = []

    def add(county, source, url, vintage, lot_field, use_field, sfr_rule, coverage, notes, live=None):
        if live is None:
            if url and url.startswith("http"):
                ok, detail, lm = probe(url)
                live = ("LIVE" if ok else "UNREACHABLE") + f" ({detail})"
                if lm and vintage in (None, "", "unverified"):
                    vintage = f"Last-Modified {lm}"
            else:
                live = "no URL"
        rows.append({"county": county, "source": source, "url": url, "status_from_build_env": live,
                     "vintage": vintage, "lot_size_field": lot_field, "use_code_field": use_field,
                     "sfr_rule": sfr_rule, "coverage_pct": coverage, "notes": notes})

    add("Statewide", "Redfin Data Center ZIP market tracker", C.REDFIN_ZIP_TRACKER_URL,
        f"periods to {meta['redfin']['latest_period_end']}; file updated {meta['redfin']['last_updated']}",
        "n/a", "n/a", "n/a", meta["redfin"]["coverage"], "USED: $/sf tiers, sale price, homes sold",
        live="LIVE (downloaded)")
    add("Statewide", "Zillow Research ZHVI (ZIP, single-family)", C.ZILLOW_ZHVI_ZIP_URL, meta["zillow"].get("vintage"),
        "n/a", "n/a", "n/a", meta["zillow"].get("coverage", "0%"), meta["zillow"]["note"])
    for u in C.ZCTA_URLS:
        used = u == meta["zcta"]["url"]
        add("Statewide", "Census ZCTA boundaries" + (" (USED - 2010 TIGER ZCTA mirror)" if used else " (2024 TIGER, preferred)"),
            u, "2010 ZCTA vintage" if used else "2024", "n/a", "n/a", "n/a",
            f"{meta['zcta']['n']} CA ZCTAs" if used else "0%", "ZIP polygons")
    add("Statewide", "Microsoft US Building Footprints (direct)", C.MICROSOFT_FOOTPRINTS_URL, "", "n/a", "n/a", "n/a", "0%",
        "direct host unreachable; same Microsoft footprints taken via Overture (below)")
    add("Statewide", f"Overture Maps buildings + divisions, release {C.OVERTURE_RELEASE} (AWS S3)",
        f"s3://{C.OVERTURE_BUCKET}/release/{C.OVERTURE_RELEASE}/", C.OVERTURE_RELEASE, "n/a", "n/a", "n/a",
        meta["footprints"]["coverage"], "USED: footprints (incl. Microsoft ML), county / city / neighborhood names",
        live="LIVE (downloaded)")
    for s in STATEWIDE_SOURCES:
        add("Statewide", s["source"], s["url"], s["vintage"], s["lot_size_field"], s["use_code_field"], "", "0%", s["notes"])

    for county in ALL_COUNTIES:
        st = meta["parcels"].get(county, {})
        cov = st.get("coverage", "0% (no data)")
        if county in COUNTY_SOURCES:
            s = COUNTY_SOURCES[county]
            add(county, s["source"], s["url"], s.get("vintage"),
                f"{s.get('lot_size_field') or 'none -> polygon area'} ({s.get('lot_size_units') or 'n/a'})",
                s.get("use_code_field") or "none", s.get("sfr_code_regex") or "unverified / none",
                cov, f"{s.get('restrictions', '')}. Evidence: {s.get('evidence', '')}", live=st.get("status_text"))
        elif county in OTHER_COUNTY_NOTES:
            typ, url, note = OTHER_COUNTY_NOTES[county]
            add(county, f"county parcels ({typ})", url, "unverified", "unverified", "unverified", "unverified",
                cov, note + ". Fallback: Regrid", live=st.get("status_text"))
        else:
            add(county, "none found", None, "", "", "", "", cov,
                "no free parcel source found" + (" (paid/viewer only)" if county in NO_FREE_SOURCE else "") +
                ". Fallback: Regrid", live=st.get("status_text", "no URL"))
    return pd.DataFrame(rows)


def run_parcels(zcta):
    meta, counts = {}, []
    for county in ALL_COUNTIES:
        status, detail, src = parcels.availability(county)
        meta[county] = {"status": status, "status_text": f"{status.upper()} ({detail})"}
        if src is None:
            continue
        try:
            pr = parcels.evaluate(parcels.load_parcels(county, src), zcta)
        except Exception as e:  # noqa: BLE001
            meta[county]["status_text"] = f"ERROR ({type(e).__name__}: {e})"[:300]
            continue
        z = parcels.zip_counts(pr)
        z["county_parcel_source"] = county
        counts.append(z)
        meta[county].update(status="processed", coverage="100%", n=int(len(pr)))
    return meta, (pd.concat(counts) if counts else pd.DataFrame())


def build(skip_footprints=False):
    C.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {}

    print("[1/5] Redfin")
    rf_raw = redfin.load_ca()
    market, rmeta = redfin.zip_market(rf_raw)
    rmeta["coverage"] = f"{market.zip.nunique()} CA ZIPs with sales in trailing 12 mo"
    meta["redfin"] = rmeta

    print("[2/5] Zillow cross-check")
    zh, zmeta = zillow.load()
    meta["zillow"] = zmeta

    print("[3/5] ZCTA, places, footprints")
    zcta, zurl, _ = geo.load_zcta()
    meta["zcta"] = {"url": zurl, "n": len(zcta)}
    places, hoods = geo.zip_places(zcta)
    if skip_footprints:
        fps, nfp = pd.DataFrame(columns=["zip"]), 0
    else:
        fps, nfp = geo.footprint_stats(zcta)
    meta["footprints"] = {"coverage": f"{nfp:,} CA footprints assigned to ZIPs", "n": nfp}

    print("[4/5] Parcels")
    pmeta, pcounts = run_parcels(zcta)
    meta["parcels"] = pmeta

    print("[5/5] Aggregate + rank")
    allz = pd.DataFrame({"zip": sorted(set(zcta.zip) | set(market.zip))})
    z = allz.merge(places, on="zip", how="left").merge(market, on="zip", how="left").merge(fps, on="zip", how="left")
    if not zh.empty:
        z = z.merge(zh, on="zip", how="left")
    if not pcounts.empty:
        z = z.merge(pcounts.groupby("zip", as_index=False).sum(numeric_only=True), on="zip", how="left")
    for c in ["sfr_parcels", "sfr_lot_5k", "pct_lot_5k", "buildable_750", "pct_buildable_750",
              "buildable_1200", "contiguous_under_750_flag", "median_lot_sqft"]:
        if c not in z:
            z[c] = pd.NA
    if "postal_city" in z:
        z = geo.apply_postal_city(z)
    z["has_zcta"] = z.zip.isin(set(zcta.zip))
    z["county"] = z.county.fillna("(no ZCTA: PO-box / unique ZIP)")
    status = {c: m["status"] for c, m in pmeta.items()}
    z["parcel_data"] = z.county.map(lambda c: "processed" if status.get(c) == "processed" else "no data")
    z["tier_weight"] = z.tier_weight.fillna(0)
    z["rank_score"] = (pd.to_numeric(z.buildable_750, errors="coerce") * z.tier_weight).where(z.parcel_data == "processed")
    z["interim_score"] = z.homes_sold_12m.fillna(0) * z.tier_weight
    z["rank_basis"] = z.parcel_data.map({"processed": "qualifying parcels x tier weight",
                                         "no data": "INTERIM: Redfin SFR sales (12 mo) x tier weight"})
    z["score"] = z.rank_score.fillna(z.interim_score)
    # Processed (parcel-based) scores rank ahead of interim proxy scores; never mix the two.
    z["_p"] = (z.parcel_data == "processed").astype(int)
    z = z.sort_values(["_p", "score"], ascending=[False, False]).drop(columns="_p")
    # PO-box / unique ZIPs have Redfin sales (mailing addresses) but no delivery area to saturate.
    tiered = (z.tier_weight > 0) & z.has_zcta
    z["rank"] = pd.NA
    z.loc[tiered, "rank"] = range(1, int(tiered.sum()) + 1)
    region_of = {c: r for r, cs in C.FOCUS_REGIONS.items() for c in cs}
    z["focus_region"] = z.county.map(region_of).fillna("Rest of California").where(z.has_zcta, "(no ZCTA)")
    z["thin_sample"] = z.thin_sample.map({True: "yes", False: ""})

    out = C.OUTPUT_DIR / "campaign_zips.xlsx"
    inv = source_inventory(meta)
    write_workbook(out, z, hoods, inv, meta)
    z.to_csv(C.OUTPUT_DIR / "all_zips.csv", index=False)
    inv.to_csv(C.OUTPUT_DIR / "source_inventory.csv", index=False)
    (C.OUTPUT_DIR / "run_meta.json").write_text(json.dumps(meta, indent=2, default=str))

    print("\nSOURCE INVENTORY")
    with pd.option_context("display.max_colwidth", 60, "display.width", 250):
        print(inv[["county", "source", "status_from_build_env", "vintage", "lot_size_field", "coverage_pct"]].to_string(index=False))
    print("\nZIPs by tier:", z.tier_label.value_counts().to_dict())
    print(f"Wrote {out}")
    return z, inv, meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-footprints", action="store_true")
    build(**vars(ap.parse_args()))
