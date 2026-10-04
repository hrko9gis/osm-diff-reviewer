from dataclasses import replace

import pytest
from qgis.PyQt.QtCore import Qt

from osm_diff_reviewer.core import review
from osm_diff_reviewer.core.review import ReviewRow
from osm_diff_reviewer.gui.review_model import COLUMNS, ReviewFilterProxy, ReviewTableModel


def _row(ref_key, classification="attribute_diff", status=review.UNREVIEWED, recheck=False, score=0.5):
    return ReviewRow(
        run_id=1,
        source_name="src",
        ref_key=ref_key,
        osm_type="node",
        osm_id=1,
        osm_version=1,
        classification=classification,
        distance_m=1.0,
        shape_score=0.9,
        attribute_score=0.1,
        total_score=score,
        alternatives="",
        attribute_details="[]",
        ref_hash="h",
        ref_attributes={},
        osm_tags={},
        ref_wkt="POINT(139.7 35.68)",
        osm_wkt="POINT(139.7 35.68)",
        status=status,
        note="",
        needs_recheck=recheck,
    )


@pytest.fixture()
def models(qgis_app):
    rows = [
        _row("A", "match", score=0.9),
        _row("B", "missing", score=0.0),
        _row("C", status=review.NOT_NEEDED_OSM),
        _row("D", status=review.NOT_NEEDED_OSM, recheck=True, score=0.7),
        _row("E", status=review.ON_HOLD, score=0.3),
    ]
    model = ReviewTableModel()
    model.set_rows(rows)
    proxy = ReviewFilterProxy()
    proxy.setSourceModel(model)
    return model, proxy


def _keys(proxy):
    return [proxy.row_at(proxy.index(i, 0)).ref_key for i in range(proxy.rowCount())]


def test_default_view_hides_matches_and_not_needed(models):
    _, proxy = models
    assert _keys(proxy) == ["B", "D", "E"]


def test_show_hidden_and_matches(models):
    _, proxy = models
    proxy.set_show_hidden(True)
    proxy.set_show_matches(True)
    assert _keys(proxy) == ["A", "B", "C", "D", "E"]


def test_filter_by_classification_status_and_recheck(models):
    _, proxy = models
    proxy.set_classification("missing")
    assert _keys(proxy) == ["B"]
    proxy.set_classification(None)
    proxy.set_status(review.ON_HOLD)
    assert _keys(proxy) == ["E"]
    proxy.set_status(None)
    proxy.set_recheck_only(True)
    assert _keys(proxy) == ["D"]


def test_classification_filter_overrides_hide_matches(models):
    _, proxy = models
    proxy.set_classification("match")
    assert _keys(proxy) == ["A"]


def test_sort_by_score_is_numeric(models):
    _, proxy = models
    proxy.sort(COLUMNS.index("total_score"), Qt.SortOrder.DescendingOrder)
    assert _keys(proxy) == ["D", "E", "B"]


def test_display_text_and_replace_row(models):
    model, _ = models
    status_column = COLUMNS.index("status")
    recheck_column = COLUMNS.index("needs_recheck")
    assert model.data(model.index(3, recheck_column)) != ""
    model.replace_row(4, replace(model.row(4), status=review.DONE))
    assert model.data(model.index(4, status_column)) == review.status_label(review.DONE)
    assert model.headerData(0, Qt.Orientation.Horizontal) is not None
