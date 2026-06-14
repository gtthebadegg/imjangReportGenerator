from imjang_report.scripts.collect_apartments_near_route import naver_link


def test_naver_link_uses_apartment_coordinates() -> None:
    url = naver_link("평촌더샵센트럴시티", 37.3943219, 126.9638755)
    assert url.startswith("https://new.land.naver.com/search?")
    assert "ms=37.394322,126.963876,17" in url
    assert "query=%ED%8F%89%EC%B4%8C%EB%8D%94%EC%83%B5%EC%84%BC%ED%8A%B8%EB%9F%B4%EC%8B%9C%ED%8B%B0" in url
    assert "37.394,126.956" not in url


def test_naver_link_without_coordinates_has_no_fixed_viewport() -> None:
    url = naver_link("테스트아파트")
    assert "new.land.naver.com/search" in url
    assert "ms=" not in url
    assert "37.394,126.956" not in url
