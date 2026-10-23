"""Per-parcel ADU buildable-area estimate (criterion 3).

Rule, per the brief:
    buildable = lot area
                - existing building footprint
                - 4 ft side and rear setbacks (CA state ADU baseline)
                - front yard (FRONT_SETBACK_FT deep across the frontage)

Parcels are in a projected CRS measured in FEET. Street frontage is not in the data,
so the front lot line is taken as the short side of the parcel's minimum rotated
rectangle that is closest to the existing house (houses usually sit toward the street).
Both an area estimate and the largest contiguous remaining piece are returned; the
latter drives the "likely under 750 sq ft contiguous" flag.
"""
import numpy as np
import shapely
from shapely.geometry import Polygon

from . import config as C


def _front_strip(parcel, house_centroid, depth):
    """Rectangle `depth` ft deep along the short MRR side nearest the house."""
    mrr = parcel.minimum_rotated_rectangle
    if mrr.geom_type != "Polygon":
        return Polygon()
    pts = np.asarray(mrr.exterior.coords)[:4]
    edges = [(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    lens = [np.hypot(*(b - a)) for a, b in edges]
    short = sorted(range(4), key=lambda i: lens[i])[:2]
    ref = np.asarray(house_centroid.coords[0]) if house_centroid is not None else None
    if ref is not None:
        short.sort(key=lambda i: np.hypot(*((edges[i][0] + edges[i][1]) / 2 - ref)))
    a, b = edges[short[0]]
    centre = pts.mean(axis=0)
    mid = (a + b) / 2
    inward = centre - mid
    n = np.linalg.norm(inward)
    if n == 0:
        return Polygon()
    inward = inward / n * depth
    return Polygon([a, b, b + inward, a + inward])


def frontage_depth(parcel):
    mrr = parcel.minimum_rotated_rectangle
    if mrr.geom_type != "Polygon":
        return 0.0, 0.0
    pts = np.asarray(mrr.exterior.coords)[:4]
    s = sorted(np.hypot(*(pts[(i + 1) % 4] - pts[i])) for i in range(2))
    return float(s[0]), float(s[1])


def buildable(parcel, footprint, side=None, rear=None, front=None, separation=None):
    """Return dict(lot_sqft, footprint_sqft, frontage_ft, depth_ft, setback_sqft,
    est_buildable_sqft, largest_contiguous_sqft)."""
    side = C.SIDE_SETBACK_FT if side is None else side
    rear = C.REAR_SETBACK_FT if rear is None else rear
    front = C.FRONT_SETBACK_FT if front is None else front
    separation = C.BUILDING_SEPARATION_FT if separation is None else separation
    parcel = shapely.make_valid(parcel)
    fp = shapely.make_valid(footprint).intersection(parcel) if footprint is not None and not footprint.is_empty else Polygon()

    # Side and rear setbacks: inward buffer of the larger of the two applies all round,
    # then the front yard strip (measured from the front lot line) is removed.
    envelope = parcel.buffer(-max(side, rear), join_style="mitre")
    strip = _front_strip(parcel, fp.centroid if not fp.is_empty else None, front)
    envelope = envelope.difference(strip)
    blocked = fp.buffer(separation, join_style="mitre") if separation > 0 else fp
    avail = envelope.difference(blocked)

    parts = getattr(avail, "geoms", [avail])
    largest = max((p.area for p in parts if p.geom_type == "Polygon"), default=0.0)
    w, d = frontage_depth(parcel)
    lot = parcel.area
    return {
        "lot_sqft_geom": lot,
        "footprint_sqft": fp.area,
        "frontage_ft": w,
        "depth_ft": d,
        "setback_sqft": lot - parcel.buffer(-max(side, rear), join_style="mitre").difference(strip).area,
        "est_buildable_sqft": max(avail.area, 0.0),
        "largest_contiguous_sqft": largest,
    }
