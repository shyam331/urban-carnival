"""Configurable constants for the California ADU / Valpak ZIP targeting pipeline.

Every threshold, setback, tier and weight used anywhere in the pipeline lives here.
Change a value, re-run `python -m adu_campaign.run`, and every output is rebuilt.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Parcel / ADU rule (criteria 1-3)
# ---------------------------------------------------------------------------
MIN_LOT_SQFT = 5_000            # criterion 2: lot size >= this
SIDE_SETBACK_FT = 4             # CA state ADU baseline (Gov. Code 66314(d)(7), formerly 65852.2)
REAR_SETBACK_FT = 4             # CA state ADU baseline
FRONT_SETBACK_FT = 15           # default front-yard depth assumption (local codes vary)
BUILDING_SEPARATION_FT = 0      # extra clearance kept around the existing house (0 = none)
ADU_MIN_BUILDABLE_SQFT = 750    # criterion 3: "qualifies" threshold
ADU_LARGE_BUILDABLE_SQFT = 1_200  # second band reported separately ("fits a 1,200 sq ft ADU")
# A footprint must cover at least this share of its own area inside a parcel to be
# counted as that parcel's existing building (handles footprints straddling lines).
FOOTPRINT_PARCEL_OVERLAP_MIN = 0.5

# ---------------------------------------------------------------------------
# Market tiers (criterion 4) -- Redfin median sale $/sq ft, trailing 12 months
# ---------------------------------------------------------------------------
# Ordered high -> low. A ZIP gets the first tier whose floor it meets.
PRICE_TIERS = [
    {"tier": 1, "label": "Tier 1 (>= $700/sf)", "min_ppsf": 700, "weight": 3},
    {"tier": 2, "label": "Tier 2 ($600-699/sf)", "min_ppsf": 600, "weight": 2},
    {"tier": 3, "label": "Tier 3 ($500-599/sf)", "min_ppsf": 500, "weight": 1},
]
# Redfin property type used for the tier test. SFR matches the ADU audience;
# "All Residential" is used only as a flagged fallback when SFR is missing.
REDFIN_PROPERTY_TYPE = "Single Family Residential"
REDFIN_FALLBACK_PROPERTY_TYPE = "All Residential"
TRAILING_MONTHS = 12            # four non-overlapping 90-day Redfin windows
MIN_HOMES_SOLD_12M = 5          # below this the ZIP's $/sf is flagged "thin sample"

# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
# rank_score = qualifying parcel count x tier weight (weights above).
# When parcel data is unavailable for a ZIP's county, an INTERIM score of
# Redfin SFR homes sold (12 mo) x tier weight is shown instead and labelled.
SUMMARY_TOP_N = 100

# ---------------------------------------------------------------------------
# Data sources (all verified reachable from this environment unless noted)
# ---------------------------------------------------------------------------
REDFIN_ZIP_TRACKER_URL = (
    "https://redfin-public-data.s3.us-west-2.amazonaws.com/"
    "redfin_market_tracker/zip_code_market_tracker.tsv000.gz"
)
ZILLOW_ZHVI_ZIP_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zhvi/"
    "Zip_zhvi_uc_sfr_sm_sa_month.csv"
)
# Census TIGER 2020 ZCTA is preferred; www2.census.gov is blocked here, so the
# pipeline falls back to a GitHub mirror of the 2010 TIGER ZCTA for California.
ZCTA_URLS = [
    "https://www2.census.gov/geo/tiger/TIGER2024/ZCTA520/tl_2024_us_zcta520.zip",
    "https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/master/"
    "ca_california_zip_codes_geo.min.json",
]
# Overture Maps release on AWS S3. Its building theme redistributes Microsoft
# US/Global ML Building Footprints (plus OSM/Esri/Google); its divisions theme
# supplies county, city (locality) and neighborhood names.
OVERTURE_BUCKET = "overturemaps-us-west-2"
OVERTURE_RELEASE = "2026-10-21.0"
MICROSOFT_FOOTPRINTS_URL = (
    "https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/California.geojson.zip"
)
CA_BBOX = (-124.48, 32.53, -114.13, 42.01)  # xmin, ymin, xmax, ymax (WGS84)
EQUAL_AREA_CRS = "EPSG:3310"  # California Albers, metres
SQFT_PER_SQM = 10.763910416709722

# ---------------------------------------------------------------------------
# Reporting regions (reported separately in "By County" and the Summary)
# ---------------------------------------------------------------------------
FOCUS_REGIONS = {
    "Orange County": ["Orange"],
    "Los Angeles County": ["Los Angeles"],
    "San Francisco": ["San Francisco"],
    "Berkeley / Oakland / Alameda County": ["Alameda"],
    "Peninsula & South Bay (Santa Clara / San Mateo)": ["Santa Clara", "San Mateo"],
    "Marin": ["Marin"],
    "San Diego": ["San Diego"],
    "Ventura": ["Ventura"],
    "Sacramento": ["Sacramento"],
    "Inland Empire (Riverside / San Bernardino)": ["Riverside", "San Bernardino"],
}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PKG_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PKG_DIR / "output"
# Large downloads stay out of git. Override with ADU_DATA_DIR.
import os  # noqa: E402

DATA_DIR = Path(os.environ.get("ADU_DATA_DIR", PKG_DIR / "data"))
