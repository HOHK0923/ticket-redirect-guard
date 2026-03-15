# Ticket Redirect Guard

어떤 FastAPI / Starlette 사이트에든 **한 줄**로 적용할 수 있는 봇/매크로 트래픽 완화 미들웨어입니다.

의심 트래픽에 **302 리다이렉트 + 랜덤 지연**을 걸어 자동화 스크립트를 교란하고,
정상 유저(브라우저)는 전혀 영향을 받지 않습니다.

## 동작 원리

1. 모든 요청을 미들웨어가 가로채서 **risk score (0~100)**를 계산합니다
2. score 구간별 처리:
   - **LOW** (0~29): 바로 통과
   - **MID** (30~69): 랜덤 지연(100~800ms) 또는 40% 확률로 302 리다이렉트
   - **HIGH** (70~100): 무조건 302 리다이렉트 (메인 페이지로)
3. 봇은 302 응답만 받고 실제 데이터에 접근하지 못합니다
4. 브라우저는 302를 자동 처리하므로 정상 유저는 영향 없습니다

### Risk Score 계산 입력

| 신호 | 점수 |
|------|------|
| IP별 요청 빈도 (10초/60초 슬라이딩 윈도우) | 최대 70점 |
| 세션/쿠키 없음 | 15점 |
| User-Agent 없음 | 10점 |
| Accept-Language 없음 | 5점 |
| 민감 경로 접근 (/api/pay, /api/checkout 등) | 10점 |

## 적용 방법

### 1. 패키지 설치

```bash
# guard/ 디렉토리를 프로젝트에 복사하고 의존성을 설치합니다
pip install fastapi uvicorn redis[hiredis] pydantic-settings
```

### 2. 미들웨어 적용 (한 줄)

```python
from fastapi import FastAPI
from guard import GuardMiddleware

app = FastAPI()

# 이 한 줄이면 됩니다
app.add_middleware(
    GuardMiddleware,
    bypass_paths={"/", "/about", "/login"},  # guard를 건너뛸 경로
)
```

### 3. Redis 실행

```bash
docker compose up -d   # Redis 7 Alpine 컨테이너
```

### 4. 환경변수 설정

`.env` 파일을 생성합니다 (`.env.example` 참고):

```bash
cp .env.example .env
# 필요에 따라 값을 수정합니다
```

### 5. 서버 실행

```bash
uvicorn your_app:app --port 8000
```

## 설정

`.env` 파일로 모든 설정을 관리합니다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GUARD_ENABLED` | `true` | 킬스위치. `false`면 미들웨어 비활성화 |
| `REDIS_URL` | `redis://redis:6379/0` | Redis 연결 URL |
| `SCORE_MID` | `30` | MID 구간 시작 점수 |
| `SCORE_HIGH` | `70` | HIGH 구간 시작 점수 |
| `RATE_LIMIT_SHORT` | `15` | 10초 내 허용 요청 수 |
| `RATE_LIMIT_LONG` | `60` | 60초 내 허용 요청 수 |
| `DELAY_MIN_MS` | `100` | MID 구간 최소 지연(ms) |
| `DELAY_MAX_MS` | `800` | MID 구간 최대 지연(ms) |
| `WHITELIST_IPS` | `127.0.0.1` | 화이트리스트 IP (쉼표 구분, CIDR 지원) |
| `WHITELIST_PATHS` | `/health,/metrics` | 화이트리스트 경로 |
| `WHITELIST_UAS` | `` | 화이트리스트 User-Agent (부분 매칭) |
| `SENSITIVE_PATHS` | `/api/seats,...` | 가중치 적용 경로 |
| `REDIRECT_URL` | `/` | 봇 감지 시 리다이렉트 대상 URL |

## 프로젝트 구조

```
guard/
  __init__.py        # GuardMiddleware export
  middleware.py      # 핵심 미들웨어 (score → pass/delay/redirect)
  config.py          # ENV 기반 설정 (pydantic-settings)
  scorer.py          # Risk score 계산기
  rate_limiter.py    # Redis sorted set 슬라이딩 윈도우 카운터
  redis_client.py    # 비동기 Redis 연결 풀
  metrics.py         # 인메모리 메트릭 수집
  logging_config.py  # JSON 구조화 로그
examples/
  basic_app.py       # 쇼핑몰 예제 (적용 방법 데모)
```

## 테스트

```bash
# Redis 실행
docker compose up -d

# 예제 앱 실행
uvicorn examples.basic_app:app --port 8000

# 정상 유저 (200 OK)
curl -H "User-Agent: Mozilla/5.0" \
     -H "Accept-Language: ko-KR" \
     -b "sid=abc; session_id=def" \
     http://localhost:8000/api/checkout

# 봇 시뮬레이션 (점점 302 증가)
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "요청 $i → HTTP %{http_code}\n" \
    -H "User-Agent: " \
    http://localhost:8000/api/checkout
done

# 메트릭 확인
curl http://localhost:8000/metrics | python3 -m json.tool
```

## 운영 참고

- 문제 발생 시 `GUARD_ENABLED=false`로 즉시 비활성화 가능합니다
- `WHITELIST_IPS`에 내부 IP 대역(CIDR)을 추가하여 내부 트래픽을 제외할 수 있습니다
- 로그는 JSON 형식으로 stdout 출력되며, 외부 수집기와 연동 가능합니다
- score 임계값, rate limit, 지연 범위 모두 ENV로 실시간 조정 가능합니다
