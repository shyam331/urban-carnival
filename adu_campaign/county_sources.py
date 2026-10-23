"""Parcel source registry for all 58 California counties.

Research method (2026-10-23): web search of official county pages. The county hosts
themselves were NOT reachable from the build environment (network policy), so no
field name below has been confirmed against a live layer. Each entry records where its
details came from in `evidence`. `availability()` in parcels.py probes the URL at run time.

Keys used by the pipeline:
  type            "arcgis" (REST layer; pipeline pages through /query), "file" (direct
                  download), "portal" (hub/Socrata page that needs a manual export),
                  "request" (request-only), "paid", or None (nothing found)
  url             dataset or layer URL
  vintage         as stated by the source (unverified unless noted)
  lot_size_field / lot_size_units
  use_code_field / sfr_code_regex   SFR rule applied to the use-code field
  situs_zip_field / situs_city_field
  apn_field
  evidence        where the details came from; "unverified" means do not trust until
                  the layer's ?f=pjson has been checked
"""

UNVERIFIED = "unverified"

COUNTY_SOURCES = {
    "Los Angeles": {
        "type": "arcgis",
        "source": "LA County Parcels (LACounty_Cache/LACounty_Parcel MapServer/0)",
        "url": "https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Parcel/MapServer/0",
        "vintage": UNVERIFIED,
        "apn_field": "AIN",
        "lot_size_field": None,  # Shape.STArea() only (geometry) -> polygon area used
        "lot_size_units": None,
        "use_code_field": "UseCode",
        "sfr_code_regex": r"^01",  # Assessor portal: 0100 = Single Family Residence
        "server_where": "UseCode LIKE '01%'",
        "situs_zip_field": "SitusZIP",
        "situs_city_field": "SitusCity",
        "record_count": UNVERIFIED,
        "restrictions": "none found; owner names not exposed",
        "evidence": "field names from search-indexed layer pages and the City of Pasadena hub mirror; "
                    "0100 = SFR from the LA County Assessor portal",
        "alt": "Assessor Parcel Data Rolls 2021-2025 (data.lacounty.gov, ~12.1M rows CSV, join on AIN)",
    },
    "Orange": {
        "type": "portal",
        "source": "SCAG 2019 Annual Land Use - Orange County (LU19 + ACRES); OC Landbase has no use code",
        "url": "https://hub.scag.ca.gov/datasets/b56dfdbd6770497ca800506928f36f1e_0",
        "vintage": "2019 parcels / tax roll (collected late 2019-early 2020)",
        "lot_size_field": "ACRES", "lot_size_units": "acres",
        "use_code_field": "LU19", "sfr_code_regex": r"^111",  # SCAG 2016 legend: 1110-1113 SFR
        "situs_zip_field": None, "situs_city_field": None, "apn_field": "APN19",
        "record_count": UNVERIFIED,
        "restrictions": "no free OC Assessor roll with use codes; county refers to ParcelQuest (paid)",
        "evidence": "SCAG hub listing + legend via search snippets; stale (2019)",
        "alt": "OC Public Works Parcel Polygons (data-ocpw.opendata.arcgis.com), >687k parcels, geometry only",
    },
    "San Francisco": {
        "type": "portal",
        "source": "Assessor Historical Secured Property Tax Rolls (wv5m-vpq2) + Parcels Active and Retired (acdm-wktn)",
        "url": "https://data.sf.gov/Housing-and-Buildings/Assessor-Historical-Secured-Property-Tax-Rolls/wv5m-vpq2",
        "vintage": "rolls 2007-2024 per page snippet; parcels layer updated 2026-05-24 (data.gov catalog)",
        "lot_size_field": "lot_area", "lot_size_units": UNVERIFIED,
        "use_code_field": "use_code", "sfr_code_regex": None,  # SFR code not confirmed -> must be set
        "situs_zip_field": None, "situs_city_field": None, "apn_field": "parcel_number",
        "record_count": UNVERIFIED, "restrictions": "none found; domain moved data.sfgov.org -> data.sf.gov 2026-09-01",
        "evidence": "Socrata page snippets; SFR code table pa56-ek2h not checked",
    },
    "Alameda": {
        "type": "portal",
        "source": "Alameda County Open Data Hub - Parcels",
        "url": "https://data.acgov.org/datasets/2b026350b5dd40b18ed7a321fdcdba81",
        "vintage": "Data Updated 2026-10-04 (hub page snippet)",
        "lot_size_field": None, "lot_size_units": None,
        "use_code_field": "UseCode", "sfr_code_regex": r"^1100$",  # Assessor UseCodeList: 1100 SFR
        "situs_zip_field": None, "situs_city_field": "SitusCity", "apn_field": "APN",
        "record_count": "489,651", "restrictions": "no license stated",
        "evidence": "record count + vintage from hub snippet; UseCode/SitusCity per third-party guide; "
                    "1100 = SFR from propinfo.acgov.org/UseCodeList",
    },
    "Santa Clara": {
        "type": "portal",
        "source": "County of Santa Clara Open Data - Parcels (ubcd-cewv)",
        "url": "https://data.sccgov.org/Government/Parcels/ubcd-cewv",
        "vintage": "as of FY 2025 (annual, ~August)",
        "lot_size_field": None, "lot_size_units": None,
        "use_code_field": None, "sfr_code_regex": None,
        "situs_zip_field": None, "situs_city_field": None, "apn_field": "apn",
        "record_count": "~500K", "restrictions": "as-is",
        "evidence": "CSV header via search snippet: no use code -> SFR cannot be identified from free data",
    },
    "San Mateo": {
        "type": "portal",
        "source": "San Mateo County GIS Data Download - Active Parcels",
        "url": "https://www.smcgov.org/tsd/gis-data-download",
        "vintage": "exported daily (per page)",
        "lot_size_field": None, "lot_size_units": None, "use_code_field": None, "sfr_code_regex": None,
        "situs_zip_field": None, "situs_city_field": None, "apn_field": None,
        "record_count": UNVERIFIED, "restrictions": "none found",
        "evidence": "attribute list not verifiable",
    },
    "Marin": {
        "type": "portal",
        "source": "Marin County GIS Open Data - Parcels",
        "url": "https://gisopendata.marincounty.gov/datasets/marincounty::parcels/about",
        "vintage": "last updated June 2026 per snippet (monthly)",
        "lot_size_field": None, "lot_size_units": None,
        "use_code_field": None, "sfr_code_regex": r"^11$",  # Assessor use code 11 (page marked obsolete)
        "situs_zip_field": None, "situs_city_field": None, "apn_field": None,
        "record_count": "~96,239", "restrictions": "not survey-accurate",
        "evidence": "use-code field name unverified; code 11 from an obsolete Assessor page",
    },
    "San Diego": {
        "type": "arcgis",
        "source": "SANDAG/SanGIS Parcels (Hosted FeatureServer)",
        "url": "https://geo.sandag.org/server/rest/services/Hosted/Parcels/FeatureServer/0",
        "vintage": UNVERIFIED + " (attributes refreshed weekly per SanGIS)",
        "lot_size_field": "acreage", "lot_size_units": "acres",  # blank under 0.25 ac -> polygon area
        "use_code_field": "nucleus_use_cd", "sfr_code_regex": r"^11[01]$",
        "server_where": "nucleus_use_cd IN ('110','111')",
        "situs_zip_field": "situs_zip", "situs_city_field": None, "apn_field": "apn",
        "record_count": UNVERIFIED, "restrictions": "public version excludes owner fields; stacked condo parcels",
        "evidence": "field names via search snippets; 110/111 SFR from a City of San Diego document, not the Assessor",
    },
    "Ventura": {
        "type": "portal",
        "source": "Ventura County Parcels Monthly (geometry only) + SCAG 2019 land use for SFR",
        "url": "https://venturacountydatadownloads-vcitsgis.hub.arcgis.com/datasets/parcels-monthly",
        "vintage": "monthly per page; preview ~2 years old",
        "lot_size_field": None, "lot_size_units": None, "use_code_field": None, "sfr_code_regex": None,
        "situs_zip_field": None, "situs_city_field": None, "apn_field": "APN",
        "record_count": "268,134", "restrictions": "one snippet labels the item 'Private Member'",
        "evidence": "preview fields via snippet",
    },
    "Sacramento": {
        "type": "portal",
        "source": "Sacramento County Open Data - Parcels",
        "url": "https://data-sacramentocounty.opendata.arcgis.com/datasets/sacramentocounty::parcels",
        "vintage": UNVERIFIED,
        "lot_size_field": None, "lot_size_units": UNVERIFIED,  # 'Lot Size' label; raw name unverified
        "use_code_field": None, "sfr_code_regex": None,  # 'Landuse' labels; SFR rule unverified
        "situs_zip_field": None, "situs_city_field": None, "apn_field": None,
        "record_count": "502,165", "restrictions": "none found",
        "evidence": "display labels only via snippet",
    },
    "Riverside": {
        "type": "portal",
        "source": "Riverside County OpenData Assessor MapServer / Parcels CREST",
        "url": "https://gis.countyofriverside.us/arcgis_mapping/rest/services/OpenData/Assessor/MapServer",
        "vintage": UNVERIFIED,
        "lot_size_field": "ACREAGE", "lot_size_units": "acres",
        "use_code_field": "CLASS_CODE", "sfr_code_regex": None,  # code meaning unverified
        "situs_zip_field": "ZIP_CODE", "situs_city_field": "SITUS_CITY", "apn_field": "APN",
        "record_count": UNVERIFIED, "restrictions": "bulk owner data paid",
        "evidence": "field names from a City of Palm Springs mirror; layer id unverified",
    },
    "San Bernardino": {
        "type": "portal",
        "source": "San Bernardino County Parcel Dataset (open.sbcounty.gov)",
        "url": "https://open.sbcounty.gov/datasets/san-bernardino-county-parcel-dataset/about",
        "vintage": UNVERIFIED,
        "lot_size_field": None, "lot_size_units": None, "use_code_field": None, "sfr_code_regex": None,
        "situs_zip_field": None, "situs_city_field": None, "apn_field": None,
        "record_count": "~840,273", "restrictions": "custom license; address/owner redacted (AB 1785)",
        "evidence": "attributes unverified; SCAG 2019 covers land use",
    },
    "Contra Costa": {
        "type": "file",
        "source": "Contra Costa County GIS Downloads - Assessor Parcels_Public shapefile (monthly)",
        "url": "https://gis.cccounty.us/Downloads/Assessor/",
        "vintage": "monthly; cached listing showed Parcels_Public_September2025.zip",
        "lot_size_field": "ACREAGE", "lot_size_units": "acres",
        "use_code_field": "USE_CODE", "sfr_code_regex": None,  # no Assessor code table found
        "situs_zip_field": None, "situs_city_field": None, "apn_field": None,
        "record_count": UNVERIFIED, "restrictions": "free; owner not exposed",
        "evidence": "field names per third-party guide",
    },
}

# Counties where only geometry-only, stale, request-only or paid parcel data was found.
OTHER_COUNTY_NOTES = {
    "Fresno": ("portal", "https://www.fresnocountyca.gov/Departments/Public-Works-and-Planning/maps-and-gis-information", "shapefile downloads; attributes unverified"),
    "Sonoma": ("portal", "https://sonomacounty.gov/administrative-support-and-fiscal-services/clerk-recorder-assessor/assessor/property-data-for-sale-to-the-public", "free Parcels Base (no owner); fuller attributes sold"),
    "San Joaquin": ("file", "https://sjmap.org/GISDataDownload.htm", "extracts Jan/Jul; latest noted 2025-01-06"),
    "Solano": ("portal", "https://regis.solanocounty.com/apps", "possible lotsize/usecode on Parcels_Public_Aumentum; ownership unconfirmed"),
    "Shasta": ("arcgis", "https://gis.shastacounty.gov/arcgis/rest/services/OpenData/Parcels/MapServer/0", "last updated July 2025"),
    "Yolo": ("portal", "https://data.sacog.org/datasets/867d6a5e7a2c44c7a4f6e996b2d89561_0", "SACOG mirror"),
    "Humboldt": ("portal", "https://humboldtgov.org/276/GIS-Data-Download", "archived 2015 copy"),
    "Siskiyou": ("portal", "https://www.siskiyoucounty.gov/planning/webform/gis-data-download", "acreage fields; disclaimer"),
    "Mariposa": ("arcgis", "https://services2.arcgis.com/wEula7SYiezXcdRv/ArcGIS/rest/services/Parcels_Public_View/FeatureServer", "daily refresh"),
    "Inyo": ("arcgis", "https://gis.inyo.gov/server/rest/services/ParcelsPublic/MapServer", ""),
    "Trinity": ("arcgis", "https://services2.arcgis.com/32siQkg0O6da8zFF/ArcGIS/rest/services/Parcel_Service/FeatureServer", "maxRecordCount 1000"),
    "El Dorado": ("arcgis", "https://gis.eldoradocounty.ca.gov/mapping/rest/services/Property/Parcels/FeatureServer/0", ""),
    "Tuolumne": ("request", "https://tuolumnecounty.ca.gov/385", "free after File Access Request Form"),
    "Plumas": ("request", "https://ca-plumascounty.civicplus.com/2299", "request-only; data use terms"),
    "Calaveras": ("portal", "https://gisdept.calaverasgov.us/FAQs", "last updated 2019-01-04 (2020 capture)"),
    "Stanislaus": ("portal", "https://open-data-stancounty-gis.hub.arcgis.com/", "2019 copy on Berkeley GeoData"),
    "Kern": ("paid", None, "only a 2013 UCSB archive; Assessor codes 0100-0106 = SFR"),
    "Santa Barbara": ("unverified", "https://services3.arcgis.com/hMpg7vsYb74pEKjX", "unattributed ParcelBaseMap FeatureServer, last edit 2024-06-03"),
    "San Luis Obispo": ("paid", None, "county refers parcel requests to ParcelQuest"),
    "Placer": ("archive", None, "2020 Stanford copy"),
    "Merced": ("archive", None, "2019 copy"),
    "Tehama": ("archive", None, "2019 copy"),
    "Nevada": ("archive", None, "2020 copy, CC-BY"),
    "San Benito": ("archive", None, "2016 copy"),
    "Butte": ("archive", None, "2016 copy, license agreement"),
    "Santa Cruz": ("archive", None, "2015 copy"),
    "Napa": ("portal", None, "registration download, unconfirmed"),
    "Kings": ("unverified", None, "county GIS page; parcel availability unconfirmed"),
    "Yuba": ("unverified", None, "county GIS catalog; parcel availability unconfirmed"),
    "Mono": ("archive", None, "gis.mono.ca.gov, 2014 metadata"),
    "Amador": ("archive", None, "viewer only; state-server copy through May 2021"),
    "Mendocino": ("unverified", None, "county ArcGIS service mentioned, URL unverified"),
}
NO_FREE_SOURCE = ["Monterey", "Tulare", "Imperial", "Madera", "Lake", "Sutter", "Glenn", "Colusa",
                  "Del Norte", "Lassen", "Modoc", "Sierra", "Alpine"]

STATEWIDE_SOURCES = [
    {"source": "CA DWR i15_Parcels_Assessor_Lightbox (statewide, 58 counties)",
     "url": "https://gis.water.ca.gov/arcgis/rest/services/Planning/i15_Parcels_Assessor_Lightbox/MapServer/0",
     "vintage": "metadata 2021-07-12; 'updated quarterly' per description (current refresh unverified)",
     "lot_size_field": "none (geometry only)", "use_code_field": "none",
     "notes": "fields OBJECTID, PARCEL_APN, COUNTYNAME, TAXAPN, SITE_ADDR -> cannot identify SFR"},
    {"source": "Regrid (paid fallback for every 'no data' county)",
     "url": "https://app.regrid.com/store/us/ca",
     "vintage": "per county; 58/58 CA counties online",
     "lot_size_field": "ll_gissqft (Regrid standard schema)", "use_code_field": "usecode / usedesc, lbcs_activity",
     "notes": "2023 list prices: $300/county standard, $8,000 statewide (2026 pricing unverified)"},
]

# Regrid standard-schema mapping, applied automatically to a dropped-in Regrid export.
# LBCS Structure 1110-1119 = single-family buildings (verify against
# support.regrid.com/parcel-data/lbcs before relying on it; county-native `usecode` is
# also carried in Regrid exports and can be mapped with the county rule instead).
REGRID_SCHEMA = {
    "apn_field": "parcelnumb",
    "lot_size_field": "ll_gissqft", "lot_size_units": "sqft",
    "use_code_field": "lbcs_structure", "sfr_code_regex": r"^111\d$",
    "situs_zip_field": "szip", "situs_city_field": "scity",
}

ALL_COUNTIES = [
    "Alameda", "Alpine", "Amador", "Butte", "Calaveras", "Colusa", "Contra Costa", "Del Norte",
    "El Dorado", "Fresno", "Glenn", "Humboldt", "Imperial", "Inyo", "Kern", "Kings", "Lake",
    "Lassen", "Los Angeles", "Madera", "Marin", "Mariposa", "Mendocino", "Merced", "Modoc",
    "Mono", "Monterey", "Napa", "Nevada", "Orange", "Placer", "Plumas", "Riverside",
    "Sacramento", "San Benito", "San Bernardino", "San Diego", "San Francisco", "San Joaquin",
    "San Luis Obispo", "San Mateo", "Santa Barbara", "Santa Clara", "Santa Cruz", "Shasta",
    "Sierra", "Siskiyou", "Solano", "Sonoma", "Stanislaus", "Sutter", "Tehama", "Trinity",
    "Tulare", "Tuolumne", "Ventura", "Yolo", "Yuba",
]
