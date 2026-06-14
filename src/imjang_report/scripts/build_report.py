#!/usr/bin/env python3
"""[결정론] session.json → 단일 HTML report.html 빌드 (v3 템플릿).

v3 필수 UI (15+ 사용자 피드백):
  - Streak inline edit + M/N progress
  - Capture mode with SVG arrows + map follow
  - Photo cluster modal (3-state marker)
  - Apartment card ↔ marker ID mapping
  - CartoDB Voyager (밝은 톤) tile
  - 280px Streak panel (left)
  - 큰 사진 모달 (max-width 900px)
  - 드롭다운 패널 (apt/news 기본 닫힘, total review만 열림)
  - 뉴스 자동 필터링
  - 사용자 뉴스 추가
  - 사용자 마크 추가 (8 emoji 타입)
  - 동네 한줄평 (NeighborhoodReview) + 진행률
  - 거래가격 기준일자
  - 후기 태그
  - MD 추출 (base64 임베드, Notion 업로드용)

사용법 (실전):
    # 작업 디렉토리에 template 복사 후 데이터 placeholder로 사용
    cp scripts/build_report_v3.py <workdir>/
    # workdir에 session.json + assets/photos/ 두고
    python3 build_report_v3.py  # → report.html 생성

⚠️ 단일 HTML 생성 시 Python f-string + JS/CSS의 `{}` 충돌 회피:
  - 일반 string + str.replace('PLACEHOLDER', value) 패턴 사용
  - 이 스킬에서 v3 템플릿이 그 패턴으로 작성됨

결정론 = session.json → HTML 변환, AI 불필요. 매번 같은 결과 보장.

Pitfall: build_report_v3.py는 ~65KB의 큰 파일. workdir로 복사 시점이 부담.
→ 향후 v4에서 scripts/build_report_v3_template.py로 자리표시자만 export하는
  방식 고려. 현재는 cp 패턴.
"""
import sys
import os

if __name__ == '__main__':
    print("build_report.py는 thin wrapper입니다.", file=sys.stderr)
    print("", file=sys.stderr)
    print("v3 템플릿 사용법:", file=sys.stderr)
    print("  1. cp scripts/build_report_v3.py <workdir>/", file=sys.stderr)
    print("  2. cd <workdir> && python3 build_report_v3.py", file=sys.stderr)
    print("  3. 산출물: report.html", file=sys.stderr)
    print("", file=sys.stderr)
    print("또는 직접 호출 (현재 디렉토리에 session.json + assets/photos/ 있을 때):", file=sys.stderr)
    print("  python3 scripts/build_report_v3.py", file=sys.stderr)
    sys.exit(0)
