from .app import rank_class, rank_label


def test_missing_keyword_rank_is_rendered_safely():
    assert rank_class(None) == "muted"
    assert rank_label(None) == "Not ranked"


def test_numeric_keyword_rank_keeps_visual_status():
    assert rank_class(8) == "good"
    assert rank_class(15) == "warn"
    assert rank_class(25) == "bad"
    assert rank_label(15.3) == "#15.3"
