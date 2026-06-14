# Examples

이 디렉토리에는 실제 사용자 사진/API 키를 넣지 않습니다.

네트워크 없이 동작 검증은 테스트가 synthetic GPS 사진을 생성해서 수행합니다.

```bash
uv pip install -e '.[test]'
pytest -q tests/test_no_network_pipeline.py
```

실제 데이터 실행은 README의 `imjang-run` 예시를 사용하세요.
