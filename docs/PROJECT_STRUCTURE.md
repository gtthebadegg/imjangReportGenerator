# GitHub 배포용 프로젝트 구조

```text
imjang-report/
  README.md
  LICENSE
  pyproject.toml
  requirements.txt
  requirements-dev.txt
  .env.example
  .gitignore

  src/imjang_report/
    __init__.py
    scripts/
      check_setup.py                    # Python/패키지/API 키 사전 점검
      run_pipeline.py                   # end-to-end 실행 진입점
      extract_photo_gps.py              # 사진 EXIF GPS 추출
      cluster_photos.py                 # GPS 클러스터링 / 선택적 역지오코딩
      fetch_molit.py                    # MOLIT/data.go.kr 실거래 조회
      collect_apartments_near_route.py  # 동선 주변 아파트/Kakao POI 병합
      geocode_kakao.py                  # Kakao Local 좌표 보정
      geocode_vworld.py                 # VWorld 좌표 fallback
      build_report_v3.py                # report.html 생성
      export_notion_md_zip.py           # Notion ZIP 생성
      filter_news.py                    # 뉴스 필터링 유틸
      score_apartments.py               # deprecated no-op. 대장 자동선정 금지

  tests/
    test_no_network_pipeline.py         # API 없이 synthetic GPS 사진으로 pipeline 검증
    test_build_report.py                # minimal session → report.html 검증

  docs/
    PYTHON_GUIDE.md
    HERMES_AGENT.md
    API_KEYS_AND_PREFLIGHT.md
    HERMES_SKILL.md                     # 원본 skill 문서 복사본
    ... 운영/교훈 reference 문서

  skills/hermes/real-estate-site-visit/
    SKILL.md                            # Hermes skill 설치용

  examples/
    README.md                           # 예시 실행 안내
```

## 배포 전 체크리스트

- [ ] `.env`, 실제 API 키, 개인 사진, 개인 `session.json`이 git에 포함되지 않는다.
- [ ] `python3 -m py_compile src/imjang_report/scripts/*.py` 통과
- [ ] `python -m imjang_report.scripts.check_setup` 통과
- [ ] `pytest -q` 통과
- [ ] README의 Python 실행 경로가 실제로 동작한다.
- [ ] Agent 가이드가 Python 가이드와 같은 명령을 사용한다.
- [ ] API 키 없는 사용자가 `--skip-market-data`로 최소 테스트를 할 수 있다.
- [ ] 대장아파트 자동 선정이 다시 들어가지 않았다.
