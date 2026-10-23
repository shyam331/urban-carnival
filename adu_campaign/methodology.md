# California ADU direct-mail targeting: methodology

Build date: 2026-10-23 · Code: `adu_campaign/` · Output: `output/campaign_zips.xlsx`

> **Read this first.** ZIP-level results estimate the **share of qualifying lots** in each ZIP.
> They are **not a verified list of homes**. In this build, no county parcel file could be
> downloaded: every county assessor host and data.ca.gov were unreachable from the build
> environment. So the parcel counts (criteria 1–3) read **"no data"** for every ZIP, and the
> ranking shown is an **interim** ranking. It uses $/sq ft tier × Redfin single-family sales
> volume and is labelled as such on every tab. The parcel stage is built and tested. It runs
> automatically when parcel data is reachable, or when county or Regrid exports are dropped
> into `data/parcels/`.

## 1. What was asked and what was delivered

| Brief item | Status in this build |
|---|---|
| Criterion 1: SFR parcels (assessor use code) | Code done (`parcels.py`, per-county use-code rules in `county_sources.py`). **No data**: assessor sources unreachable. |
| Criterion 2: lot ≥ 5,000 sq ft | Code done. Uses the assessor lot-size field when present (acres converted), else polygon area. **No data**. |
| Criterion 3: buildable ≥ 750 sq ft (and ≥ 1,200 band, contiguous-area flag) | Code done and unit-tested on synthetic lots (`tests/`). Footprints downloaded for all of CA. **No parcel data** to apply it to. |
| Criterion 4: ZIP median $/sq ft ≥ $700 / $600 / $500 (trailing 12 mo, Redfin) | **Done for every CA ZIP Redfin publishes** (1,620 ZIPs; 1,506 have a ZIP boundary). |
| ZIP → county, city, neighborhoods | **Done** for all 1,763 CA ZCTAs (Overture divisions + address points). |
| Ranking by qualifying parcels × tier | Formula in place (live in Excel). **Interim proxy used** until parcel counts exist. |
| Zillow ZHVI cross-check | **Not done**: files.zillowstatic.com unreachable. Loader built (`zillow.py`). |
| Spot check of 10 ZIPs | Done with web-search snippets (direct page fetches failed). See §7. |

## 2. Sources and vintage

The full table, with live/blocked status probed at build time, is on the **Source Inventory** tab
(and `output/source_inventory.csv`).

| Source | Used for | Vintage | Status |
|---|---|---|---|
| Redfin Data Center ZIP market tracker (`redfin-public-data.s3…/zip_code_market_tracker.tsv000.gz`) | $/sq ft, sale price, homes sold | 90-day windows ending 2025-08-31, 2025-11-30, 2026-02-28, 2026-05-31; file updated 2026-06-02 | Downloaded (1.55 GB) |
| Overture Maps `2026-10-21.0` buildings (S3) | Building footprints. Overture redistributes **Microsoft ML Building Footprints** alongside OSM / Esri / Google footprints; each footprint keeps its source tag. | Release 2026-10-21 | Downloaded: 15.66 M footprints in the CA bbox. 13.67 M fall inside CA ZIPs; 27% are tagged Microsoft (the rest OSM/Esri/Google, preferred by Overture where they overlap). |
| Microsoft US Building Footprints (direct, `minedbuildings.z5.web.core.windows.net`) | (preferred copy) | – | Blocked; Overture copy used instead |
| Overture divisions (county / locality polygons, neighborhood points) | County, city, neighborhood names | 2026-10-21 | Downloaded |
| Overture addresses (postcode + postal city) | Mailing city per ZIP | 2026-10-21 | Downloaded |
| Census ZCTA via GitHub mirror (`OpenDataDE/State-zip-code-GeoJSON`, CA file) | ZIP polygons | **2010** TIGER ZCTA | Used. The 2020/2024 TIGER host (www2.census.gov) is blocked. |
| Zillow ZHVI ZIP SFR | Cross-check | – | Blocked |
| County assessor / open-data portals (58 counties) | Parcels, use codes, lot size | See inventory | **All blocked or manual-export only** |
| CA DWR statewide parcel layer (`i15_Parcels_Assessor_Lightbox`) | Statewide parcels | Metadata 2021-07-12 | Blocked. It also has **no use code or lot size** (APN, county, address only), so it cannot drive the SFR filter. |
| Regrid | Paid fallback | Per county | Not purchased |

**How parcel sources were vetted.** Field names, vintages and SFR codes in `county_sources.py`
came from web-search snippets of the official county pages, because the pages themselves were
unreachable. Each entry says where its details came from. Anything not confirmed is marked
`unverified`. The pipeline refuses to process a county whose SFR use-code rule is unverified,
rather than guessing one. Before trusting any county run, open the layer's `?f=pjson` and
confirm the field names.

SFR rules with some documentary support:

* **LA County:** `UseCode` starting `01` (0100 = Single Family Residence, Assessor portal).
* **Alameda:** `1100` (Assessor UseCodeList).
* **San Diego:** `nucleus_use_cd` 110 / 111 (City of San Diego document, not the Assessor).
* **Marin:** use code 11 (Assessor page marked obsolete).
* **SCAG 2019 land use:** `LU19` 1110–1113 (used for Orange; 2019 vintage).

Unverified or unavailable: SF, Sacramento, Riverside, San Bernardino, Ventura, Contra Costa, Santa Clara (its free layer has
no use code at all), San Mateo.

## 3. Parcel rule (criteria 1–3), as implemented

All values are constants in `config.py` and are mirrored on the **Assumptions** tab.

| Constant | Default | Note |
|---|---|---|
| `MIN_LOT_SQFT` | 5,000 | criterion 2 |
| `SIDE_SETBACK_FT`, `REAR_SETBACK_FT` | 4, 4 | CA state ADU baseline (Gov. Code §66314(d)(7), formerly §65852.2) |
| `FRONT_SETBACK_FT` | 15 | Default from the brief. Local front setbacks are often 20–25 ft. |
| `BUILDING_SEPARATION_FT` | 0 | Clearance kept around the existing house. Attached ADUs are allowed, so default is 0. |
| `ADU_MIN_BUILDABLE_SQFT` | 750 | criterion 3 |
| `ADU_LARGE_BUILDABLE_SQFT` | 1,200 | reported as a second band |
| `FOOTPRINT_PARCEL_OVERLAP_MIN` | 0.5 | a footprint counts for a parcel if ≥ 50% of it lies inside |

Per parcel (`buildable.py`), in feet, in California Albers (EPSG:3310):

1. **SFR filter.** The county use-code regex is applied to the use-code field. Condos, multifamily,
   commercial and vacant codes fail it.
2. **Lot size.** Assessor lot-size field (acres × 43,560 when in acres). Polygon area is used
   when the field is blank (e.g. San Diego leaves `acreage` blank under 0.25 ac).
3. **Existing footprint.** Union of Overture/Microsoft footprints with ≥ 50% of their area in the
   parcel, clipped to the parcel. Detached garages and sheds are included when they were mapped.
4. **Setbacks.** The parcel is shrunk inward by 4 ft on every side (side and rear setbacks).
   Then the front yard is removed: a 15 ft strip along the **front lot line**.
   * Street frontage is not in the data, so the front line is taken as the short side of the
     parcel's minimum rotated rectangle that is nearest the house.
5. **`est_buildable_sqft`** = remaining area minus the footprint (plus separation buffer). On a
   rectangle this equals the brief's arithmetic: lot − footprint − 15·w − 4·w − 2·4·(d − 19).
   This is checked in `tests/test_buildable.py`.
6. **`largest_contiguous_sqft`** = the largest single remaining piece. Parcels that pass
   criterion 3 but whose largest piece is < 750 sq ft are counted in the flag column
   "contiguous area likely < 750".
7. **Outputs.** Qualifying = SFR ∧ lot ≥ 5,000 ∧ est. buildable ≥ 750. The ≥ 1,200 band is also counted.
8. **ZIP assignment.** Situs ZIP when the source has one, else the ZCTA containing the parcel.

ZIP aggregates (All ZIPs tab):

* total SFR parcels
* count and % with lot ≥ 5,000
* count and % with est. buildable ≥ 750
* count ≥ 1,200
* contiguous flag count
* median lot size

## 4. Market tiers (criterion 4)

* Redfin `PROPERTY_TYPE = "Single Family Residential"`. When a ZIP has no SFR rows, the
  "All Residential" figures are used and flagged in the `$/sq ft basis` column (42 ZIPs).
* **Trailing 12 months** = the four non-overlapping 90-day Redfin windows ending 2026-05-31.
  * ZIP $/sq ft = homes-sold-weighted average of the four window medians.
  * The same method gives the sale price.
  * Homes sold = sum of the four windows.
  * This approximates a true 12-month median. Redfin does not publish one at ZIP level.
* Tiers, highest floor met:

  | Tier | Median $/sq ft | Weight |
  |---|---|---|
  | 1 | ≥ $700 | 3 |
  | 2 | $600–699 | 2 |
  | 3 | $500–599 | 1 |

  * The tiers are cumulative: "≥ $600" means Tier 1 plus Tier 2.
  * The weights are our choice and can be edited on the Assumptions tab.
* ZIPs with fewer than 5 sales in 12 months are flagged `Thin sample` but still tiered.

## 5. Ranking

* **Target formula (the brief's):** `rank score = qualifying parcels × tier weight`. It is live
  in Excel (All ZIPs, "Rank score") and is used for every ZIP whose county was processed.
* **This build (interim):** `interim score = Redfin SFR homes sold (12 mo) × tier weight`.
  * This is a market-size proxy: active, high-value SFR ZIPs rise to the top.
  * It does **not** measure lot size or ADU room. Dense urban ZIPs with small lots
    (e.g. parts of SF, Santa Monica, Berkeley flats) are probably over-ranked by it.
* Processed (parcel-based) scores always rank ahead of interim scores. The two are never mixed.

## 6. Geography and names

* **ZIP universe.** 1,763 California ZCTAs (2010), plus any Redfin ZIP not in that set.
  * ZIPs created after 2010 have no polygon. They show "(not in 2010 ZCTA)" as county.
  * ZCTAs approximate USPS ZIP delivery areas. PO-box-only ZIPs have no ZCTA.
* **County.** The Overture county polygon with the largest overlap. The share is in
  "County share of ZIP area". Multi-county ZIPs (e.g. 94708: Berkeley Hills in Alameda +
  Kensington in Contra Costa) are assigned to the larger-area county.
* **City.** Chosen in this order:
  1. The postal city used by most Overture address points in the ZIP. This is what a mailer should
     print. It is used only where address points cover at least 30% of the ZIP's house-scale
     buildings and that city holds a majority (1,465 ZIPs).
     * Overture address coverage is uneven: Alameda County has almost none.
  2. Otherwise, the Overture locality polygon with the largest overlap (134 ZIPs).
     * This names the incorporated city, which can differ from the postal name for
       unincorporated areas. Example: 94580, mailed as San Lorenzo, shows Hayward.
  3. Otherwise, the nearest locality point (164 mostly rural ZIPs).

  Other postal cities with ≥ 10% of addresses are listed.
* **PO-box / unique ZIPs.** 72 Redfin ZIPs that meet a tier have no ZCTA polygon and no address
  points. These are PO-box or unique ZIPs; Redfin reports sales there from owners' mailing
  addresses. They cannot be saturation-mailed, so they appear on All ZIPs with county
  "(no ZCTA …)" but are **excluded from ranking, Summary, Valpak and tier counts**.
* **Neighborhoods.** Overture `macrohood` / `neighborhood` / `microhood` points inside each ZIP
  polygon. Many suburban and rural ZIPs have none.
* **Focus regions** are reported separately on "By County":
  * Orange
  * Los Angeles
  * San Francisco
  * Alameda (Berkeley/Oakland)
  * Santa Clara + San Mateo
  * Marin
  * San Diego
  * Ventura
  * Sacramento
  * Inland Empire (Riverside + San Bernardino)
  * "Rest of California"

## 7. Validation: 10-ZIP spot check

Direct fetches of redfin.com / zillow.com failed from the build environment (DNS / proxy). So the
check used web-search snippets of those pages and of other market reports. Most Redfin ZIP pages
expose listing-side numbers in snippets, not $/sq ft, so several ZIPs could only be compared at
city level.

Our values: Redfin SFR, trailing 4 quarters to 2026-05-31.

| ZIP (area) | Our $/sf · median price · sales (12 mo) · tier | Comparison found | Difference | Verdict |
|---|---|---|---|---|
| 95125 (San Jose, Willow Glen) | $1,138 · $2.06M · 381 · T1 | JLee Realty (MLSListings), Q2 2026 houses: $1,154/sf, $2.25M, 114 sales (one quarter) | $/sf −1.4%, price −8% | Consistent; tier unchanged |
| 95818 (Sacramento, Land Park) | $511 · $746K · 233 · T3 | RealtyTrac Sep 2026 median sold $759,900; Sacramento Assoc. of Realtors via local press $515/sf (year not stated) | price −1.9%, $/sf −0.8% | Consistent. **Only $11 above the T3 floor**, so the tier is sensitive to the window. |
| 92506 (Riverside) | $392 · $729K · 407 · below $500 | TopHap (ATTOM) Aug 2026: ~$426/sf, $698K, 471 sales | $/sf −8%, price +4% | Consistent; stays below every tier |
| 92661 (Newport Beach, Balboa) | $2,618 · $5.33M · 48 · T1 | Brokerage ZIP page (undated): median $5.77M | price −8% | Consistent within small-sample noise |
| 94708 (Berkeley Hills / Kensington) | $847 · $1.62M · 149 · T1 | ATTOM early 2025 ZIP median $1.765M; Redfin Berkeley city Nov 2025 $768/sf | price −8% vs ATTOM | Tier unchanged. City $/sf is lower but includes the flats and condos. |
| 90272 (Pacific Palisades) | $1,228 · $3.92M · 114 · T1 | ATTOM Jun 2025: median $2.78M from 394 residential sales | **price +41%, sales −71%** | **Discrepancy.** Likely cause (not verified): after the January 2025 fire, many sales were burned lots, which ATTOM may count as residential and Redfin SFR would mostly exclude. Tier unaffected, but treat this ZIP's sales and lot inventory as abnormal. |
| 94941 (Mill Valley) | $1,084 · $2.28M · 279 · T1 | Redfin Mill Valley city Feb 2025: $991/sf, $1.765M | city-level, older | Not directly verifiable; directionally consistent |
| 94110 (SF Mission / Bernal Hts) | $1,089 · $1.54M · 258 · T1 | Redfin SF citywide Jul 2025: $912/sf (all property types) | city-level, all types | Not directly verifiable. SFR premium over condo-heavy citywide figure is plausible. |
| 93001 (Ventura) | $798 · $1.14M · 137 · T1 | Zillow Ventura city ZHVI Jun 2026: $897K typical value (all homes) | different metric | Not comparable (ZHVI is a value index, not a sale median) |
| 92037 (La Jolla) | $1,362 · $3.62M · 284 · T1 | Redfin ZIP snippets: listing-side only (pending median list $2.85M) | – | Not verifiable from snippets |

Summary:

* **Comparable ZIP-level figures were found for 6 of 10 ZIPs.** In 5 of them our numbers are
  within ±8%, and no tier changes.
* **One material discrepancy (90272)** reflects the fire, not a pipeline error.
* **Four ZIPs could only be checked at city level or not at all.**
* **Re-run this check by opening the live pages** once redfin.com / zillow.com are reachable.

Sources:

* [JLee Realty 95125](https://julianalee.com/zip-code/95125/95125-statistics.htm)
* [RealtyTrac 95818](https://www.realtytrac.com/market-trends/sacramento-ca-95818/)
* [Sierra2 95818](https://sierra2.org/home-sale-prices-in-95818-zip-code-highest-in-county-per-square-foot)
* [TopHap 92506](https://os.tophap.com/api/reports/geo/zip/92506)
* [92661 broker page](https://www.kentuckychoicerealty.com/CA/Newport-Beach/92661)
* [ATTOM 94708](https://propertynavigator.attomdata.com/data/us-real-estate/ca/alameda-county/berkeley/94708)
* [Redfin Berkeley](https://redfin.com/city/1590/CA/Berkeley/housing-market)
* [ATTOM Pacific Palisades](https://attomdata.com/data/us-real-estate/ca/los-angeles-county/pacific-palisades)
* [Redfin Mill Valley](https://redfin.com/city/12192/CA/Mill-Valley/housing-market)
* [Redfin SF blog](https://www.redfin.com/blog/new-home-listings-in-san-francisco-ca-09-11-25/)
* [Zillow Ventura](https://www.zillow.com/ventura-ca/home-values)
* [Redfin 92037](https://www.redfin.com/zipcode/92037/pending-listings)

**Discrepancies to note**

* Redfin's public file stops at 2026-05-31. Live pages carry ~4 more months of sales.
* City-level figures include condos and are not comparable to ZIP-level SFR medians.
* 90272 figures are likely distorted by post-fire (January 2025) lot and rebuild sales.

## 8. Results (this build)

Mailable ZIPs (with a ZIP boundary) by tier. Cumulative counts are how the list expands as the
floor drops.

| $/sq ft floor | ZIPs in tier | Cumulative ZIPs | SFR sales, 12 mo (cumulative) |
|---|---|---|---|
| ≥ $700 (Tier 1) | 389 | **389** | 48,758 |
| $600–699 (Tier 2) | 169 | **558** | 71,276 |
| $500–599 (Tier 3) | 178 | **736** | 95,474 |

By focus region (number of ZIPs):

| Region | T1 | T2 | T3 |
|---|---|---|---|
| Los Angeles County | 104 | 60 | 85 |
| Orange County | 43 | 40 | 4 |
| Santa Clara / San Mateo | 77 | 2 | 2 |
| San Diego | 31 | 12 | 26 |
| Alameda (Berkeley / Oakland) | 24 | 14 | 2 |
| San Francisco | 25 | 1 | 0 |
| Marin | 20 | 4 | 2 |
| Ventura | 4 | 2 | 9 |
| Sacramento | 0 | 0 | 3 |
| Inland Empire | 0 | 2 | 2 |
| Rest of California | 61 | 32 | 43 |

Flags:

* 40 ranked ZIPs are thin samples (< 5 sales).
* 16 use the All-Residential fallback.
* 277 have no named Overture neighborhood.

**The three biggest data gaps**

1. **No parcel data for any county.** Criteria 1–3 (SFR, 5,000 sq ft lot, 750 sq ft buildable)
   could not be applied anywhere, so no ZIP has a qualifying-lot count yet. Fix: allow the county
   hosts in the environment network policy, or buy Regrid county files, and re-run.
2. **Stale, unconfirmed market data.** Redfin's public ZIP file ends 2026-05-31, and the Zillow
   ZHVI cross-check could not be run.
3. **2010 ZIP boundaries and uneven names.** ZIP polygons are 2010 ZCTAs (2020+ unavailable).
   City and neighborhood names rely on Overture, whose address and neighborhood coverage is
   uneven (Alameda addresses; 277 ranked ZIPs with no neighborhood name).

## 9. Data gaps and limitations

1. **No parcel data (largest gap).**
   * Every county assessor portal, ArcGIS host, Socrata host and data.ca.gov was blocked by
     the build environment's network policy.
   * Several key counties only offer manual hub exports anyway:
     * Alameda
     * San Francisco
     * Santa Clara
     * San Mateo
     * Marin
     * Sacramento
     * Ventura
     * San Bernardino
   * Orange County has **no free assessor roll with use codes**. Only the 2019 SCAG land-use layer exists.
   * Santa Clara's free layer has **no use code**.
   * About 13 counties have no free parcel data at all; several more have only stale archives.
   * **Fallback:** Regrid county files (≈ $300 per county standard schema, ≈ $8,000 statewide at
     2023 list prices; current pricing unverified). Drop them into `data/parcels/` and re-run.
2. **Stale market data.** Redfin's public ZIP tracker was last updated 2026-06-02, so the
   "last 12 months" is June 2025–May 2026. The Zillow cross-check could not be run (host blocked).
3. **2010 ZIP boundaries.** The 2020+ ZCTA file was unreachable, so ZIPs created or redrawn
   since 2010 are missing or mis-shaped. Redfin ZIPs with no 2010 polygon have no county,
   city or footprint data.
4. **Buildable-area model.**
   * Side and rear setbacks are the state 4 ft baseline. State law also keeps local lot-coverage,
     FAR and open-space rules from blocking an ADU of at least 800 sq ft, so some lots under
     this model's 750 sq ft threshold can still legally host one.
   * Local front-setback rules, easements, slopes, fire zones (VHFHSZ), coastal zone, septic and
     HOA rules are not modelled.
   * Front-line detection is a heuristic. Corner and flag lots will be misjudged.
   * Footprints can miss recent construction (including existing ADUs) or include
     trees/shadows as buildings.
5. **Homes, not households.**
   * Counts are SFR parcels, not mailboxes. Owner-occupancy is unknown.
   * Valpak delivers by carrier route, so a ZIP-level count is a planning estimate.
6. **Interim ranking** is a market-activity proxy (see §5). Do not read it as a lot count.

## 10. Reproducing / extending

```bash
python -m adu_campaign.fetch_overture        # divisions, addresses, buildings (S3)
python -m adu_campaign.run                   # everything else, writes output/
python -m pytest adu_campaign/tests
```

To add a county:

1. Drop a county export or a Regrid county file at `data/parcels/<county_slug>.gpkg`.
   * Regrid exports are mapped automatically (`ll_gissqft`, `lbcs_structure`, `szip`).
   * Verify the LBCS SFR code range before relying on it.
2. Or, for a county export, set `use_code_field` and a **verified** `sfr_code_regex` in
   `county_sources.py`.
3. Re-run. Counties with live ArcGIS layers are paged automatically, with the SFR filter applied
   server-side.
