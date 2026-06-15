#!/usr/bin/env python3
"""[결정론] 부동산 임장 자동 정리 end-to-end 파이프라인 초안.

사용자 필수 입력은 사진 폴더 절대경로뿐이다.
동선 캡처 이미지는 받지 않는다. 사진 GPS를 기준으로 동선을 만들고,
기본 buffer 300m 내 MOLIT 실거래 아파트와 Kakao POI-only 아파트를 자동 수집한다.

사용법 예시:
  uv run python3 scripts/run_pipeline.py \
    --photos /absolute/path/to/photos \
    --workdir ./out/anyang-auto \
    --region-hint 안양 \
    --lawd-cd 41171 \
    --lawd-cd 41173 \
    --deal-ymd 202605

산출물:
  <workdir>/session.json
  <workdir>/trade_*.json, rent_*.json
  <workdir>/near_route_apartments_audit.json
  <workdir>/kakao_geocode_audit.json (선택 단계)
  <workdir>/report.html

주의:
  - 기본 report builder는 scripts/build_report_v3.py를 사용한다.
  - Notion 업로드는 이 파이프라인에서 제외한다.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("\n$ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def python_cmd() -> list[str]:
    """Run with the current Python interpreter. Install dependencies via pyproject/requirements first."""
    return [sys.executable]


def py_script(name: str) -> str:
    return str(SCRIPT_DIR / name)


def init_session(workdir: Path, photos: Path, region_hint: str, lawd_codes: list[str], deal_ymd: str, buffer_m: float) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    session_path = workdir / "session.json"
    if not session_path.exists():
        session = {
            "session_id": workdir.name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "photo_folder": str(photos),
            "region": region_hint,
            "lawd_codes": lawd_codes,
            "data_source": {
                "molit_deal_ymd": deal_ymd,
                "route_buffer_m": buffer_m,
                "route_source": "photo_gps",
            },
            "photos": [],
            "neighborhoods": [],
            "apartments": [],
            "facilities": [],
            "news_items": [],
            "reviews": {},
            "neighborhood_review": {},
            "user_news": [],
            "user_marks": [],
            "user_marks_counter": 0,
        }
        session_path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    return session_path


def copy_photos_for_html(session_path: Path, photos: Path, workdir: Path) -> None:
    # build_report_v3.py expects assets/photos/<filename> for relative display.
    assets = workdir / "assets" / "photos"
    assets.mkdir(parents=True, exist_ok=True)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    copied = 0
    for p in session.get("photos", []):
        fn = p.get("filename")
        if not fn:
            continue
        src = photos / fn
        dst = assets / fn
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            copied += 1
        # Keep abs_path for MD/file references.
        p.setdefault("abs_path", str(src))
    session_path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"copied photos for HTML: {copied} new files -> {assets}")


def append_market_data_warnings(session_path: Path, warnings: list[dict]) -> None:
    if not warnings:
        return
    session = json.loads(session_path.read_text(encoding="utf-8"))
    ds = session.get("data_source")
    if not isinstance(ds, dict):
        ds = {"legacy_data_source": ds}
    ds["market_data_warnings"] = warnings
    session["data_source"] = ds
    session_path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_report_builder(src: Path, workdir: Path, session_path: Path) -> Path:
    """Copy current v3 builder and rewrite hard-coded workdir paths."""
    dst = workdir / "build_report_v3.py"
    text = src.read_text(encoding="utf-8")
    text = text.replace("'/tmp/imjang_<date>_<slug>/session.json'", repr(str(session_path)))
    text = text.replace("'/tmp/imjang_<date>_<slug>/report.html'", repr(str(workdir / "report.html")))
    dst.write_text(text, encoding="utf-8")
    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", required=True, help="사진 폴더 절대경로")
    ap.add_argument("--workdir", required=True, help="작업/산출물 디렉토리")
    ap.add_argument("--region-hint", required=True, help="예: 안양")
    ap.add_argument("--lawd-cd", action="append", required=True, help="시군구 법정동코드 앞 5자리. repeatable")
    ap.add_argument("--deal-ymd", required=True, help="YYYYMM")
    ap.add_argument("--buffer-m", type=float, default=300.0)
    ap.add_argument("--cluster-radius-km", type=float, default=0.3)
    ap.add_argument("--skip-geocode-clusters", action="store_true", help="Nominatim 역지오코딩 생략")
    ap.add_argument("--build-report-script", help="build_report_v3.py 경로. 생략 시 scripts/build_report_v3.py 사용")
    ap.add_argument("--skip-report", action="store_true")
    ap.add_argument("--skip-market-data", action="store_true", help="API 호출(MOLIT/Kakao) 없이 사진/GPS/HTML만 생성")
    args = ap.parse_args()

    photos = Path(args.photos).expanduser().resolve()
    workdir = Path(args.workdir).expanduser().resolve()
    if not photos.is_dir():
        raise SystemExit(f"photos directory not found: {photos}")

    session_path = init_session(workdir, photos, args.region_hint, args.lawd_cd, args.deal_ymd, args.buffer_m)

    run(python_cmd() + [py_script("extract_photo_gps.py"), "--photos", str(photos), "--session", str(session_path)])
    session_after_extract = json.loads(session_path.read_text(encoding="utf-8"))
    if len(session_after_extract.get("photos", [])) < 2:
        raise SystemExit("GPS photos < 2 after extraction. Check photo folder / EXIF / Pillow support.")

    cluster_cmd = [sys.executable, py_script("cluster_photos.py"), "--session", str(session_path), "--radius", str(args.cluster_radius_km)]
    if args.skip_geocode_clusters:
        cluster_cmd.append("--no-geocode")
    run(cluster_cmd)

    if args.skip_market_data:
        print("\nSKIP market data: MOLIT/Kakao API collection disabled")
        session = json.loads(session_path.read_text(encoding="utf-8"))
        session.setdefault("apartments", [])
        session.setdefault("facilities", [])
        session.setdefault("news_items", [])
        session_path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        trade_paths = []
        rent_paths = []
        market_data_warnings = []
        for lawd in args.lawd_cd:
            trade = workdir / f"trade_{lawd}_{args.deal_ymd}.json"
            rent = workdir / f"rent_{lawd}_{args.deal_ymd}.json"
            try:
                run([sys.executable, py_script("fetch_molit.py"), "fetch", "--lawd-cd", lawd, "--deal-ymd", args.deal_ymd, "--kind", "trade", "--out", str(trade)])
                trade_paths.append(trade)
            except subprocess.CalledProcessError as e:
                market_data_warnings.append({
                    "lawd_cd": lawd,
                    "deal_ymd": args.deal_ymd,
                    "kind": "trade",
                    "command": [str(x) for x in e.cmd],
                    "returncode": e.returncode,
                })
                print(f"[warn] trade fetch failed for {lawd} {args.deal_ymd}; continue with Kakao POI-only apartments", file=sys.stderr)

            try:
                run([sys.executable, py_script("fetch_molit.py"), "fetch", "--lawd-cd", lawd, "--deal-ymd", args.deal_ymd, "--kind", "rent", "--source", "proxy", "--out", str(rent)])
                rent_paths.append(rent)
            except subprocess.CalledProcessError as e:
                market_data_warnings.append({
                    "lawd_cd": lawd,
                    "deal_ymd": args.deal_ymd,
                    "kind": "rent",
                    "command": [str(x) for x in e.cmd],
                    "returncode": e.returncode,
                })
                print(f"[warn] rent fetch failed for {lawd} {args.deal_ymd}; continue without rent prices", file=sys.stderr)

        if market_data_warnings:
            (workdir / "market_data_warnings.json").write_text(json.dumps(market_data_warnings, ensure_ascii=False, indent=2), encoding="utf-8")
            append_market_data_warnings(session_path, market_data_warnings)

        collect_cmd = [
            sys.executable, py_script("collect_apartments_near_route.py"),
            "--session", str(session_path),
            "--buffer-m", str(args.buffer_m),
            "--region-hint", args.region_hint,
            "--audit", str(workdir / "near_route_apartments_audit.json"),
        ]
        for p in trade_paths:
            collect_cmd += ["--trade-json", str(p)]
        for p in rent_paths:
            collect_cmd += ["--rent-json", str(p)]
        run(collect_cmd)

        try:
            run([
                sys.executable,
                py_script("enrich_naver_complexes.py"),
                "--session", str(session_path),
                "--cache", str(workdir / "naver_complex_cache.json"),
                "--audit", str(workdir / "naver_complex_audit.json"),
            ])
        except subprocess.CalledProcessError as e:
            print(f"[warn] naver complex lookup failed; keep search-link fallback: rc={e.returncode}", file=sys.stderr)

    # 자동 대장아파트 판단은 제거됨.
    # 대장아파트는 report.html에서 사용자가 직접 체크하고 localStorage/JSON/MD/Notion export에 반영한다.

    copy_photos_for_html(session_path, photos, workdir)

    if not args.skip_report:
        src = Path(args.build_report_script).expanduser().resolve() if args.build_report_script else (SCRIPT_DIR / "build_report_v3.py")
        if not src.exists():
            raise SystemExit(f"build report script not found: {src}")
        run([sys.executable, str(src), "--session", str(session_path), "--out", str(workdir / "report.html")], cwd=workdir)

    print("\nDONE")
    print(f"session: {session_path}")
    if (workdir / "report.html").exists():
        print(f"report: {workdir / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
