from imjang_report.scripts.collect_apartments_near_route import is_apartment_doc


def test_is_apartment_doc_filters_auxiliary_pois() -> None:
    cat = "부동산 > 주거시설 > 아파트"
    assert is_apartment_doc({"category_name": cat, "place_name": "평촌더샵센트럴시티"})
    assert not is_apartment_doc({"category_name": cat, "place_name": "안양역푸르지오더샵아파트 커뮤니티센터"})
    assert not is_apartment_doc({"category_name": cat, "place_name": "하이트타운아파트103동"})
    assert not is_apartment_doc({"category_name": cat, "place_name": "대도 B동"})
    assert not is_apartment_doc({"category_name": cat, "place_name": "어떤아파트 관리사무소"})
