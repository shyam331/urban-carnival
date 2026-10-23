"""ZIP (ZCTA) boundaries joined to Overture county / city / neighborhood names and footprint stats."""
import geopandas as gpd
import pandas as pd
import shapely

from . import config as C
from .util import download

FT_CRS = C.EQUAL_AREA_CRS


def load_zcta(data_dir=None):
    """Return (GeoDataFrame[zip, geometry] in EPSG:4326, source_url). Tries ZCTA_URLS in order."""
    d = (data_dir or C.DATA_DIR) / "zcta"
    errors = []
    for url in C.ZCTA_URLS:
        dest = d / url.rsplit("/", 1)[-1]
        try:
            download(url, dest, timeout=300)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url}: {e}")
            continue
        g = gpd.read_file(dest)
        zcol = next(c for c in g.columns if c.upper().startswith("ZCTA5CE"))
        g = g.rename(columns={zcol: "zip"})[["zip", "geometry"]].to_crs(4326)
        g = g[g.zip.str.match(r"^9[0-6]\d{3}$")]  # California ZCTAs
        return g.reset_index(drop=True), url, errors
    raise RuntimeError("No ZCTA source reachable: " + "; ".join(errors))


def _largest_overlap(left, right, name_col, out_col):
    """For each left polygon pick the right polygon's name with the largest intersection area."""
    l = left[["zip", "geometry"]].to_crs(FT_CRS)
    r = right[[name_col, "geometry"]].to_crs(FT_CRS)
    ov = gpd.overlay(l, r, how="intersection", keep_geom_type=True)
    ov["a"] = ov.area
    best = ov.sort_values("a", ascending=False).drop_duplicates("zip")
    share = best.set_index("zip").a / l.set_index("zip").area
    return best.set_index("zip")[name_col].rename(out_col), share.rename(out_col + "_share")


def zip_places(zcta, data_dir=None):
    d = (data_dir or C.DATA_DIR) / "overture"
    areas = _read_geo(d / "division_area_ca.parquet")
    pts = _read_geo(d / "division_ca.parquet")
    counties = areas[(areas.subtype == "county") & (areas["class"] == "land")]
    if counties.empty:
        counties = areas[areas.subtype == "county"]
    counties = counties.assign(county=counties.name.str.replace(r"\s+County$", "", regex=True))
    localities = areas[(areas.subtype == "locality") & (areas["class"] == "land")]
    if localities.empty:
        localities = areas[areas.subtype == "locality"]

    county, cshare = _largest_overlap(zcta, counties, "county", "county")
    city, lshare = _largest_overlap(zcta, localities, "name", "city")
    out = zcta[["zip"]].set_index("zip").join([county, cshare, city, lshare])

    # ZIPs outside every locality polygon: nearest locality point
    loc_pts = pts[pts.subtype == "locality"].to_crs(FT_CRS)
    cent = zcta.to_crs(FT_CRS).set_index("zip").representative_point()
    near = gpd.sjoin_nearest(gpd.GeoDataFrame(geometry=cent), loc_pts[["name", "geometry"]], how="left")
    near = near[~near.index.duplicated()]
    need = out.city.isna()
    out["city_source"] = "locality polygon (largest overlap)"
    out.loc[need, "city"] = near.loc[need[need].index, "name"]
    out.loc[need, "city_source"] = "nearest locality point (no locality polygon overlaps)"

    # Postal city: the city most Overture address points in the ZIP are mailed to.
    # Applied later (apply_postal_city) once footprint counts tell us address coverage.
    pc_path = d / "postal_cities_ca.parquet"
    if pc_path.exists():
        pcs = pd.read_parquet(pc_path)
        tot = pcs.groupby("zip").n.transform("sum")
        pcs = pcs.assign(share=pcs.n / tot).sort_values(["zip", "n"], ascending=[True, False])
        top = pcs.drop_duplicates("zip").set_index("zip")
        out["postal_city"] = top.postal_city
        out["postal_city_share"] = top.share
        out["address_points"] = pcs.groupby("zip").n.sum()
        out["postal_cities"] = pcs[pcs.share >= 0.10].groupby("zip").postal_city.apply(lambda s: "; ".join(s))

    # Neighborhoods: neighborhood / macrohood / microhood points inside each ZCTA
    hoods = pts[pts.subtype.isin(["macrohood", "neighborhood", "microhood"])][["name", "subtype", "geometry"]]
    hj = gpd.sjoin(hoods, zcta[["zip", "geometry"]], predicate="within")
    order = {"macrohood": 0, "neighborhood": 1, "microhood": 2}
    hj["o"] = hj.subtype.map(order)
    hj = hj.sort_values(["zip", "o", "name"]).drop_duplicates(["zip", "name"])
    nb = hj.groupby("zip").name.apply(lambda s: "; ".join(s)).rename("neighborhoods")
    out = out.join(nb)
    return out.reset_index(), hj[["zip", "name", "subtype"]].rename(columns={"name": "neighborhood"})


def apply_postal_city(z, min_coverage=0.30, min_share=0.5):
    """Use the postal city only where Overture address points are dense enough to trust.

    Coverage = address points / house-scale building footprints in the ZIP. Overture's
    address coverage is uneven (e.g. Alameda County has almost none), so sparse ZIPs keep
    the locality-polygon name.
    """
    z = z.copy()
    z["locality"] = z.city
    cov = z.address_points / z.footprints_house_scale
    ok = z.postal_city.notna() & (cov >= min_coverage) & (z.postal_city_share >= min_share)
    z.loc[ok, "city"] = z.postal_city
    z.loc[ok, "city_source"] = ("postal city of " + (z.postal_city_share[ok] * 100).round().astype(int).astype(str)
                                + "% of address points")
    z.loc[~ok, "postal_cities"] = None  # too sparse to list
    return z


def _read_geo(path):
    df = pd.read_parquet(path)
    return gpd.GeoDataFrame(df.drop(columns=["geometry"]), geometry=shapely.from_wkb(df.geometry), crs=4326)


def footprint_stats(zcta, data_dir=None, batch=400_000):
    """Per-ZIP building-footprint counts and median footprint (sq ft) from the Overture CA extract.

    Streams each file in batches to bound memory; result cached to footprint_stats.parquet.
    """
    import pyarrow.parquet as pq

    base = (data_dir or C.DATA_DIR) / "overture"
    cache = base / "footprint_stats.parquet"
    if cache.exists():
        s = pd.read_parquet(cache)
        return s, int(s.footprints_total.sum())
    zc = zcta[["zip", "geometry"]]
    parts = []
    for f in sorted((base / "buildings").glob("buildings_*.parquet")):
        pf = pq.ParquetFile(f)
        if "geometry" not in pf.schema_arrow.names:
            continue
        for b in pf.iter_batches(batch_size=batch, columns=["geometry", "source_dataset"]):
            geom = shapely.from_wkb(b.column("geometry").to_numpy(zero_copy_only=False))
            g = gpd.GeoSeries(geom, crs=4326)
            area = (g.to_crs(FT_CRS).area * C.SQFT_PER_SQM).astype("float32").values
            pts = gpd.GeoDataFrame({"area_sqft": area, "src": b.column("source_dataset").to_pylist()},
                                   geometry=shapely.centroid(geom), crs=4326)
            j = gpd.sjoin(pts, zc, predicate="within", how="inner")
            parts.append(pd.DataFrame({"zip": j.zip.values, "area_sqft": j.area_sqft.values,
                                       "microsoft": j.src.fillna("").str.contains("Microsoft", case=False).values}))
            del geom, g, pts, j
    if not parts:
        return pd.DataFrame(columns=["zip"]), 0
    b = pd.concat(parts, ignore_index=True)
    b["house_scale"] = b.area_sqft.between(600, 6000)
    s = b.groupby("zip").agg(
        footprints_total=("area_sqft", "size"),
        footprints_house_scale=("house_scale", "sum"),
        footprints_microsoft=("microsoft", "sum"),
        median_footprint_sqft=("area_sqft", "median"),
    )
    s["median_house_scale_footprint_sqft"] = b[b.house_scale].groupby("zip").area_sqft.median()
    s = s.reset_index()
    s.to_parquet(cache)
    return s, int(s.footprints_total.sum())
