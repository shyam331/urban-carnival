"""Geometry checks for the buildable-area rule on synthetic lots (no real parcel data)."""
from shapely.geometry import box
from shapely import affinity

from adu_campaign.buildable import buildable


def test_rectangular_lot_matches_hand_calculation():
    # 50 ft frontage x 100 ft deep, house 30x50 sitting 20 ft behind the front lot line (y=0).
    lot = box(0, 0, 50, 100)
    house = box(10, 20, 40, 70)
    r = buildable(lot, house, side=4, rear=4, front=15)
    # lot 5000 - house 1500 - front 15*50 - rear 4*50 - sides 2*4*(100-15-4) = 1902
    assert abs(r["est_buildable_sqft"] - 1902) < 1e-6
    assert abs(r["frontage_ft"] - 50) < 1e-9 and abs(r["depth_ft"] - 100) < 1e-9


def test_front_is_side_nearest_house_and_rotation_invariant():
    lot = box(0, 0, 50, 100)
    house_back = box(10, 40, 40, 90)  # house toward the y=100 end -> that end is "front"
    a = buildable(lot, house_back, side=4, rear=4, front=15)
    rot = buildable(affinity.rotate(lot, 33, origin=(0, 0)), affinity.rotate(house_back, 33, origin=(0, 0)), 4, 4, 15)
    assert abs(a["est_buildable_sqft"] - rot["est_buildable_sqft"]) < 1e-3
    # house occupies y 40-90; front strip y 85-100 overlaps house by 5 ft -> 5000-1500-1598+5*30
    assert abs(a["est_buildable_sqft"] - 2052) < 1e-6


def test_small_contiguous_flag():
    # 5,000 sf lot almost filled by the house: two thin leftover strips, none >= 750 sf.
    lot = box(0, 0, 50, 100)
    house = box(4, 15, 46, 90)
    r = buildable(lot, house, side=4, rear=4, front=15)
    assert r["largest_contiguous_sqft"] < 750


def test_vacant_lot_has_no_footprint():
    r = buildable(box(0, 0, 60, 120), None, 4, 4, 15)
    assert r["footprint_sqft"] == 0
    assert abs(r["est_buildable_sqft"] - (52 * (120 - 4 - 15))) < 1e-6
