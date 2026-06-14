#!/usr/bin/env python3
"""Preflight checker for imjang-report.

Checks Python version, required packages, optional API keys, and optional network
connectivity without printing secret values.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import sys
import urllib.request
from pathlib import Path
from urllib.error import URLError, HTTPError

REQUIRED_PACKAGES = ["PIL"]
OPTIONAL_PACKAGES = ["piexif"]
API_KEYS = {
    "KAKAO_REST_API_KEY": "Kakao Local API: apartment POI/geocoding (recommended)",
    "MOLIT_SERVICE_KEY": "data.go.kr MOLIT RTMS apartment trade API (recommended for direct trade data)",
    "DATA_GO_KR_SERVICE_KEY": "alias for MOLIT_SERVICE_KEY",
    "VWORLD_KEY": "VWorld geocoding fallback (optional)",
    "KSKILL_PROXY_BASE_URL": "k-skill proxy URL for rent/proxy fallback (optional)",
}
DEFAULT_ENV_FILES = [
    Path(".env"),
    Path.home() / ".config" / "imjang-report" / "secrets.env",
    Path.home() / ".config" / "k-skill" / "secrets.env",
    Path.home() / ".hermes" / ".env",
]


def load_env_file(path: Path) -> list[str]:
    loaded = []
    if not path.is_file():
        return loaded
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
            loaded.append(k)
    return loaded


def redact(v: str | None) -> str:
    if not v:
        return "missing"
    if len(v) <= 8:
        return "set (redacted)"
    return f"set ({v[:3]}…{v[-3:]}, redacted)"


def package_status(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def http_check(url: str, headers: dict[str, str] | None = None, timeout: int = 8) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except HTTPError as e:
        # HTTP errors still prove DNS/TLS/connectivity; auth errors are reported separately.
        return False, f"HTTP {e.code}"
    except URLError as e:
        return False, str(e.reason)
    except Exception as e:
        return False, str(e)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check imjang-report local setup")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--check-network", action="store_true", help="also probe public API endpoints")
    ap.add_argument("--env-file", action="append", default=[], help="extra env file to load")
    args = ap.parse_args()

    env_files = [Path(x).expanduser() for x in args.env_file] + DEFAULT_ENV_FILES
    loaded_files = []
    for f in env_files:
        loaded = load_env_file(f)
        if loaded:
            loaded_files.append({"path": str(f), "keys_loaded": sorted(loaded)})

    results: dict[str, object] = {
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "ok": sys.version_info >= (3, 11),
        },
        "platform": platform.platform(),
        "env_files_loaded": loaded_files,
        "packages": {},
        "api_keys": {},
        "network": {},
    }

    for pkg in REQUIRED_PACKAGES:
        results["packages"][pkg] = {"required": True, "ok": package_status(pkg)}  # type: ignore[index]
    for pkg in OPTIONAL_PACKAGES:
        results["packages"][pkg] = {"required": False, "ok": package_status(pkg)}  # type: ignore[index]

    has_molit = bool(os.getenv("MOLIT_SERVICE_KEY") or os.getenv("DATA_GO_KR_SERVICE_KEY"))
    for key, desc in API_KEYS.items():
        results["api_keys"][key] = {"description": desc, "status": redact(os.getenv(key))}  # type: ignore[index]
    results["api_keys"]["MOLIT_OR_DATA_GO_KR"] = {  # type: ignore[index]
        "description": "at least one of MOLIT_SERVICE_KEY or DATA_GO_KR_SERVICE_KEY",
        "ok": has_molit,
    }

    if args.check_network:
        ok, msg = http_check("https://dapi.kakao.com/v2/local/search/keyword.json?query=%EC%95%84%ED%8C%8C%ED%8A%B8", headers={"Authorization": "KakaoAK " + os.getenv("KAKAO_REST_API_KEY", "")})
        results["network"]["kakao_local"] = {"ok": ok, "detail": msg}  # type: ignore[index]
        ok, msg = http_check("https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade?LAWD_CD=41173&DEAL_YMD=202605&numOfRows=1&pageNo=1&type=json&serviceKey=" + (os.getenv("MOLIT_SERVICE_KEY") or os.getenv("DATA_GO_KR_SERVICE_KEY") or ""))
        results["network"]["molit_rtms_trade"] = {"ok": ok, "detail": msg}  # type: ignore[index]
        proxy = os.getenv("KSKILL_PROXY_BASE_URL", "https://k-skill-proxy.nomadamas.org")
        ok, msg = http_check(proxy.rstrip("/") + "/health")
        results["network"]["kskill_proxy_health"] = {"ok": ok, "detail": msg}  # type: ignore[index]

    required_ok = results["python"]["ok"] and all(v["ok"] for v in results["packages"].values() if v["required"])  # type: ignore[index,union-attr]
    recommended_ok = bool(os.getenv("KAKAO_REST_API_KEY")) and has_molit
    results["summary"] = {
        "required_ok": required_ok,
        "recommended_api_keys_ok": recommended_ok,
        "can_run_sample_no_network": required_ok,
        "can_run_full_pipeline": required_ok and recommended_ok,
    }

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("imjang-report setup check")
        print(f"- Python: {results['python']['version']} ({'OK' if results['python']['ok'] else 'FAIL: need >=3.11'})")
        print("- Packages:")
        for name, st in results["packages"].items():  # type: ignore[union-attr]
            label = "required" if st["required"] else "optional"
            print(f"  - {name}: {'OK' if st['ok'] else 'MISSING'} ({label})")
        print("- API keys (values redacted):")
        for key, st in results["api_keys"].items():  # type: ignore[union-attr]
            if key == "MOLIT_OR_DATA_GO_KR":
                print(f"  - {key}: {'OK' if st['ok'] else 'MISSING'}")
            else:
                print(f"  - {key}: {st['status']} — {st['description']}")
        if args.check_network:
            print("- Network:")
            for name, st in results["network"].items():  # type: ignore[union-attr]
                print(f"  - {name}: {'OK' if st['ok'] else 'CHECK'} ({st['detail']})")
        summary = results["summary"]  # type: ignore[assignment]
        print("- Summary:")
        print(f"  - sample/no-network run: {'OK' if summary['can_run_sample_no_network'] else 'NO'}")
        print(f"  - full API pipeline: {'OK' if summary['can_run_full_pipeline'] else 'NO (set Kakao + MOLIT keys)'}")

    return 0 if required_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
