# Release checklist

Last local verification: 2026-06-14

## Required checks

- [x] Project structure exists for GitHub distribution.
- [x] Pure Python CLI path documented in `README.md` and `docs/PYTHON_GUIDE.md`.
- [x] Agent/Hermes path documented in `docs/HERMES_AGENT.md` and `skills/hermes/real-estate-site-visit/SKILL.md`.
- [x] API key setup and preflight documented in `docs/API_KEYS_AND_PREFLIGHT.md` and `.env.example`.
- [x] Secrets are not committed; `.env`, `.env.*`, `secrets.env`, and key files are ignored.
- [x] Synthetic no-network tests exist under `tests/`.
- [x] Kakao POI auxiliary facility filter regression test exists.

## Commands run

```bash
python3 -m py_compile src/imjang_report/scripts/*.py
uv run --with pillow --with pytest --with piexif python -m imjang_report.scripts.check_setup --json
uv run --with pillow --with pytest --with piexif pytest -q
```

Result:

```text
3 passed in 0.20s
```

## Full API smoke test run locally

Command shape:

```bash
uv run --with pillow --with pytest --with piexif python -m imjang_report.scripts.run_pipeline \
  --photos <private-photo-folder> \
  --workdir /tmp/imjang_repo_full_verify2 \
  --region-hint 안양 \
  --lawd-cd 41171 \
  --lawd-cd 41173 \
  --deal-ymd 202605 \
  --skip-geocode-clusters
```

Result summary:

- GPS photos: 104 / 104
- clusters: 15
- MOLIT trade items: 245 + 568
- rent fallback items: 100 + 100
- apartments within 300m: 85
- generated: `/tmp/imjang_repo_full_verify2/session.json`
- generated: `/tmp/imjang_repo_full_verify2/report.html`
- auxiliary POI check after filtering: no community/management/kindergarten tokens in final apartment names

The command above used private local photos and local API keys; do not commit its outputs.

## Secret scan commands

```bash
# Personal-path and known-token scan
search_files pattern: <private usernames, private photo folder names, known token prefixes, local temp paths>

# generic key/token scan
search_files pattern: (?i)(api[_-]?key|token|secret|service[_-]?key)[\s:=]+[A-Za-z0-9_\-]{20,}|KakaoAK\s+[A-Za-z0-9_\-]{10,}|Bearer\s+[A-Za-z0-9_\-]{10,}
```

Result: 0 matches for actual secret/token/personal-path patterns.

## Before pushing

```bash
git status --short
git add .
git commit -m "Initial imjang-report release"
git branch -M main
git remote add origin git@github.com:<OWNER>/imjang-report.git
git push -u origin main
```
