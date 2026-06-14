#!/usr/bin/env python3
"""Export an imjang session to a Notion-importable Markdown ZIP.

Notion Markdown import can ingest local relative image links when the .md file
and images/ directory are packaged together in a ZIP. This script creates:

  imjang_notion_import.zip
  ├─ imjang_report.md
  └─ images/
     ├─ 001_IMG_xxx.jpg
     └─ ...

Images are resized/compressed to reduce Notion import failures.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageOps
except Exception as e:  # pragma: no cover
    raise SystemExit("Pillow is required: uv run --with pillow python3 export_notion_md_zip.py ...") from e


def slugify(s: str, max_len: int = 80) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "_", s.strip())
    s = re.sub(r"_+", "_", s).strip("._")
    return (s[:max_len] or "item")


def load_json(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def storage_reviews(storage: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = storage.get("reviews") or {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(v, str):
            out[k] = {"text": v.strip(), "tags": []}
        elif isinstance(v, dict):
            out[k] = {"text": str(v.get("text") or "").strip(), "tags": v.get("tags") or []}
    return out


def fmt_tags(tags: list[str]) -> str:
    clean = [str(t).strip().replace(" ", "_") for t in tags if str(t).strip()]
    return " ".join("#" + t for t in clean)


def money_line(label: str, value: Any) -> str | None:
    if not value:
        return None
    return f"- {label}: {value}"


def copy_resize_image(src: Path, dst: Path, max_width: int, quality: int, max_bytes: int) -> tuple[bool, str]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            w, h = im.size
            if max(w, h) > max_width:
                scale = max_width / float(max(w, h))
                im = im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            # Save as JPEG for predictable Notion import.
            q = quality
            while True:
                im.save(dst, format="JPEG", quality=q, optimize=True, progressive=True)
                if dst.stat().st_size <= max_bytes or q <= 50:
                    break
                q -= 8
            return True, f"resized q={q}"
    except Exception as e:
        # Fallback: copy original if Pillow cannot decode it.
        try:
            shutil.copy2(src, dst)
            return True, f"copied original after pillow error: {e}"
        except Exception as e2:
            return False, f"failed: {e}; copy failed: {e2}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, type=Path)
    ap.add_argument("--storage", type=Path, help="Optional JSON backup from report.html localStorage export")
    ap.add_argument("--photos-dir", type=Path, help="Defaults to SESSION_DIR/assets/photos")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--zip-name", default="imjang_notion_import.zip")
    ap.add_argument("--image-max-px", type=int, default=1600)
    ap.add_argument("--image-quality", type=int, default=82)
    ap.add_argument("--image-max-mb", type=float, default=4.5, help="Target per-image size for Notion free import safety")
    ap.add_argument("--photos", choices=["all", "reviewed"], default="all")
    args = ap.parse_args()

    session = load_json(args.session)
    storage = load_json(args.storage) if args.storage else {}
    reviews = storage_reviews(storage)
    favorite_ids = set(storage.get("favorite_apartments") or [])
    leader_ids = set(storage.get("leader_apartments") or [])
    hidden_ids = set(storage.get("hidden_apartments") or [])

    photos_dir = args.photos_dir or (args.session.parent / "assets" / "photos")
    out = args.out_dir
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True, exist_ok=True)

    # Build deterministic image map.
    image_map: dict[str, str] = {}
    image_logs: list[str] = []
    photos = sorted(session.get("photos") or [], key=lambda p: (p.get("timestamp") or "", p.get("filename") or ""))
    max_bytes = int(args.image_max_mb * 1024 * 1024)

    selected_photos = []
    for idx, p in enumerate(photos, start=1):
        rid = p.get("id") or p.get("filename") or str(idx)
        rev = reviews.get(rid, {})
        if args.photos == "reviewed" and not rev.get("text"):
            continue
        fn = p.get("filename") or ""
        src = photos_dir / fn
        if not src.exists():
            image_logs.append(f"MISSING\t{fn}")
            continue
        stem = slugify(Path(fn).stem, 60)
        dst_name = f"{len(selected_photos)+1:03d}_{stem}.jpg"
        ok, msg = copy_resize_image(src, out / "images" / dst_name, args.image_max_px, args.image_quality, max_bytes)
        if ok:
            image_map[rid] = "images/" + dst_name
            selected_photos.append(p)
        image_logs.append(f"{('OK' if ok else 'FAIL')}\t{fn}\t{dst_name}\t{msg}")

    md: list[str] = []
    title = session.get("title") or "안양 임장 기록"
    visit_date = session.get("visit_date") or session.get("date") or "2026-06-13"
    md += [f"# 🏠 {title}", "", f"- 방문일: {visit_date}", f"- 사진: {len(selected_photos)}장", f"- 아파트: {len(session.get('apartments') or [])}개", f"- 시설: {len(session.get('facilities') or [])}개", ""]

    # First section: neighborhood review. Keep a blank template even when the user has not filled it yet.
    nr = storage.get("neighborhood_review") or {}
    prompts = nr.get("prompts") or {}
    labels = {"atmosphere": "분위기", "commerce": "상권", "transit": "교통", "walkability": "도보", "future": "5년후 전망"}
    md += ["## 🏘️ 동네 총평", "", "### 한줄평", f"> {nr.get('overall') or ''}", "", "### 세부 항목"]
    for k, label in labels.items():
        md.append(f"- **{label}**: {prompts.get(k) or ''}")
    md.append("")

    md += ["## 📷 사진 기록", ""]
    for i, p in enumerate(selected_photos, start=1):
        rid = p.get("id") or p.get("filename") or str(i)
        rev = reviews.get(rid, {})
        ts = (p.get("timestamp") or "").replace("T", " ")[:16]
        heading = ts or p.get("filename") or f"사진 {i}"
        md += [f"### {i}. {heading}", ""]
        if rid in image_map:
            alt = slugify(p.get("filename") or f"photo_{i}")
            md += [f"![{alt}]({image_map[rid]})", ""]
        if p.get("address") or p.get("display_name"):
            md.append(f"- 위치: {p.get('address') or p.get('display_name')}")
        if rev.get("tags"):
            md.append(f"- 태그: {fmt_tags(rev['tags'])}")
        if rev.get("text"):
            md += ["", rev["text"], ""]
        else:
            md.append("")

    apartments = session.get("apartments") or []
    md += ["## 🏢 아파트 단지", ""]
    # Favorites/leaders first if storage is provided, then by route distance/name.
    def apt_key(a: dict[str, Any]):
        aid = a.get("id")
        return (0 if aid in leader_ids else 1, 0 if aid in favorite_ids else 1, a.get("distance_to_route_m") or 999999, a.get("name") or "")
    for a in sorted(apartments, key=apt_key):
        aid = a.get("id")
        if aid in hidden_ids:
            continue
        tags: list[str] = []
        if aid in leader_ids:
            tags.append("대장아파트")
        if aid in favorite_ids:
            tags.append("관심단지")
        tags.extend(a.get("tags") or [])
        rev = reviews.get(aid, {})
        tags.extend(rev.get("tags") or [])
        marker = " 👑" if aid in leader_ids else (" ★" if aid in favorite_ids else "")
        md += [f"### {a.get('name','이름 없음')}{marker}", ""]
        lines = []
        if a.get("address"):
            lines.append(f"- 주소: {a['address']}")
        if a.get("distance_to_route_m") is not None:
            lines.append(f"- 동선 거리: {round(float(a['distance_to_route_m']))}m")
        if a.get("built_year"):
            lines.append(f"- 준공: {a['built_year']}년")
        for line in [money_line("중위 매매", a.get("recent_trade_price")), money_line("중위 전세", a.get("jeonse_price"))]:
            if line:
                lines.append(line)
        if a.get("latest_deal_date"):
            lines.append(f"- 거래 기준: {a['latest_deal_date']}")
        if tags:
            lines.append(f"- 태그: {fmt_tags(tags)}")
        md.extend(lines or ["- 정보 없음"])
        if rev.get("text"):
            md += ["", f"> {rev['text']}"]
        md.append("")

    facilities = session.get("facilities") or []
    if facilities:
        md += ["## 🧭 주요 시설", ""]
        for f in facilities:
            md.append(f"- {f.get('name','시설')} ({f.get('type','')})")
        md.append("")

    news = session.get("news_items") or []
    if news:
        md += ["## 📰 뉴스/호재", ""]
        for n in news[:30]:
            title = n.get("title") or "뉴스"
            url = n.get("url") or n.get("link")
            if url:
                md.append(f"- [{title}]({url})")
            else:
                md.append(f"- {title}")
        md.append("")

    md += ["---", f"Generated: {datetime.now().isoformat(timespec='seconds')}", ""]
    md_path = out / "imjang_report.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    (out / "image_export_log.tsv").write_text("\n".join(image_logs) + "\n", encoding="utf-8")

    zip_path = out.parent / args.zip_name
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(out.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(out))

    print(json.dumps({
        "out_dir": str(out),
        "zip": str(zip_path),
        "markdown": str(md_path),
        "photos_included": len(selected_photos),
        "zip_bytes": zip_path.stat().st_size,
        "max_image_bytes": max((p.stat().st_size for p in (out / 'images').glob('*.jpg')), default=0),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
