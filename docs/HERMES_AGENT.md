# Agent / Hermes 실행 가이드

이 저장소는 agent가 실행해도 되고, 사람이 Python만 직접 실행해도 되도록 구성되어 있습니다.

## Agent에게 맡길 때의 원칙

Agent는 다음 순서로 실행해야 합니다.

1. `README.md`, `docs/PYTHON_GUIDE.md`, 이 문서를 읽습니다.
2. `python -m imjang_report.scripts.check_setup`으로 로컬 Python/패키지/API 키 상태를 점검합니다.
3. API 키가 없으면 사용자에게 어떤 키가 부족한지 redacted 없이 이름만 알려줍니다.
4. 사진 폴더, 지역 힌트, 법정동 코드, 거래월을 확인합니다.
5. `python -m imjang_report.scripts.run_pipeline ...`로 실행합니다.
6. `report.html`과 `session.json`이 실제 생성됐는지 확인합니다.
7. 필요하면 `export_notion_md_zip.py`로 Notion ZIP을 생성합니다.

## Hermes skill 설치

```bash
mkdir -p ~/.hermes/skills/real-estate-site-visit
cp skills/hermes/real-estate-site-visit/SKILL.md ~/.hermes/skills/real-estate-site-visit/SKILL.md
```

설치 후 Hermes에게 다음처럼 요청합니다.

```text
부동산 임장 기록 시작하자.
사진 폴더는 /absolute/path/to/photos 이고,
지역 힌트는 안양,
법정동 코드는 41171, 41173,
거래월은 202605야.
먼저 imjang-report 저장소의 check_setup을 실행해서 키/라이브러리를 점검하고,
순수 Python 파이프라인으로 report.html까지 만들어줘.
```

## Agent 프롬프트 템플릿

```text
저장소: /path/to/imjang-report
사진 폴더: /absolute/path/to/photos
출력 폴더: /path/to/out
지역 힌트: <예: 안양>
법정동 코드: <예: 41171, 41173>
거래월: <YYYYMM>

요구사항:
1. README.md와 docs/PYTHON_GUIDE.md를 읽고 따라라.
2. python -m imjang_report.scripts.check_setup --check-network를 먼저 실행하라.
3. 키가 없거나 네트워크가 막히면 어떤 단계가 제한되는지 말하고, --skip-market-data 테스트 경로를 먼저 검증하라.
4. 실제 전체 파이프라인을 실행하고 report.html/session.json 생성 여부를 확인하라.
5. 최종 응답에는 실행한 명령, 생성 파일 경로, 실패/제한 사항만 요약하라.
```

## Agent가 하면 안 되는 일

- API 키 값을 응답에 출력하지 않기
- `.env`를 커밋하지 않기
- 사진 GPS가 없는데 있는 것처럼 꾸미지 않기
- Kakao/MOLIT API가 실패했는데 성공한 것처럼 가짜 데이터를 만들지 않기
- 대장아파트를 자동 선정하지 않기. 웹 리포트에서 사용자가 직접 체크합니다.
