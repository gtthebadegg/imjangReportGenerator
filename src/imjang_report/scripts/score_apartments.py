#!/usr/bin/env python3
"""Deprecated: 대장아파트 자동 선정 제거.

이 스크립트는 더 이상 대장아파트를 계산하거나 `is_daejang=True`를 설정하지 않는다.
대장아파트는 생성된 report.html에서 사용자가 직접 체크하며, 해당 값은
localStorage의 `leader_apartments[]` 및 JSON/Markdown/Notion export에 반영된다.

호환성을 위해 파일은 남겨두되, 실행 시 기존 자동 대장 플래그만 제거하고 종료한다.
"""
import argparse
import json
import pathlib
import sys


def main():
    ap = argparse.ArgumentParser(description="Deprecated no-op: manual leader apartment selection only")
    ap.add_argument("--session", required=True, help="session.json path")
    args = ap.parse_args()
    path = pathlib.Path(args.session)
    session = json.loads(path.read_text(encoding="utf-8"))
    apartments = session.get("apartments", [])
    cleared = 0
    for apt in apartments:
        if apt.get("is_daejang"):
            cleared += 1
        apt["is_daejang"] = False
        apt["score"] = 0
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"deprecated score_apartments.py: automatic leader selection disabled; cleared={cleared}", file=sys.stderr)


if __name__ == "__main__":
    main()
