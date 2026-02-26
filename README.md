# Ticket Redirect Guard

티켓팅 백엔드에 붙이는 봇/매크로 트래픽 완화 PoC.

의심 트래픽에 302 리다이렉트 챌린지를 걸어서 자동화 스크립트를 흔들고, 정상 유저(브라우저)는 리다이렉트를 자동으로 따라가서 쿠키를 받고 원래 페이지로 복귀한다.

## 동작 원리

1. 모든 요청을 미들웨어가 가로채서 risk score를 계산한다
2. score 구간별 처리:
   - **LOW** (0~29): 바로 통과
   - **MID** (30~69): 랜덤 지연(100~800ms) 또는 40% 확률로 302 리다이렉트
   - **HIGH** (70~100): 무조건 302 리다이렉트
3. 302 리다이렉트 대상은 `/challenge` 엔드포인트
4. `/challenge`에서 HMAC 서명 토큰을 HttpOnly 쿠키로 발급하고 원래 경로로 302 복귀
5. 브라우저는 이 과정을 자동으로 처리하지만, 단순 매크로는 쿠키/리다이렉트 처리가 안 되어 흐름이 끊긴다

## Risk Score 계산 입력

- IP별 요청 빈도 (10초/60초 슬라이딩 윈도우)
- 세션/쿠키 유무
- User-Agent, Accept-Language 헤더 존재 여부
- 민감 경로 가중치 (/seat, /reserve, /pay 등)

## 빠른 시작

```bash
# 실행
docker compose up --build -d

# 헬스 체크
curl http://localhost:8000/health

# 테스트 시나리오 실행
bash tests/test_scenarios.sh
```

## 프로젝트 구조

```
app/
  main.py           # FastAPI 앱 엔트리포인트
  config.py         # 환경변수 기반 설정
  middleware.py      # Guard 미들웨어 (risk score -> pass/delay/redirect)
  scorer.py          # Risk score 계산기
  rate_limiter.py    # Redis 기반 슬라이딩 윈도우 카운터
  token.py           # HMAC 서명 토큰 생성/검증
  metrics.py         # 인메모리 메트릭 수집
  routes.py          # 엔드포인트 (/challenge, /metrics, 데모용 등)
  logging_config.py  # JSON 구조화 로그
tests/
  test_scenarios.sh  # curl 기반 검증 시나리오
```

## 설정

`.env` 파일로 모든 설정을 관리한다. `.env.example` 참고.

주요 설정:

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GUARD_ENABLED` | `true` | 킬스위치. false면 미들웨어 비활성화 |
| `HMAC_SECRET` | - | 토큰 서명 키. 반드시 변경 필요 |
| `SCORE_MID` | `30` | MID 구간 시작 점수 |
| `SCORE_HIGH` | `70` | HIGH 구간 시작 점수 |
| `RATE_LIMIT_SHORT` | `15` | 10초 내 허용 요청 수 |
| `RATE_LIMIT_LONG` | `60` | 60초 내 허용 요청 수 |
| `DELAY_MIN_MS` | `100` | MID 구간 최소 지연(ms) |
| `DELAY_MAX_MS` | `800` | MID 구간 최대 지연(ms) |
| `WHITELIST_IPS` | `127.0.0.1` | 화이트리스트 IP (쉼표 구분) |
| `WHITELIST_PATHS` | `/health,/metrics` | 화이트리스트 경로 |
| `SENSITIVE_PATHS` | `/seat,/reserve,...` | 가중치 적용 경로 |

## curl 예시

### 정상 유저 (브라우저처럼 헤더 포함)

```bash
# 첫 요청 - 챌린지를 거쳐 쿠키 획득
curl -v -c cookies.txt -L \
  -H "User-Agent: Mozilla/5.0" \
  -H "Accept-Language: ko-KR" \
  http://localhost:8000/seat

# 이후 요청 - 쿠키 포함하여 안정적 통과
curl -b cookies.txt \
  -H "User-Agent: Mozilla/5.0" \
  -H "Accept-Language: ko-KR" \
  http://localhost:8000/seat
```

### 의심 트래픽 (헤더 없이 빠르게 반복)

```bash
# 쿠키 없이, UA 없이 빠르게 호출 -> 점차 302 비율 증가
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "요청 $i -> HTTP %{http_code}\n" \
    http://localhost:8000/seat
done
```

## 메트릭 확인

```bash
curl http://localhost:8000/metrics | python3 -m json.tool
```

응답 예시:
```json
{
  "uptime_seconds": 120.5,
  "redirect_count": 15,
  "challenge_pass_count": 8,
  "challenge_fail_count": 2,
  "pass_count": 45,
  "delay_count": 10,
  "avg_delay_ms": 350.2
}
```

## 운영 참고

- 문제 발생 시 `GUARD_ENABLED=false`로 즉시 비활성화 가능
- `WHITELIST_IPS`에 내부 IP 대역 추가하여 내부 트래픽 제외
- 로그는 JSON 형식으로 stdout 출력, 외부 수집기 연동 가능
- 토큰 TTL, score 임계값, rate limit 모두 ENV로 조정 가능
