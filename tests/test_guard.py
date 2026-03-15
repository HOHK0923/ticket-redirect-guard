"""Guard 방어 검증 테스트.

다양한 트래픽 패턴을 시뮬레이션하여 Guard 미들웨어가
의도대로 동작하는지 검증합니다.

실행: python3 tests/test_guard.py
사전조건: docker compose up -d && uvicorn examples.basic_app:app --port 8000
"""

import http.cookiejar
import json
import sys
import time
import urllib.request
import urllib.error
from collections import Counter
from dataclasses import dataclass, field

BASE = "http://localhost:8000"


@dataclass
class TestResult:
    name: str
    total: int = 0
    status_counts: Counter = field(default_factory=Counter)
    redirect_count: int = 0
    pass_count: int = 0

    def record(self, status: int):
        self.total += 1
        self.status_counts[status] += 1
        if status == 302:
            self.redirect_count += 1
        elif 200 <= status < 300:
            self.pass_count += 1

    def summary(self) -> str:
        redirect_pct = (self.redirect_count / max(self.total, 1)) * 100
        pass_pct = (self.pass_count / max(self.total, 1)) * 100
        lines = [
            f"  총 요청: {self.total}",
            f"  통과(2xx): {self.pass_count} ({pass_pct:.0f}%)",
            f"  리다이렉트(302): {self.redirect_count} ({redirect_pct:.0f}%)",
            f"  상태코드 분포: {dict(self.status_counts)}",
        ]
        return "\n".join(lines)


def make_request(url, headers=None, cookie_jar=None, follow_redirects=False):
    """단일 HTTP 요청. 리다이렉트 추적 여부 선택 가능."""
    opener_handlers = []
    if cookie_jar is not None:
        opener_handlers.append(urllib.request.HTTPCookieProcessor(cookie_jar))
    if not follow_redirects:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise urllib.error.HTTPError(newurl, code, msg, headers, fp)
        opener_handlers.append(NoRedirect)

    opener = urllib.request.build_opener(*opener_handlers)
    req = urllib.request.Request(url, headers=headers or {})
    try:
        resp = opener.open(req, timeout=10)
        return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return -1


def print_header(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")


# 시나리오 1: 정상 유저 (브라우저 시뮬레이션)
def test_normal_user():
    print_header("시나리오 1: 정상 유저 (쿠키 + 브라우저 헤더)")
    result = TestResult(name="normal_user")
    cj = http.cookiejar.CookieJar()

    browser_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        "Cookie": "sid=abc123; session_id=def456",
    }

    print("  [테스트] 2초 간격으로 10회 요청...")
    for i in range(10):
        status = make_request(
            f"{BASE}/api/checkout",
            headers=browser_headers,
            cookie_jar=cj,
            follow_redirects=False,
        )
        result.record(status)
        print(f"    요청 {i+1:2d} -> HTTP {status}")
        time.sleep(2)

    print(f"\n  [결과]")
    print(result.summary())
    print(f"  [기대] 대부분 통과(2xx), 리다이렉트 거의 없어야 함")
    return result


# 시나리오 2: 단순 반복 (쿠키/헤더 없이 빠르게)
def test_simple_rapid():
    print_header("시나리오 2: 단순 반복 (쿠키 없음, 헤더 없음, 빠른 호출)")
    result = TestResult(name="simple_rapid")

    print("  [테스트] 간격 없이 30회 요청...")
    for i in range(30):
        status = make_request(
            f"{BASE}/api/checkout",
            headers={"User-Agent": ""},
            follow_redirects=False,
        )
        result.record(status)
        print(f"    요청 {i+1:2d} -> HTTP {status}")

    print(f"\n  [결과]")
    print(result.summary())
    print(f"  [기대] 후반부로 갈수록 302 비율 증가")
    return result


# 시나리오 3: 민감 경로 집중
def test_sensitive_paths():
    print_header("시나리오 3: 민감 경로 집중 (/api/pay, /api/reserve)")
    result = TestResult(name="sensitive_paths")
    paths = ["/api/pay", "/api/reserve", "/api/pay", "/api/checkout", "/api/pay"]

    print("  [테스트] 민감 경로에 간격 없이 25회 요청...")
    for i in range(25):
        path = paths[i % len(paths)]
        status = make_request(
            f"{BASE}{path}",
            headers={"User-Agent": ""},
            follow_redirects=False,
        )
        result.record(status)
        print(f"    요청 {i+1:2d} {path:18s} -> HTTP {status}")

    print(f"\n  [결과]")
    print(result.summary())
    print(f"  [기대] 민감 경로 가중치로 인해 일반보다 빠르게 302 발생")
    return result


# 메트릭 확인
def show_metrics():
    print_header("메트릭 확인")
    try:
        req = urllib.request.Request(f"{BASE}/metrics")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"  메트릭 조회 실패: {e}")


def main():
    print("\n" + "=" * 50)
    print("  Ticket Redirect Guard - 방어 검증 테스트")
    print("=" * 50)

    print("\n[사전] Redis rate counter 초기화를 위해 5초 대기...")
    time.sleep(5)

    results = []
    results.append(test_normal_user())

    print("\n--- 다음 시나리오 준비 (rate counter 리셋 대기 12초) ---")
    time.sleep(12)

    results.append(test_simple_rapid())

    print("\n--- 다음 시나리오 준비 (12초 대기) ---")
    time.sleep(12)

    results.append(test_sensitive_paths())

    show_metrics()

    # 종합 결과
    print_header("종합 결과")
    for r in results:
        redirect_pct = (r.redirect_count / max(r.total, 1)) * 100
        if r.name == "normal_user":
            verdict = "OK" if redirect_pct < 30 else "FAIL (정상 유저 과차단)"
        else:
            verdict = "OK" if redirect_pct > 10 else "FAIL (의심 트래픽 미탐지)"
        print(f"  {r.name:20s} | 302비율: {redirect_pct:5.1f}% | {verdict}")


if __name__ == "__main__":
    main()
