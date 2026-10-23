# California ADU / Valpak ZIP targeting

Ranks every California ZIP for an ADU direct-mail campaign. A parcel qualifies when it is
single-family, has a lot of at least 5,000 sq ft, and has at least 750 sq ft of estimated
buildable ADU area. ZIPs are tiered by Redfin median sale $/sq ft. See
[`methodology.md`](methodology.md) for every assumption and data gap.

```bash
pip install -r adu_campaign/requirements.txt
python -m adu_campaign.fetch_overture      # footprints, divisions, postal cities (AWS S3, ~20 min)
python -m adu_campaign.run                 # builds output/campaign_zips.xlsx
python -m pytest adu_campaign/tests
```

* All thresholds, setbacks, tiers and weights live in `config.py`.
* County parcel sources live in `county_sources.py`. A county is processed automatically
  when its source is reachable. You can also drop a county export, or a Regrid county file,
  at `data/parcels/<county>.gpkg` (e.g. `los_angeles.gpkg`).
* Large downloads go to `data/` (git-ignored). Set `ADU_DATA_DIR` to put them elsewhere.

Outputs (in `output/`): `campaign_zips.xlsx`, `all_zips.csv`, `source_inventory.csv`, `run_meta.json`.
