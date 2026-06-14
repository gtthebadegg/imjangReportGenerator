from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def test_build_report_from_minimal_session(tmp_path: Path) -> None:
    session = {
        "session_id": "minimal_test",
        "title": "샘플 임장 기록",
        "region": "샘플시",
        "visit_date": "2026-06-13",
        "photo_folder": "/mnt/d/2026 부동산 스터디/260613 안양/assets/photos",
        "data_source": {"molit_deal_ymd": "202605", "route_buffer_m": 300},
        "data_source_note": "literal </script> must not close the SESSION script",
        "photos": [
            {"id": "photo_1", "filename": "p1.jpg", "lat": 37.39, "lng": 126.95, "timestamp": "2026-06-13T11:00:00"}
        ],
        "neighborhoods": [],
        "apartments": [
            {
                "id": "apt_sample",
                "name": "샘플아파트",
                "address": "샘플시 샘플동 1",
                "lat": 37.394,
                "lng": 126.956,
                "recent_trade_price": "10.0억",
                "data_as_of": "unknown",
                "latest_deal_date": "2026-05-20",
                "kakao_map_link": "https://map.kakao.com/?q=%EC%83%98%ED%94%8C%EC%95%84%ED%8C%8C%ED%8A%B8",
                "google_maps_link": "https://www.google.com/maps/search/%EC%83%98%ED%94%8C%EC%95%84%ED%8C%8C%ED%8A%B8",
            }
        ],
        "facilities": [],
        "news_items": [],
    }
    session_path = tmp_path / "session.json"
    out_path = tmp_path / "report.html"
    session_path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    (tmp_path / "assets" / "photos").mkdir(parents=True)

    cmd = [
        sys.executable,
        "-m",
        "imjang_report.scripts.build_report_v3",
        "--session",
        str(session_path),
        "--out",
        str(out_path),
    ]
    res = subprocess.run(cmd, cwd=Path(__file__).parents[1], text=True, capture_output=True, timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr
    html = out_path.read_text(encoding="utf-8")
    assert "샘플 임장 기록" in html
    assert "imjang_report_v3_data_minimal_test" in html
    assert "202605" in html
    assert "네이버부동산" in html
    assert "실제 지도와<br>맞지 않나요?" in html
    assert "실제 지도와<br>맞지 않습니다" not in html
    assert "function naverLandLinkForApt" in html
    assert "new.land.naver.com/search?ms=" in html
    assert "lat.toFixed(6)" in html
    assert "lng.toFixed(6)" in html
    assert "37.394,126.956,14" not in html
    assert "2026-05-20" in html
    assert "data: unknown" not in html
    assert '\"data_as_of\": \"unknown\"' not in html
    assert "window.SESSION =" in html
    assert "const SESSION = window.SESSION;" in html
    assert "function photoAssetUrl" in html
    assert "function photoOriginalFileUrl" in html
    assert "function photoImgOnError" in html
    assert "id=\"photo-modal-delete-review-btn\"" in html
    assert "function deleteReviewById" in html
    assert "function deleteCurrentPhotoReview" in html
    assert "이 사진의 후기를 삭제하시겠습니까?" in html
    assert "이 아파트 단지의 후기를 삭제하시겠습니까?" in html
    assert "🗑️ 후기 삭제" in html
    assert "file:///" in html and ":/" in html
    assert "^\\/mnt\\/([a-zA-Z])\\/(.*)$" in html
    assert "onerror=\"" in html
    session_start = html.index("window.SESSION =")
    first_close_after_session = html.index("</script>", session_start)
    second_script_after_session = html.index("<script>", session_start + 1)
    assert first_close_after_session < second_script_after_session
    session_block = html[session_start:first_close_after_session]
    assert "literal <\\/script> must not close" in session_block
    assert "REPORT_TITLE_JS" not in html
    assert "임장 기록_JS" not in html
    script_blocks = re.findall(r"<script(?: [^>]*)?>(.*?)</script>", html, re.S)
    assert len(script_blocks) >= 4
    if shutil.which("node"):
        script_path = tmp_path / "report-runtime.js"
        script_path.write_text(script_blocks[-1], encoding="utf-8")
        syntax = subprocess.run(["node", "--check", str(script_path)], text=True, capture_output=True, timeout=30)
        assert syntax.returncode == 0, syntax.stdout + syntax.stderr
