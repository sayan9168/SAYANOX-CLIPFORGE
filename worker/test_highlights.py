from highlights import Segment,find_highlights
def test_ranks_non_overlapping_segments():
    xs=[Segment(0,20,"This is a strong complete point!",.9,.8,.8,.7),
        Segment(10,30,"Overlapping weaker point",.2,.2,.2,.2),
        Segment(40,65,"Another useful complete explanation?",.8,.7,.7,.8)]
    out=find_highlights(xs,15,60,3)
    assert out
    assert all(15 <= x["end"]-x["start"] <= 60 for x in out)
