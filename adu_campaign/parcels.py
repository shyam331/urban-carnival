"""Parcel ingest -> SFR filter -> footprint join -> buildable area -> per-ZIP counts.

Sources come from county_sources.COUNTY_SOURCES. A county is processed only when its
source is reachable (or a local copy exists under DATA_DIR/parcels/); otherwise it is
reported as "no data" -- nothing is imputed.

Local fallback: drop a county file (GeoPackage, GeoParquet, GeoJSON or shapefile zip)
at DATA_DIR/parcels/<county_slug>.<ext>. Regrid county exports are recognised
automatically (fields ll_gissqft / usecode / usedesc / szip).
"""
import json
import urllib.parse
import urllib.request

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq
import shapely

from . import config as C
from .buildable import buildable
from .county_sources import COUNTY_SOURCES, REGRID_SCHEMA
from .util import probe

ACRES_TO_SQFT = 43_560


def slug(county):
    return county.lower().replace(" ", "_")


def local_file(county):
    d = C.DATA_DIR / "parcels"
    for ext in ("parquet", "gpkg", "geojson", "zip", "shp"):
        p = d / f"{slug(county)}.{ext}"
        if p.exists():
            return p
    return None


def availability(county):
    """(status, detail, source dict or None)."""
    lf = local_file(county)
    if lf:
        return "local file", str(lf), {"type": "local", "path": lf}
    src = COUNTY_SOURCES.get(county)
    if not src or not src.get("url"):
        return "no data", ("no automated source configured; place a county or Regrid export at "
                           f"data/parcels/{slug(county)}.gpkg"), None
    if src.get("type") not in ("arcgis", "file"):
        return "no data", (f"'{src.get('type')}' source needs a manual export to "
                           f"data/parcels/{slug(county)}.gpkg"), None
    if not src.get("sfr_code_regex"):
        return "no data", "SFR use-code rule unverified for this source; not processed", None
    live, detail, _ = probe(src["url"] + ("?f=pjson" if src["type"] == "arcgis" else ""))
    return ("live" if live else "no data"), detail, (src if live else None)


def _arcgis_pages(url, where, fields, page=2000):
    offset = 0
    while True:
        q = {"where": where, "outFields": ",".join(fields), "f": "geojson", "outSR": 4326,
             "resultOffset": offset, "resultRecordCount": page, "returnGeometry": "true"}
        with urllib.request.urlopen(f"{url}/query?{urllib.parse.urlencode(q)}", timeout=300) as r:
            fc = json.load(r)
        feats = fc.get("features", [])
        if not feats:
            return
        yield gpd.GeoDataFrame.from_features(feats, crs=4326)
        if len(feats) < page and not fc.get("exceededTransferLimit"):
            return
        offset += len(feats)


def load_parcels(county, src):
    if src["type"] == "local":
        p = src["path"]
        g = gpd.read_parquet(p) if p.suffix == ".parquet" else gpd.read_file(p)
        schema = REGRID_SCHEMA if "ll_gissqft" in g.columns else COUNTY_SOURCES.get(county, {})
        if not schema.get("sfr_code_regex") or not schema.get("use_code_field"):
            raise ValueError(f"{county}: set use_code_field and a verified sfr_code_regex in county_sources.py")
    elif src["type"] == "arcgis":
        fields = [f for f in (src.get("apn_field"), src.get("use_code_field"), src.get("lot_size_field"),
                              src.get("situs_zip_field"), src.get("situs_city_field")) if f]
        g = pd.concat(list(_arcgis_pages(src["url"], src.get("server_where", "1=1"), fields)), ignore_index=True)
        g = gpd.GeoDataFrame(g, crs=4326)
        schema = src
    else:  # direct file
        g = gpd.read_file(src["url"])
        schema = src
    return normalise(g, schema)


def normalise(g, s):
    g = g.to_crs(C.EQUAL_AREA_CRS)
    out = gpd.GeoDataFrame({"apn": g.get(s.get("apn_field"))}, geometry=g.geometry.values, crs=g.crs)
    use = g[s["use_code_field"]].astype(str).str.strip() if s.get("use_code_field") in g else pd.Series("", index=g.index)
    out["use_code"] = use.values
    out["is_sfr"] = use.str.match(s["sfr_code_regex"]).values if s.get("sfr_code_regex") else False
    geom_sqft = g.geometry.area.values * C.SQFT_PER_SQM
    lf = s.get("lot_size_field")
    if lf and lf in g:
        v = pd.to_numeric(g[lf], errors="coerce").values
        v = v * ACRES_TO_SQFT if s.get("lot_size_units") == "acres" else v
        out["lot_sqft"] = np.where(np.isfinite(v) & (v > 0), v, geom_sqft)
        out["lot_size_basis"] = np.where(np.isfinite(v) & (v > 0), "assessor field", "polygon area")
    else:
        out["lot_sqft"], out["lot_size_basis"] = geom_sqft, "polygon area"
    zf = s.get("situs_zip_field")
    out["situs_zip"] = g[zf].astype(str).str.extract(r"(\d{5})")[0].values if zf and zf in g else None
    return out


def footprints_in(bounds_4326):
    """Overture CA footprints whose bbox intersects bounds (xmin, ymin, xmax, ymax)."""
    xmin, ymin, xmax, ymax = bounds_4326
    parts = []
    for f in sorted((C.DATA_DIR / "overture" / "buildings").glob("buildings_*.parquet")):
        t = pq.read_table(f)
        if t.num_rows == 0:
            continue
        b = t.column("bbox")
        m = pc.and_(pc.and_(pc.less_equal(pc.struct_field(b, "xmin"), xmax), pc.greater_equal(pc.struct_field(b, "xmax"), xmin)),
                    pc.and_(pc.less_equal(pc.struct_field(b, "ymin"), ymax), pc.greater_equal(pc.struct_field(b, "ymax"), ymin)))
        t = t.filter(m)
        if t.num_rows:
            parts.append(gpd.GeoDataFrame({"bid": t.column("id").to_pylist()},
                                          geometry=shapely.from_wkb(t.column("geometry").to_numpy(zero_copy_only=False)), crs=4326))
    return pd.concat(parts, ignore_index=True) if parts else gpd.GeoDataFrame({"bid": []}, geometry=[], crs=4326)


def evaluate(parcels, zcta):
    """Apply criteria 1-3 to SFR parcels and return the per-parcel table (sq ft units)."""
    sfr = parcels[parcels.is_sfr].copy()
    sfr["lot_ok"] = sfr.lot_sqft >= C.MIN_LOT_SQFT
    # ZIP: situs ZIP when present, else ZCTA containing the parcel's interior point
    pts = gpd.GeoDataFrame(geometry=sfr.geometry.representative_point(), crs=sfr.crs).to_crs(4326)
    zj = gpd.sjoin(pts, zcta[["zip", "geometry"]], predicate="within", how="left")
    zj = zj[~zj.index.duplicated()]
    sfr["zip"] = sfr.situs_zip.where(sfr.situs_zip.notna(), zj.zip)

    big = sfr[sfr.lot_ok]
    m2ft = C.SQFT_PER_SQM ** 0.5  # metres -> feet
    if len(big):
        fps = footprints_in(big.to_crs(4326).total_bounds).to_crs(C.EQUAL_AREA_CRS)
        fps["fp_area"] = fps.area
        ov = gpd.overlay(big[["geometry"]].reset_index(names="pidx"), fps, how="intersection", keep_geom_type=True)
        ov = ov[ov.area >= C.FOOTPRINT_PARCEL_OVERLAP_MIN * ov.fp_area]
        fp_by_parcel = ov.dissolve("pidx").geometry
        rows = []
        for idx, geom in big.geometry.items():
            fp = fp_by_parcel.get(idx)
            # work in feet so setbacks are in their native unit
            g_ft = shapely.affinity.scale(geom, m2ft, m2ft, origin=(0, 0))
            f_ft = shapely.affinity.scale(fp, m2ft, m2ft, origin=(0, 0)) if fp is not None else None
            rows.append(buildable(g_ft, f_ft))
        res = pd.DataFrame(rows, index=big.index)
        sfr = sfr.join(res)
    sfr["buildable_750"] = sfr.lot_ok & (sfr.get("est_buildable_sqft", 0) >= C.ADU_MIN_BUILDABLE_SQFT)
    sfr["buildable_1200"] = sfr.lot_ok & (sfr.get("est_buildable_sqft", 0) >= C.ADU_LARGE_BUILDABLE_SQFT)
    sfr["contiguous_under_750_flag"] = sfr.buildable_750 & (sfr.get("largest_contiguous_sqft", 0) < C.ADU_MIN_BUILDABLE_SQFT)
    return sfr


def zip_counts(sfr):
    g = sfr.groupby("zip")
    out = pd.DataFrame({
        "sfr_parcels": g.size(),
        "sfr_lot_5k": g.lot_ok.sum(),
        "median_lot_sqft": g.lot_sqft.median(),
        "buildable_750": g.buildable_750.sum(),
        "buildable_1200": g.buildable_1200.sum(),
        "contiguous_under_750_flag": g.contiguous_under_750_flag.sum(),
    })
    out["pct_lot_5k"] = out.sfr_lot_5k / out.sfr_parcels
    out["pct_buildable_750"] = out.buildable_750 / out.sfr_parcels
    return out.reset_index()
