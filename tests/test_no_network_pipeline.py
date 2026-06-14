from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def make_gps_jpeg(path: Path, lat: float, lng: float, dt: str = "2026:06:13 11:00:00") -> None:
    from PIL import Image
    import piexif

    def deg_to_dms(value: float):
        value = abs(value)
        deg = int(value)
        minutes_float = (value - deg) * 60
        minutes = int(minutes_float)
        seconds = round((minutes_float - minutes) * 60 * 10000)
        return ((deg, 1), (minutes, 1), (seconds, 10000))

    img = Image.new("RGB", (80, 60), color=(240, 240, 240))
    exif = {
        "0th": {piexif.ImageIFD.DateTime: dt},
        "Exif": {piexif.ExifIFD.DateTimeOriginal: dt},
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: "N" if lat >= 0 else "S",
            piexif.GPSIFD.GPSLatitude: deg_to_dms(lat),
            piexif.GPSIFD.GPSLongitudeRef: "E" if lng >= 0 else "W",
            piexif.GPSIFD.GPSLongitude: deg_to_dms(lng),
        },
    }
    img.save(path, "jpeg", exif=piexif.dump(exif))


def test_no_network_pipeline_generates_session_and_report(tmp_path: Path) -> None:
    photos = tmp_path / "photos"
    out = tmp_path / "out"
    photos.mkdir()
    make_gps_jpeg(photos / "p1.jpg", 37.3942, 126.9568, "2026:06:13 11:00:00")
    make_gps_jpeg(photos / "p2.jpg", 37.3950, 126.9570, "2026:06:13 11:10:00")

    cmd = [
        sys.executable,
        "-m",
        "imjang_report.scripts.run_pipeline",
        "--photos",
        str(photos),
        "--workdir",
        str(out),
        "--region-hint",
        "테스트시",
        "--lawd-cd",
        "41173",
        "--deal-ymd",
        "202605",
        "--skip-geocode-clusters",
        "--skip-market-data",
    ]
    res = subprocess.run(cmd, cwd=Path(__file__).parents[1], text=True, capture_output=True, timeout=120)
    assert res.returncode == 0, res.stdout + res.stderr

    session_path = out / "session.json"
    report_path = out / "report.html"
    assert session_path.exists()
    assert report_path.exists()
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert len(session["photos"]) == 2
    assert session["data_source"]["route_buffer_m"] == 300.0
    html = report_path.read_text(encoding="utf-8")
    assert "테스트시 임장 기록" in html
    assert "SESSION =" in html
    assert "Leaflet" in html or "leaflet" in html
