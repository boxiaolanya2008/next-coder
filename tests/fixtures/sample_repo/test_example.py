"""Tests for sample_repo.example (will be expanded by the demo Implementer)."""

from example import Point, make_point


def test_make_point():
    p = make_point(1, 2)
    assert isinstance(p, Point)
    assert p.x == 1
    assert p.y == 2


def test_distance_zero():
    p = make_point(3, 4)
    assert p.distance_to(p) == 0


def test_distance_unit():
    a = make_point(0, 0)
    b = make_point(3, 4)
    assert a.distance_to(b) == 5
