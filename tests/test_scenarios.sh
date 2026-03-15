#!/usr/bin/env bash
# -------------------------------------------------------
# Ticket Redirect Guard - 검증 시나리오
#
# 사전 조건: docker compose up -d && uvicorn examples.basic_app:app --port 8000
# 사용법:   bash tests/test_scenarios.sh
# -------------------------------------------------------

set -euo pipefail

BASE="http://localhost:8000"

green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
separator() { echo "────────────────────────────────────────"; }

# 1. Health check
separator
green "[1] Health check"
curl -s "$BASE/health" | python3 -m json.tool
echo

# 2. 정상 유저 시나리오 (쿠키 O, 느린 호출)
separator
green "[2] 정상 유저 - 쿠키 + 브라우저 헤더로 느린 요청"
for i in 1 2 3; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" \
    -H "Accept-Language: ko-KR,ko;q=0.9" \
    -b "sid=abc123; session_id=def456" \
    "$BASE/api/checkout")
  echo "  요청 $i -> HTTP $CODE"
  sleep 2
done
echo

# 3. 의심 트래픽 시나리오 (쿠키 X, 빠른 반복)
separator
yellow "[3] 의심 트래픽 - 쿠키 없이 빠르게 반복"
for i in $(seq 1 25); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "User-Agent: " \
    "$BASE/api/checkout")
  printf "  요청 %2d -> HTTP %s\n" "$i" "$CODE"
done
echo

# 4. 민감 경로 테스트
separator
yellow "[4] 민감 경로 (/api/pay) - 쿠키 없이"
for i in 1 2 3 4 5; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "User-Agent: " \
    "$BASE/api/pay")
  echo "  /api/pay 요청 $i -> HTTP $CODE"
done
echo

# 5. 메트릭 확인
separator
green "[5] 메트릭 확인"
curl -s "$BASE/metrics" | python3 -m json.tool
echo

separator
green "테스트 완료"
