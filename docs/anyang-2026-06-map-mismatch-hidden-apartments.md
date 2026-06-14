# 안양 2026-06 — 지도 불일치 단지 숨김 UX

## 배경
Kakao Local POI와 MOLIT 실거래 단지를 병합해 동선 주변 아파트를 자동 수집하면, 일부 단지는 실제 지도 위치와 맞지 않을 수 있다. 대표 사례: `동편마을(3단지)`.

## 사용자 요구
아파트 팝업에서 사용자가 잘못된 지도 위치를 발견했을 때, 해당 단지를 기록에서 숨길 수 있어야 한다. 단순히 데이터가 부정확하다고 설명하는 데 그치지 말고, 사용자가 직접 정리할 수 있는 UI가 필요하다.

## 구현 패턴
- 아파트 팝업 우측 상단에 `실제 지도와 맞지 않습니다` 버튼을 둔다.
- 버튼 클릭 시 `confirm()` 또는 동등한 확인 모달로 다음 취지의 문구를 보여준다.
  - 현재 사용하는 지도 API/Kakao 등 외부 데이터에 잘못된 좌표가 들어간 것 같다.
  - 기록의 정확함을 위해 해당 아이콘을 지도에서 삭제할 수 있다.
  - 삭제하면 임장기록 스크립트를 재실행하지 않는 한 다시 복구되지 않는다.
- 확인 시 localStorage에 `hidden_apartments[]`를 저장한다.
- `hidden_apartments[]`에 있는 단지는 아래 표면에서 모두 제외한다.
  - Leaflet 아파트 마커
  - 좌측 아파트 목록과 태그 필터
  - 전체 보기 bounds 계산
  - 후기 갈무리 overlay
  - MD 추출
  - Notion ZIP/Markdown 생성
  - JSON 백업에는 `hidden_apartments[]`를 포함한다.

## 중요한 UX/데이터 원칙
- 원본 `SESSION.apartments` 또는 수집 JSON을 즉시 삭제하지 말고, 사용자 저장 상태로 숨긴다. 이렇게 해야 JSON 백업/재실행/디버깅 경로가 명확하다.
- 버튼은 Leaflet 기본 닫기(X) DOM을 직접 조작하기보다 팝업 내용 우측 상단에 두는 편이 안전하다.
- 삭제는 가벼운 토글이 아니라 기록 정확도 보정 행위이므로 확인 문구를 분명히 보여준다.
- 삭제 후에는 열린 팝업을 닫고 마커를 `map.removeLayer(marker)`로 제거한 뒤 `aptMarkers[id]`에서도 삭제한다.
- 이후 `renderAptTagFilter()`와 `renderAptList()`를 다시 호출해 목록/필터 상태를 즉시 갱신한다.

## 검증 체크리스트
1. 잘못된 단지 팝업 HTML에 `실제 지도와 맞지 않습니다` 버튼이 있다.
2. 클릭 시 안내 문구가 표시된다.
3. 확인 후 `isHiddenApt(id) === true`가 된다.
4. `aptMarkers[id]`가 제거되고 지도에서 마커가 사라진다.
5. 좌측 목록 `.apt-card[data-id="..."]`가 사라진다.
6. `generateMarkdown()` 결과에 해당 단지 후기가 포함되지 않는다.
7. JSON 백업/localStorage에 `hidden_apartments[]`가 보존된다.
8. 페이지 새로고침 후에도 숨김 상태가 유지된다.

## 예시 JS 함수 이름
- `ensureHiddenAptArray()`
- `isHiddenApt(aptId)`
- `hideMismatchedApt(aptId, aptName, ev)`

## Pitfall
`hidden_apartments[]`를 목록 렌더링에만 적용하면 MD/Notion ZIP이나 갈무리에 잘못된 단지가 계속 남는다. 숨김 상태는 모든 산출 표면에 공통 필터로 적용해야 한다.
