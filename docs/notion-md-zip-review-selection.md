# Notion ZIP / MD 추출 기준과 폴더 선택 UX

Session learning from the Anyang imjang report workflow.

## Durable rule

For MD export and Notion ZIP export, do not treat tags alone as a written review.

A photo or apartment counts as "reviewed" only when the free-text review field contains non-whitespace text:

- photo review textarea placeholder: `임장 후기를 자유롭게 적어주세요...`
- photo-specific prompt copy may be: `이 사진에 대한 후기를 입력하세요`

Tags are supplementary metadata for an item that already has review text. A tag-only item should remain excluded from default MD/Notion ZIP exports, review badges, capture overlays, and reviewed-count export summaries unless the UI explicitly says it is filtering by tag.

Recommended helper shape:

```js
function getReviewText(targetId) {
  const r = storage.reviews[targetId];
  if (!r) return null;
  const text = String(r.text || '').trim();
  return text ? text : null;
}
```

Then default export predicates should use only `!!getReviewText(id)`, not `getReviewTags(id).length`.

## Notion ZIP folder selection copy

Avoid saying "HTML 옆의 assets/photos 폴더" to the user unless explaining implementation details. Although technically this is a relative path next to `report.html`, it is confusing in the browser folder picker.

Preferred user-facing copy:

1. 1차 선택창: 원본 임장 사진 폴더
   - show the concrete original photo folder path from `SESSION.photo_folder`
   - explain: `처음 촬영 사진이 들어 있던 폴더입니다.`
2. 2차 선택창: 추출할 대상 위치
   - if the browser asks again, tell the user to select the same original photo folder again
   - explicitly say they do not need to calculate or choose a relative path from the HTML file

Also clarify that the folder picker is not choosing where to save the ZIP. It is granting browser permission to read local photos.

Suggested button text:

- `📁 사진 폴더 확인 후 ZIP 생성`

Suggested checkbox copy:

- `전체 사진 포함 (기본: MD 추출과 동일하게 실제 후기 문구가 입력된 사진만 포함)`

## Verification checklist

When changing this area, test at least these cases with temporary localStorage or fixture data:

- tag-only photo is excluded from default Notion ZIP and MD export
- text-review photo is included in default Notion ZIP and MD export
- tag-only apartment is excluded from exported apartment-review section
- `전체 사진 포함` includes all photos
- Notion modal hint does not mention `assets/photos` as a required user choice
- console has no JS errors after opening the modal and generating markdown
