"""Address-level footprint table for every mailable ZIP.

For each Overture address point inside a ranked ZIP, find the building footprint that
contains it and report the footprint (ground-floor, not interior floor area) in sq ft.

NOT available without parcel data: lot size (-> "no data"), zoning. "Residential" here is
Overture's own building class / subtype, which is null for most buildings; it is reported
as evidence, never as zoning. Rows are NOT dropped for unknown class.

    python -m adu_campaign.addresses fetch   # download CA address points (S3)
    python -m adu_campaign.addresses build   # join to footprints -> output/addresses/*.xlsx
"""
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import shapely
import xlsxwriter

from . import config as C
from . import fetch_overture as F
from . import geo

NON_RES_CLASSES = {
    "commercial", "retail", "industrial", "school", "office", "warehouse", "hospital", "church", "civic",
    "public", "hotel", "university", "college", "kindergarten", "supermarket", "service", "transportation",
    "train_station", "government", "fire_station", "religious", "cathedral", "chapel", "mosque", "synagogue",
    "temple", "stadium", "parking", "manufacture", "hangar", "barn", "stable", "greenhouse", "farm_auxiliary",
    "shed", "garage", "garages", "carport", "roof", "cabin_outbuilding", "outbuilding", "kiosk", "toilets",
}
RES_CLASSES = {"house", "detached", "residential", "apartments", "terrace", "semidetached_house", "bungalow",
               "dormitory", "duplex", "static_caravan", "houseboat", "cabin"}
ADDR_DIR = "addresses"


def fetch(out_dir):
    """All CA address points (id, number, street, unit, postcode, postal_city, lon, lat)."""
    fs = F.s3()
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = ["id", "number", "street", "unit", "postcode", "postal_city", "address_levels", "country", "geometry", "bbox"]
    for k, path in enumerate(F.theme_files(fs, "addresses", "address")):
        dest = out_dir / f"addr_{k:03d}.parquet"
        if dest.exists():
            continue
        pf = pq.ParquetFile(path, filesystem=fs)
        rgs = F.matching_row_groups(pf)
        parts = []
        for rg in rgs:
            t = F._in_bbox(pf.read_row_group(rg, columns=cols))
            t = t.filter(pc.equal(t.column("country"), "US"))
            if not t.num_rows:
                continue
            ca = [bool(lv) and lv[0].get("value") == "CA" for lv in t.column("address_levels").to_pylist()]
            t = t.filter(pa.array(ca))
            if t.num_rows:
                parts.append(t.drop_columns(["address_levels", "country", "bbox"]))
        if parts:
            pq.write_table(pa.concat_tables(parts), dest, compression="zstd")
        print(f"addr file {k}: {sum(p.num_rows for p in parts)} CA rows", flush=True)


def load_addresses(data_dir, zcta, mailable):
    base = data_dir / "overture" / ADDR_DIR
    frames = []
    for f in sorted(base.glob("addr_*.parquet")):
        t = pq.read_table(f).to_pandas()
        g = shapely.from_wkb(t.geometry.values)
        t["lon"], t["lat"] = shapely.get_x(g), shapely.get_y(g)
        frames.append(t.drop(columns=["geometry"]))
    a = pd.concat(frames, ignore_index=True)
    a = a[a.number.notna() & a.street.notna()]
    pts = gpd.GeoDataFrame(a, geometry=gpd.points_from_xy(a.lon, a.lat), crs=4326)
    z = zcta[zcta.zip.isin(mailable)][["zip", "geometry"]]
    j = gpd.sjoin(pts, z, predicate="within", how="inner").drop(columns="index_right")
    j = j[~j.index.duplicated()]
    key = ["number", "street", "unit", "zip"]
    j["unit"] = j.unit.fillna("")
    return j.drop_duplicates(key).reset_index(drop=True)


def match_buildings(addr, data_dir, chunk=1_000_000):
    """Add footprint_sqft / building class / building id to each address (containing footprint).

    Each building file is read in row-group batches so peak memory stays bounded; a building
    can straddle batches only by its own row group, so every polygon is tested exactly once.
    """
    addr = addr.copy()
    n = len(addr)
    fp = np.full(n, np.nan)
    bid = np.empty(n, dtype=object)
    bcl = np.empty(n, dtype=object)
    bst = np.empty(n, dtype=object)
    x, y = addr.lon.values, addr.lat.values
    done = np.zeros(n, dtype=bool)
    for f in sorted((data_dir / "overture" / "buildings").glob("buildings_*.parquet")):
        pf = pq.ParquetFile(f)
        if pf.metadata.num_rows == 0 or "geometry" not in pf.schema_arrow.names:
            continue
        hits = 0
        for batch in pf.iter_batches(batch_size=250_000, columns=["id", "geometry", "class", "subtype", "bbox"]):
            bb = batch.column("bbox")
            xmin = pc.min(pc.struct_field(bb, "xmin")).as_py(); xmax = pc.max(pc.struct_field(bb, "xmax")).as_py()
            ymin = pc.min(pc.struct_field(bb, "ymin")).as_py(); ymax = pc.max(pc.struct_field(bb, "ymax")).as_py()
            sel = np.where(~done & (x >= xmin) & (x <= xmax) & (y >= ymin) & (y <= ymax))[0]
            if not len(sel):
                continue
            geoms = shapely.from_wkb(batch.column("geometry").to_numpy(zero_copy_only=False))
            tree = shapely.STRtree(geoms)
            pi, bi = tree.query(shapely.points(x[sel], y[sel]), predicate="within")
            if not len(pi):
                continue
            first = pd.Series(bi, index=pi).groupby(level=0).first()
            rows = sel[first.index.values]
            b = first.values
            area = (gpd.GeoSeries(geoms[b], crs=4326).to_crs(C.EQUAL_AREA_CRS).area * C.SQFT_PER_SQM).values
            fp[rows] = area
            bid[rows] = np.asarray(batch.column("id").to_pylist(), dtype=object)[b]
            bcl[rows] = np.asarray(batch.column("class").to_pylist(), dtype=object)[b]
            bst[rows] = np.asarray(batch.column("subtype").to_pylist(), dtype=object)[b]
            done[rows] = True
            hits += len(rows)
            del geoms, tree
        print(f"  {f.name}: +{hits} matched (total {int(done.sum()):,} of {n:,})", flush=True)
    addr["footprint_sqft"], addr["building_id"], addr["building_class"], addr["building_subtype"] = fp, bid, bcl, bst
    return addr


def residential_evidence(df):
    cls = df.building_class.fillna("")
    sub = df.building_subtype.fillna("")
    out = np.where(df.footprint_sqft.isna(), "no footprint at address point",
          np.where(cls.isin(NON_RES_CLASSES) | sub.isin({"outbuilding", "commercial", "industrial", "education",
                                                         "medical", "civic", "agricultural", "service"}),
                   "non-residential / outbuilding class",
          np.where(cls.isin(RES_CLASSES) | (sub == "residential"), "Overture class: residential",
                   "class not tagged (unknown)")))
    return out


def _s(v):
    return v if isinstance(v, str) else ""


def write_xlsx(df, path, title):
    wb = xlsxwriter.Workbook(path, {"constant_memory": True, "strings_to_numbers": False})
    ws = wb.add_worksheet("Addresses")
    hdr = wb.add_format({"bold": True, "font_name": "Arial", "bg_color": "#1F3864", "font_color": "#FFFFFF",
                         "text_wrap": True, "valign": "top"})
    base = wb.add_format({"font_name": "Arial"})
    num = wb.add_format({"font_name": "Arial", "num_format": "#,##0"})
    pct = wb.add_format({"font_name": "Arial", "num_format": "0.0%"})
    heads = ["Address", "City", "ZIP", "Neighborhood", "ZIP tier", "Residential evidence (Overture building class; NOT zoning)",
             "Existing structure footprint (sq ft, ground floor)", "Lot size (sq ft)",
             "% of lot built (footprint / lot)", "Footprint-scale flag (600-6,000 sq ft)", "Building class", "Building ID"]
    widths = [34, 18, 7, 24, 18, 34, 18, 12, 14, 18, 14, 38]
    for j, (h, w) in enumerate(zip(heads, widths)):
        ws.write(0, j, h, hdr)
        ws.set_column(j, j, w)
    ws.set_row(0, 48)
    ws.freeze_panes(1, 1)
    for i, r in enumerate(df.itertuples(index=False), 1):
        ws.write_string(i, 0, r.address, base)
        ws.write_string(i, 1, _s(r.city), base)
        ws.write_string(i, 2, r.zip, base)
        ws.write_string(i, 3, _s(r.neighborhood), base)
        ws.write_string(i, 4, r.tier, base)
        ws.write_string(i, 5, r.res_evidence, base)
        if pd.notna(r.footprint_sqft):
            ws.write_number(i, 6, round(r.footprint_sqft, 1), num)
        else:
            ws.write_string(i, 6, "no data", base)
        ws.write_string(i, 7, "no data", base)  # lot size: needs parcel data
        ws.write_formula(i, 8, f'=IF(AND(ISNUMBER(G{i + 1}),ISNUMBER(H{i + 1})),G{i + 1}/H{i + 1},"no data")', pct)
        ws.write_string(i, 9, r.scale_flag, base)
        ws.write_string(i, 10, _s(r.building_class), base)
        ws.write_string(i, 11, _s(r.building_id), base)
    ws.autofilter(0, 0, len(df), len(heads) - 1)
    note = wb.add_worksheet("Read me")
    for k, line in enumerate([
        title,
        "Footprint = ground-floor area of the Overture/Microsoft building polygon containing the address point (not interior floor area).",
        "Lot size = 'no data': no county parcel data could be downloaded (see methodology.md). Paste/merge lot sizes into column H and column I recalculates.",
        "Residential evidence is Overture's own building class. It is NOT zoning. 'class not tagged' = most buildings; kept, not excluded.",
        "Several addresses (units) can share one building; the footprint is then the whole building, not per unit.",
        "A detached garage / ADU / shed on the same lot is a separate building and is NOT added to the main house footprint.",
    ]):
        note.write(k, 0, line, base)
    note.set_column(0, 0, 150)
    wb.close()


def build(data_dir=None, out_dir=None, max_rows=1_000_000):
    data_dir = data_dir or C.DATA_DIR
    out_dir = out_dir or (C.OUTPUT_DIR / "addresses")
    out_dir.mkdir(parents=True, exist_ok=True)
    z = pd.read_csv(C.OUTPUT_DIR / "all_zips.csv", dtype={"zip": str})
    z = z[z["rank"].notna()]
    zcta, _, _ = geo.load_zcta(data_dir)
    hoods = _neighborhood_polys(data_dir)
    print(f"{len(z)} mailable ZIPs")
    addr = load_addresses(data_dir, zcta, set(z.zip))
    print(f"{len(addr):,} unique addresses in mailable ZIPs")
    addr = match_buildings(addr, data_dir)
    addr["neighborhood"] = _assign_neighborhood(addr, hoods, z)
    m = z.set_index("zip")
    addr["city"] = addr.zip.map(m.city)
    addr["tier"] = addr.zip.map(m.tier_label)
    addr["county"] = addr.zip.map(m.county)
    addr["region"] = addr.zip.map(m.focus_region)
    addr["address"] = (addr.number.astype(str) + " " + addr.street.astype(str) +
                       np.where(addr.unit != "", " #" + addr.unit.astype(str), ""))
    addr["res_evidence"] = residential_evidence(addr)
    addr["scale_flag"] = np.where(addr.footprint_sqft.between(600, 6000), "house-scale", "")
    addr["rank"] = addr.zip.map(m["rank"])
    addr = addr.sort_values(["rank", "street", "number"]).reset_index(drop=True)
    cols = ["address", "city", "zip", "neighborhood", "tier", "res_evidence", "footprint_sqft", "scale_flag",
            "building_class", "building_id", "county", "region", "rank"]
    addr[cols].to_parquet(out_dir / "addresses_all.parquet")
    files = write_all(addr[cols], out_dir, max_rows)
    idx = pd.DataFrame(files, columns=["file", "region", "addresses", "zips"])
    idx.to_csv(out_dir / "index.csv", index=False)
    stats = {
        "addresses": len(addr),
        "with_footprint": int(addr.footprint_sqft.notna().sum()),
        "residential_tagged": int((addr.res_evidence == "Overture class: residential").sum()),
        "non_residential": int((addr.res_evidence == "non-residential / outbuilding class").sum()),
    }
    print(stats)
    return idx, stats


def write_all(addr, out_dir, max_rows=1_000_000):
    files = []
    for region, g in addr.groupby("region", sort=False):
        n = int(np.ceil(len(g) / max_rows))
        bounds = np.linspace(0, len(g), n + 1).astype(int)
        for p in range(n):
            chunk = g.iloc[bounds[p]:bounds[p + 1]]
            slug = region.split(" (")[0].replace(" / ", "_").replace(" ", "_").replace("&", "and")
            name = f"addresses_{slug}{'' if n == 1 else f'_part{p + 1}'}.xlsx"
            write_xlsx(chunk, out_dir / name, f"{region}: {len(chunk):,} addresses ({chunk.zip.nunique()} ZIPs)")
            files.append((name, region, len(chunk), chunk.zip.nunique()))
            print("wrote", name, len(chunk), flush=True)
    return files


def _neighborhood_polys(data_dir):
    d = data_dir / "overture" / "division_area_ca.parquet"
    a = geo._read_geo(d)
    h = a[a.subtype.isin(["neighborhood", "macrohood", "microhood"])][["name", "subtype", "geometry"]]
    return h


def _assign_neighborhood(addr, hoods, z):
    """Smallest neighborhood polygon containing the address; else blank."""
    order = {"microhood": 0, "neighborhood": 1, "macrohood": 2}
    h = hoods.assign(o=hoods.subtype.map(order)).sort_values("o")
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(addr.lon, addr.lat), crs=4326)
    j = gpd.sjoin(pts, h[["name", "o", "geometry"]], predicate="within", how="left")
    j = j.sort_values("o").loc[~j.sort_values("o").index.duplicated()].sort_index()
    return j.name.reindex(range(len(addr))).values


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "write":  # re-write Excel files from the cached matched table
        od = C.OUTPUT_DIR / "addresses"
        a = pd.read_parquet(od / "addresses_all.parquet")
        pd.DataFrame(write_all(a, od), columns=["file", "region", "addresses", "zips"]).to_csv(od / "index.csv", index=False)
    elif cmd == "fetch":
        fetch(C.DATA_DIR / "overture" / ADDR_DIR)
    else:
        build()
