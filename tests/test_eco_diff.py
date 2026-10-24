from models.pickplace import PickPlaceComponent
from models.review import ReviewRecord
from services.eco_diff import compare_revisions


def _rec(des, mpn="", x=0.0, y=0.0, rot=0.0, new_x=None, block=0):
    return ReviewRecord(designator=des, mpn=mpn, layer="Top",
                        old_x=x, old_y=y, old_rotation=rot,
                        new_x=new_x, status="Pending", block=block)


def _comp(des, mpn="", x=0.0, y=0.0, rot=0.0):
    return PickPlaceComponent(designator=des, mpn=mpn, layer="Top",
                              x=x, y=y, rotation=rot)


def test_added_removed():
    old = [_rec("C1"), _rec("C2")]
    new = [_comp("C2"), _comp("C3", mpn="M")]
    diff = compare_revisions(old, new)
    assert [a.designator for a in diff.added] == ["C3"]
    assert diff.added[0].mpn == "M"
    assert [r.designator for r in diff.removed] == ["C1"]
    assert not diff.moved and not diff.mpn_changed
    assert not diff.is_empty
    assert diff.counts == (1, 1, 0, 0)


def test_moved_and_tolerances():
    old = [_rec("C1", x=10.0, y=20.0, rot=0.0)]
    # inside tolerance -> no moved
    diff = compare_revisions(old, [_comp("C1", x=10.005, y=20.0, rot=0.5)])
    assert not diff.moved
    # outside move tol
    diff = compare_revisions(old, [_comp("C1", x=10.5, y=20.0, rot=0.0)])
    assert len(diff.moved) == 1
    assert diff.moved[0].dx == 0.5
    # outside rot tol only
    diff = compare_revisions(old, [_comp("C1", x=10.0, y=20.0, rot=5.0)])
    assert len(diff.moved) == 1
    assert diff.moved[0].drot == 5.0


def test_rotation_wraps_around():
    old = [_rec("C1", rot=359.0)]
    diff = compare_revisions(old, [_comp("C1", rot=1.0)], rot_tol_deg=1.0)
    assert len(diff.moved) == 1  # 2° circular distance exceeds 1° tol
    assert diff.moved[0].drot == 2.0
    diff = compare_revisions(old, [_comp("C1", rot=359.5)], rot_tol_deg=1.0)
    assert not diff.moved  # 0.5° circular distance within tol


def test_mpn_changed_only_when_both_present():
    old = [_rec("C1", mpn="M-A"), _rec("C2", mpn="")]
    new = [_comp("C1", mpn="m-a"), _comp("C2", mpn="M-B")]
    diff = compare_revisions(old, new)
    assert not diff.mpn_changed  # case-insensitive equal / empty old
    diff = compare_revisions([_rec("C1", mpn="M-A")], [_comp("C1", mpn="M-B")])
    assert [(m.designator, m.old_mpn, m.new_mpn) for m in diff.mpn_changed] == [
        ("C1", "M-A", "M-B")]


def test_effective_values_and_case_insensitive():
    old = [_rec("c1", x=1.0, new_x=9.0)]
    new = [_comp("C1", x=9.0)]
    diff = compare_revisions(old, new)
    assert not diff.moved and not diff.added and not diff.removed


def test_panelize_blocks_ignored():
    old = [_rec("C1", block=0), _rec("C1_2", block=1)]
    new = [_comp("C1"), _comp("C1_2")]
    diff = compare_revisions(old, new)
    assert [a.designator for a in diff.added] == ["C1_2"]
    assert not diff.removed


def test_empty_diff():
    diff = compare_revisions([], [])
    assert diff.is_empty
    assert diff.counts == (0, 0, 0, 0)


def test_duplicates_tracked_but_not_listed_as_added():
    old = [_rec("C1"), _rec("C2")]
    new = [_comp("C1"), _comp("C1", x=1.0), _comp("C2")]
    diff = compare_revisions(old, new)
    assert not diff.added and not diff.removed
    assert [(d.designator, d.side, d.count) for d in diff.new_duplicates] == [
        ("C1", "new", 2)]
    assert diff.old_unique == 2
    assert diff.new_unique == 2
    assert not diff.is_empty  # duplicates alone open the dialog
    assert diff.duplicate_count == 1


def test_old_duplicates_tracked():
    old = [_rec("C1"), _rec("C1", x=5.0)]
    diff = compare_revisions(old, [_comp("C1")])
    assert [(d.designator, d.side, d.count) for d in diff.old_duplicates] == [
        ("C1", "old", 2)]
    assert diff.old_unique == 1
