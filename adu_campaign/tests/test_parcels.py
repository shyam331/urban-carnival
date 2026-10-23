"""Integration check of the parcel stage on a synthetic 3-parcel block (no real data)."""
import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from adu_campaign import config as C
from adu_campaign import parcels

FT = 0.3048  # EPSG:3310 is metres


def _ft_box(x0, y0, x1, y1):
    return box(x0 * FT, y0 * FT, x1 * FT, y1 * FT)


def test_evaluate_and_zip_counts(monkeypatch):
    ox, oy = -150000, -450000  # somewhere in LA in EPSG:3310 metres
    shift = lambda g: gpd.GeoSeries([g], crs=C.EQUAL_AREA_CRS).translate(ox, oy).iloc[0]  # noqa: E731
    lots = gpd.GeoDataFrame({
        "apn": ["big", "small", "condo"],
        "use_code": ["0100", "0100", "010C"],
        "is_sfr": [True, True, False],
        "lot_sqft": [7500.0, 4000.0, 8000.0],
        "lot_size_basis": "polygon area",
        "situs_zip": ["90000", "90000", "90000"],
    }, geometry=[shift(_ft_box(0, 0, 50, 150)), shift(_ft_box(50, 0, 90, 100)), shift(_ft_box(90, 0, 150, 150))],
        crs=C.EQUAL_AREA_CRS)
    house = gpd.GeoDataFrame({"bid": ["h1"]}, geometry=[shift(_ft_box(10, 20, 40, 70))], crs=C.EQUAL_AREA_CRS).to_crs(4326)
    monkeypatch.setattr(parcels, "footprints_in", lambda bounds: house)
    zcta = gpd.GeoDataFrame({"zip": []}, geometry=[], crs=4326)

    out = parcels.evaluate(lots, zcta)
    assert set(out.apn) == {"big", "small"}  # condo excluded by SFR filter
    big = out.set_index("apn").loc["big"]
    # 7500 - 1500 - front 15*50 - rear 4*50 - sides 2*4*(150-19) = 4002
    assert abs(big.est_buildable_sqft - 4002) < 1
    assert bool(big.buildable_750) and bool(big.buildable_1200)
    z = parcels.zip_counts(out).set_index("zip").loc["90000"]
    assert z.sfr_parcels == 2 and z.sfr_lot_5k == 1 and z.buildable_750 == 1
    assert z.pct_lot_5k == 0.5
