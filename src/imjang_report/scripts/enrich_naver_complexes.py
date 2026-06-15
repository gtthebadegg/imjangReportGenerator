#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def norm_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(ch for ch in text if ch.isalnum() or ord(ch) >= 128)


def norm_name(value: Any) -> str:
    return norm_text(value).replace("아파트", "")


def as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def walk_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_dicts(item)


def first_non_empty(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", []):
            return value
    return None


def extract_coords(node: dict[str, Any]) -> tuple[float | None, float | None]:
    direct_pairs = [
        (node.get("lat"), node.get("lng")),
        (node.get("latitude"), node.get("longitude")),
        (node.get("y"), node.get("x")),
    ]
    for lat_v, lng_v in direct_pairs:
        lat = as_float(lat_v)
        lng = as_float(lng_v)
        if lat is not None and lng is not None:
            return lat, lng
    for child in walk_dicts(node):
        if child is node:
            continue
        for lat_v, lng_v in [
            (child.get("lat"), child.get("lng")),
            (child.get("latitude"), child.get("longitude")),
            (child.get("y"), child.get("x")),
        ]:
            lat = as_float(lat_v)
            lng = as_float(lng_v)
            if lat is not None and lng is not None:
                return lat, lng
    return None, None


def extract_candidates(payload: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in walk_dicts(payload):
        complex_no = first_non_empty(node, ["complexNumber", "complexNo", "complexId", "complex_id"])
        if complex_no in (None, ""):
            continue
        complex_no = str(complex_no)
        if complex_no in seen:
            continue
        seen.add(complex_no)
        lat, lng = extract_coords(node)
        out.append(
            {
                "complex_no": complex_no,
                "complex_name": first_non_empty(node, ["complexName", "complexNm", "name", "title"]),
                "legal_division_name": first_non_empty(node, ["legalDivisionName", "umdNm", "dongName", "address"]),
                "address_text": first_non_empty(node, ["address", "fullAddress", "roadAddress", "detailAddress", "jibunAddress"]),
                "lat": lat,
                "lng": lng,
                "raw": node,
            }
        )
    return out


def score_candidate(apt: dict[str, Any], cand: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    apt_name = norm_name(apt.get("name"))
    cand_name = norm_name(cand.get("complex_name"))
    if apt_name and cand_name:
        if apt_name == cand_name:
            score += 120
            reasons.append("name_exact")
        elif apt_name in cand_name or cand_name in apt_name:
            score += 70
            reasons.append("name_partial")

    apt_addr = norm_text(apt.get("address"))
    legal = norm_text(cand.get("legal_division_name"))
    addr_text = norm_text(cand.get("address_text"))
    if legal and apt_addr and legal in apt_addr:
        score += 25
        reasons.append("legal_in_address")
    if addr_text and apt_addr:
        overlap_bonus = 0
        for token in [apt.get("name"), apt.get("address"), apt.get("road_address")]:
            tok = norm_text(token)
            if tok and tok in addr_text:
                overlap_bonus += 10
        if overlap_bonus:
            score += min(overlap_bonus, 20)
            reasons.append("address_overlap")

    apt_lat = as_float(apt.get("lat"))
    apt_lng = as_float(apt.get("lng"))
    cand_lat = as_float(cand.get("lat"))
    cand_lng = as_float(cand.get("lng"))
    if None not in (apt_lat, apt_lng, cand_lat, cand_lng):
        assert apt_lat is not None and apt_lng is not None and cand_lat is not None and cand_lng is not None
        dist_km = haversine_km(apt_lat, apt_lng, cand_lat, cand_lng)
        if dist_km <= 0.1:
            score += 40
            reasons.append("dist_lt_100m")
        elif dist_km <= 0.3:
            score += 25
            reasons.append("dist_lt_300m")
        elif dist_km <= 1.0:
            score += 10
            reasons.append("dist_lt_1km")
        elif dist_km > 5.0:
            score -= 30
            reasons.append("dist_gt_5km")
    return score, reasons


def fetch_autocomplete(keyword: str, timeout: int = 20) -> Any:
    url = (
        "https://fin.land.naver.com/front-api/v1/search/autocomplete/complexes"
        f"?keyword={urllib.parse.quote(keyword)}&size=10&page=0"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://fin.land.naver.com/",
        "Origin": "https://fin.land.naver.com",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Enrich apartments with Naver complex ids for fin.land deeplinks")
    ap.add_argument("--session", required=True)
    ap.add_argument("--cache")
    ap.add_argument("--audit")
    ap.add_argument("--sleep-seconds", type=float, default=0.7)
    ap.add_argument("--min-score", type=float, default=70.0)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    session_path = Path(args.session)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    apartments = session.get("apartments", [])
    if not isinstance(apartments, list):
        raise SystemExit("session.apartments must be a list")

    cache_path = Path(args.cache) if args.cache else (session_path.parent / "naver_complex_cache.json")
    cache = load_cache(cache_path)
    warnings: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    matched = 0
    attempted = 0
    rate_limited = False

    for apt in apartments:
        if not isinstance(apt, dict):
            continue
        if apt.get("naver_complex_no") and not args.force:
            audit_rows.append({"name": apt.get("name"), "status": "kept_existing", "naver_complex_no": apt.get("naver_complex_no")})
            continue
        if args.limit is not None and attempted >= args.limit:
            audit_rows.append({"name": apt.get("name"), "status": "skipped_limit"})
            continue

        name = str(apt.get("name") or "").strip()
        if not name:
            continue
        cache_key = norm_name(name)
        cached = cache.get(cache_key)
        attempted += 1

        if rate_limited:
            audit_rows.append({"name": name, "status": "skipped_after_rate_limit"})
            continue

        try:
            if cached is None or args.force:
                payload = fetch_autocomplete(name)
                candidates = extract_candidates(payload)
                cache[cache_key] = {"fetched_at": time.time(), "candidates": candidates}
                save_cache(cache_path, cache)
                if args.sleep_seconds > 0:
                    time.sleep(args.sleep_seconds)
            else:
                candidates = cached.get("candidates", [])
        except urllib.error.HTTPError as e:
            warning = {"name": name, "status": "http_error", "code": e.code, "message": str(e)}
            warnings.append(warning)
            audit_rows.append(warning)
            if e.code == 429:
                rate_limited = True
            continue
        except Exception as e:
            warning = {"name": name, "status": "lookup_error", "message": str(e)}
            warnings.append(warning)
            audit_rows.append(warning)
            continue

        scored = []
        for cand in candidates:
            score, reasons = score_candidate(apt, cand)
            cand_view = {
                "complex_no": cand.get("complex_no"),
                "complex_name": cand.get("complex_name"),
                "legal_division_name": cand.get("legal_division_name"),
                "address_text": cand.get("address_text"),
                "lat": cand.get("lat"),
                "lng": cand.get("lng"),
                "score": round(score, 2),
                "reasons": reasons,
            }
            scored.append(cand_view)
        scored.sort(key=lambda row: row["score"], reverse=True)
        best = scored[0] if scored else None
        if best and best["score"] >= args.min_score and best.get("complex_no"):
            apt["naver_complex_no"] = str(best["complex_no"])
            if best.get("complex_name"):
                apt["naver_complex_name"] = best["complex_name"]
            apt["naver_complex_match_score"] = best["score"]
            apt["naver_complex_match_reasons"] = best["reasons"]
            matched += 1
            audit_rows.append({"name": name, "status": "matched", "best": best, "candidate_count": len(scored)})
        else:
            audit_rows.append({
                "name": name,
                "status": "no_match",
                "candidate_count": len(scored),
                "best": best,
            })

    ds = session.get("data_source")
    if not isinstance(ds, dict):
        ds = {"legacy_data_source": ds}
    ds["naver_complex_lookup"] = {
        "method": "fin_land_autocomplete_complexes",
        "attempted": attempted,
        "matched": matched,
        "warnings": warnings,
        "rate_limited": rate_limited,
        "cache_path": str(cache_path),
    }
    session["data_source"] = ds
    session_path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.audit:
        Path(args.audit).write_text(json.dumps({
            "summary": ds["naver_complex_lookup"],
            "rows": audit_rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"naver complex lookup: attempted={attempted} matched={matched} warnings={len(warnings)} rate_limited={rate_limited}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
