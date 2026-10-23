"""Download California building footprints and division names from Overture Maps (AWS S3).

Overture's building theme redistributes Microsoft ML Building Footprints together with
OSM, Esri and Google footprints. The Microsoft host itself (minedbuildings.z5.web.core.windows.net)
is blocked from this environment, so Overture is the reachable copy. Every footprint keeps
its source dataset so Microsoft-only analysis remains possible.

Only parquet row groups whose bbox statistics intersect CA_BBOX are read.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.fs as pafs
import pyarrow.parquet as pq

from . import config as C


def s3():
    kw = {"anonymous": True, "region": "us-west-2"}
    if os.environ.get("HTTPS_PROXY"):
        kw["proxy_options"] = os.environ["HTTPS_PROXY"]
    return pafs.S3FileSystem(**kw)


def theme_files(fs, theme, typ):
    base = f"{C.OVERTURE_BUCKET}/release/{C.OVERTURE_RELEASE}/theme={theme}/type={typ}"
    return [i.path for i in fs.get_file_info(pafs.FileSelector(base)) if i.path.endswith(".parquet") or "part-" in i.path]


def _bbox_col_index(md, name):
    for j in range(md.num_columns):
        if md.schema.column(j).path == name:
            return j
    raise KeyError(name)


def matching_row_groups(pf, bbox=C.CA_BBOX):
    md = pf.metadata
    ix = {k: _bbox_col_index(md, f"bbox.{k}") for k in ("xmin", "xmax", "ymin", "ymax")}
    out = []
    for i in range(md.num_row_groups):
        rg = md.row_group(i)
        st = {k: rg.column(j).statistics for k, j in ix.items()}
        if any(s is None or not s.has_min_max for s in st.values()):
            out.append(i)
            continue
        if st["xmin"].min <= bbox[2] and st["xmax"].max >= bbox[0] and st["ymin"].min <= bbox[3] and st["ymax"].max >= bbox[1]:
            out.append(i)
    return out


def _in_bbox(tbl, bbox=C.CA_BBOX):
    b = tbl.column("bbox")
    xmin, xmax = pc.struct_field(b, "xmin"), pc.struct_field(b, "xmax")
    ymin, ymax = pc.struct_field(b, "ymin"), pc.struct_field(b, "ymax")
    m = pc.and_(pc.and_(pc.less_equal(xmin, bbox[2]), pc.greater_equal(xmax, bbox[0])),
                pc.and_(pc.less_equal(ymin, bbox[3]), pc.greater_equal(ymax, bbox[1])))
    return tbl.filter(m)


def fetch_buildings(out_dir):
    fs = s3()
    files = theme_files(fs, "buildings", "building")
    out_dir.mkdir(parents=True, exist_ok=True)

    def one(k_path):
        k, path = k_path
        dest = out_dir / f"buildings_{k:04d}.parquet"
        if dest.exists():
            return k, -1
        pf = pq.ParquetFile(path, filesystem=fs)
        rgs = matching_row_groups(pf)
        if not rgs:
            pq.write_table(pa.table({"id": pa.array([], pa.string())}), dest)
            return k, 0
        t = pf.read_row_groups(rgs, columns=["id", "geometry", "bbox", "sources", "subtype", "class", "is_underground"])
        t = _in_bbox(t)
        primary = [s[0]["dataset"] if s else None for s in t.column("sources").to_pylist()]
        t = t.drop_columns(["sources"]).append_column("source_dataset", pa.array(primary, pa.string()))
        pq.write_table(t, dest, compression="zstd")
        return k, t.num_rows

    total = 0
    with ThreadPoolExecutor(8) as ex:
        for k, n in ex.map(one, enumerate(files)):
            total += max(n, 0)
            if n:
                print(f"  file {k}/{len(files)}: {n} CA footprints", flush=True)
    print(f"buildings: {total} footprints written to {out_dir}")


def fetch_divisions(out_dir):
    """County / locality polygons and neighborhood points for California."""
    fs = s3()
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = {"division": ["id", "geometry", "bbox", "subtype", "class", "names", "region", "country", "parent_division_id", "population"],
            "division_area": ["id", "geometry", "bbox", "subtype", "class", "names", "region", "country", "division_id"]}
    for typ, cl in cols.items():
        parts = []
        for path in theme_files(fs, "divisions", typ):
            pf = pq.ParquetFile(path, filesystem=fs)
            rgs = matching_row_groups(pf)
            if not rgs:
                continue
            t = _in_bbox(pf.read_row_groups(rgs, columns=cl))
            t = t.filter(pc.equal(t.column("region"), "US-CA"))
            names = [n["primary"] if n else None for n in t.column("names").to_pylist()]
            t = t.drop_columns(["names"]).append_column("name", pa.array(names, pa.string()))
            parts.append(t)
        tbl = pa.concat_tables(parts)
        pq.write_table(tbl, out_dir / f"{typ}_ca.parquet", compression="zstd")
        print(f"{typ}: {tbl.num_rows} CA rows")


def fetch_postal_cities(out_dir):
    """Count Overture address points per (5-digit postcode, postal city) in California.

    Used to name each ZIP by the city mail is addressed to (the most common postal city),
    which is what a Valpak list should show; locality polygons often pick a CDP instead.
    """
    fs = s3()
    counts = {}
    for path in theme_files(fs, "addresses", "address"):
        pf = pq.ParquetFile(path, filesystem=fs)
        rgs = matching_row_groups(pf)
        if not rgs:
            continue
        for rg in rgs:
            t = _in_bbox(pf.read_row_group(rg, columns=["country", "postcode", "postal_city", "address_levels", "bbox"]))
            t = t.filter(pc.equal(t.column("country"), "US"))
            for pcode, pcity, lv in zip(t.column("postcode").to_pylist(), t.column("postal_city").to_pylist(),
                                        t.column("address_levels").to_pylist()):
                if not lv or lv[0].get("value") != "CA" or not pcode:
                    continue
                city = pcity or (lv[-1].get("value") if len(lv) > 1 else None)
                if city:
                    k = (pcode[:5], city.strip().title())
                    counts[k] = counts.get(k, 0) + 1
    tbl = pa.table({"zip": [k[0] for k in counts], "postal_city": [k[1] for k in counts], "n": list(counts.values())})
    out_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(tbl, out_dir / "postal_cities_ca.parquet")
    print(f"postal cities: {tbl.num_rows} (zip, city) pairs from {sum(counts.values())} CA address points")


if __name__ == "__main__":
    which = sys.argv[1:] or ["divisions", "addresses", "buildings"]
    base = C.DATA_DIR / "overture"
    if "divisions" in which:
        fetch_divisions(base)
    if "addresses" in which:
        fetch_postal_cities(base)
    if "buildings" in which:
        fetch_buildings(base / "buildings")
