# Ticket Redirect Guard

봇/매크로를 세션 행동 분석으로 탐지하여 **대기열 + 302 리다이렉트**로 차단하는 독립형 보안 프록시 서버입니다.

## 아키텍처

```
Client → [AI 보안 퀴즈] → 보안 서버 (대기열 + 302) → 백엔드 서버
              │                    │
              │               ┌────┴────┐
              │               │ 정상유저  │→ 좌석 선택으로 통과
              └──(다른 팀)──→  │  봇/매크로 │→ 302 리다이렉트 (차단)
                              └─────────┘
```

**담당 범위**: AI 퀴즈 통과 후 → 대기열("잠시만 기다려주세요!") → 행동 분석 → 302 리다이렉트

## 봇 탐지 방식 (AI Feature 3개)

백엔드를 통과하는 요청 로그(`server_request_log`)를 세션 단위로 분석하여 3개의 Feature를 실시간 계산합니다.

| Feature | 의미 | 사람 | 봇 |
|---------|------|------|-----|
| `endpoint_burst_max_1s` | 같은 API를 1초에 몇 번 호출했는가 | 1 | 3+ |
| `req_interval_cv` | 요청 간격의 변동계수 (CV = 표준편차/평균) | ~0.41 (불규칙) | ~0.06 (기계적) |
| `target_retry_count` | 같은 대상(좌석/주문)을 몇 번 재시도했는가 | 1 | 4+ |

### 스코어링

| Feature | 조건 | 점수 |
|---------|------|------|
| Burst | >= 3회/초 | 최대 40점 |
| CV | < 0.15 (너무 규칙적) | 최대 35점 |
| Retry | >= 3회 재시도 | 최대 25점 |
| **합계** | **60점 이상** | **302 차단** |

## 데이터 흐름

### 수집하는 Raw Data

**server_request_log** (API 호출 1건 = 1로그):
- 식별자: `UUID`, `X-User-Id`, `X-Session-Ticket`
- 대상: `showScheduleId`, `seatIds`, `orderId`
- 시간: `ts_ms_server`
- 요청: `endpoint`, `status`, `latency_ms`, `ip`, `device_id`

**domain_event_log** (퍼널 단계 이벤트):
- `seatmap_view` → `seat_hold_attempt` → `checkout_enter` → `payment_attempt` → `payment_success` / `payment_fail`

### 엔드포인트 매핑

| 백엔드 API | 도메인 이벤트 |
|-----------|-------------|
| `GET /api/ticketing/{id}/seatmap` | `seatmap_view` |
| `POST /api/ticketing/{id}/hold/seat` | `seat_hold_attempt` |
| `POST /api/bookings` | `checkout_enter` |
| `POST /api/bookings/{id}/payment-ready` | `payment_attempt` |
| `POST /api/payments/confirm` | `payment_success` |
| `GET /api/payments/fail` | `payment_fail` |

## 빠른 시작

```bash
# 1. 클론 및 설치
git clone https://github.com/HOHK0923/ticket-redirect-guard.git
cd ticket-redirect-guard
pip install -r requirements.txt

# 2. Redis
docker compose up -d

# 3. 환경변수
cp .env.example .env

# 4. 보안 서버 실행
uvicorn server:app --host 0.0.0.0 --port 8000
```

## AI 퀴즈 연동

AI 보안 퀴즈(다른 팀 담당) 통과 후 대기열로 진입합니다.

```
1. 사용자가 AI 퀴즈 통과
2. 퀴즈 시스템이 GET /_guard/queue 로 리다이렉트
3. 대기열 페이지 표시 ("잠시만 기다려주세요!")
4. 클라이언트가 /_guard/queue/status 폴링
5. risk score 확인 후:
   - 통과 → 좌석 선택 페이지로 302
   - 차단 → 메인 페이지로 302
```

## 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GUARD_ENABLED` | `true` | 킬스위치 |
| `UPSTREAM_URL` | `http://localhost:8080` | 백엔드 서버 주소 |
| `BURST_THRESHOLD` | `3` | 1초 내 동일 API 호출 임계값 |
| `CV_THRESHOLD` | `0.15` | 요청 간격 CV 임계값 (미만 시 의심) |
| `RETRY_THRESHOLD` | `3` | 동일 대상 재시도 임계값 |
| `SCORE_HIGH` | `60` | 차단 스코어 임계값 |
| `QUEUE_WAIT_MIN_SECONDS` | `3` | 대기열 최소 대기 시간 |
| `SESSION_IDLE_TIMEOUT_SECONDS` | `60` | 세션 유휴 타임아웃 |
| `SENSITIVE_PATHS` | `/api/ticketing,...` | Guard 적용 대상 경로 |

## 프로젝트 구조

```
server.py                # 보안 서버 엔트리포인트
guard/
  __init__.py             # GuardMiddleware export
  middleware.py           # 핵심 미들웨어 (세션 기반 행동 분석)
  scorer.py               # AI feature 기반 risk score 계산
  session_tracker.py      # Redis 세션 히스토리 추적
  request_parser.py       # 요청에서 세션/대상 데이터 추출
  queue.py                # 대기열 페이지 및 상태 API
  proxy.py                # 리버스 프록시 (백엔드 전달)
  models.py               # 데이터 모델 (ServerRequestLog, DomainEventLog 등)
  config.py               # ENV 기반 설정
  redis_client.py         # 비동기 Redis 연결
  metrics.py              # 인메모리 메트릭
  logging_config.py       # JSON 구조화 로그
examples/
  backend_app.py          # 예제 백엔드 서버 (테스트용)
```

## 운영 참고

- `GUARD_ENABLED=false` → 모든 요청을 그대로 백엔드에 전달합니다
- `/_guard/health` → 보안 서버 상태 확인
- `/_guard/metrics` → 통과/차단/대기열 메트릭
- `/_guard/log` → 최근 가드 판단 로그 (최대 500건)
- 모든 로그는 JSON 형식으로 stdout 출력됩니다
