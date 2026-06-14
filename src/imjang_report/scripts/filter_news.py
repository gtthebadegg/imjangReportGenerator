#!/usr/bin/env python3
"""[결정론] 호재/뉴스 키워드 필터링 — 맛슐랭/안전점검 등 제외.

사용법:
    uv run python3 scripts/filter_news.py \
        --input /tmp/news_all.json \
        --output /tmp/news_filtered.json

또는 stdin:
    cat news.json | uv run python3 scripts/filter_news.py --output filtered.json

입력: {"items": [{"title": ..., "description": ...}, ...]}
출력: 필터링된 items (제목/요약에 제외 키워드 없는 것만)

결정론 = 키워드 매칭만. AI 불필요. 같은 입력 → 같은 결과.

v2_ui_patterns.md §11 "뉴스 자동 필터링 키워드" 패턴.
"""
import argparse
import json
import sys

# v2_ui_patterns.md에서 검증된 제외 키워드 (맛슐랭은 사용자 명시 제외)
EXCLUDED_NEWS_KEYWORDS = [
    '맛슐랭',         # 사용자 명시 제외
    '안전 상황', '안전점검',  # 일반 안전 행정
    '콘크리트',         # 보수/하자 (호재 아님)
    '정체 극심', '출근길',  # 정체 관련
    '치과특화', '동물병원',  # 의료 특화 (사용자 피드백)
    '이전',            # 이전 뉴스
]

def is_excluded(item):
    """item: {title, description, ...} → True if should be excluded"""
    text = (item.get('title', '') + ' ' + item.get('description', '') + ' ' + item.get('summary', '')).lower()
    for kw in EXCLUDED_NEWS_KEYWORDS:
        if kw.lower() in text:
            return True
    return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', help='입력 JSON 경로 (없으면 stdin)')
    parser.add_argument('--output', required=True, help='출력 JSON 경로')
    args = parser.parse_args()

    if args.input:
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    items = data.get('items', data if isinstance(data, list) else [])
    print(f"입력: {len(items)}개", file=sys.stderr)

    filtered = []
    excluded = []
    for it in items:
        if is_excluded(it):
            excluded.append(it.get('title', '')[:50])
        else:
            filtered.append(it)

    print(f"유지: {len(filtered)}개 / 제외: {len(excluded)}개", file=sys.stderr)
    for ex in excluded[:10]:
        print(f"  ✗ {ex}", file=sys.stderr)

    output = data.copy() if isinstance(data, dict) else {}
    if isinstance(output, dict):
        output['items'] = filtered
    else:
        output = filtered

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✓ {args.output} 저장 완료: items={len(filtered)}", file=sys.stderr)

if __name__ == '__main__':
    main()
