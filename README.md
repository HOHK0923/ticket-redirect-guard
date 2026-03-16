# Ticket Redirect Guard

모든 사용자에게 **대기열 + 302 리다이렉트**를 적용하여 봇/매크로 트래픽을 차단하는 독립형 보안 프록시 서버입니다.

## 아키텍처

```
Client → [AI 보안 퀴즈] → 보안 서버 → 백엔드 서버
           (다른 팀)         (이 서버)

보안 서버 내부:
┌─────────────────────────────────────┐
│  1. 대기열 진입 ("잠시만 기다려주세요!")  │
│  2. 대기 (최소 N초)                    │
│  3. 큐 통과 토큰 발급                   │
│  4. 302 리다이렉트 → 좌석 선택 페이지    │
│                                       │
│  * 큐 새치기 방지:                      │
│    토큰 없이 API 직접 접근 → 대기열로 302 │
└─────────────────────────────────────┘
```

**담당 범위**: 대기열 + 302 리다이렉트 (모든 사용자 대상)

## 핵심 기능

### 1. 대기열 (Queue)
- 모든 사용자가 대기열을 거쳐야 합니다
- 대기열 페이지에서 JavaScript 폴링 (2초 간격)
- 최소 대기 시간 경과 후 통과

### 2. 302 리다이렉트
- 대기 완료 → 좌석 선택 페이지로 302 리다이렉트
- 봇/매크로는 대기열의 JS 폴링 + 302 리다이렉트 과정에서 자연스럽게 탈락

### 3. 큐 새치기 방지
- 대기열 통과 시 Redis에 **큐 통과 토큰** 발급
- 미들웨어가 모든 API 요청에서 토큰 검증
- 토큰 없이 직접 API 호출 → 대기열로 302 강제 이동
- 토큰은 세션에 바인딩 + TTL 자동 만료

## 흐름

```
1. 사용자가 AI 퀴즈 통과 (다른 팀)
2. GET /_guard/queue → 대기열 페이지
3. 클라이언트가 /_guard/queue/status 폴링 (2초마다)
4. 최소 대기 시간 경과 → 큐 통과 토큰 발급
5. 302 리다이렉트 → 좌석 선택 페이지
6. 이후 API 호출 시 미들웨어가 토큰 검증 → 통과
```

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

## 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GUARD_ENABLED` | `true` | 킬스위치 |
| `UPSTREAM_URL` | `http://localhost:8080` | 백엔드 서버 주소 |
| `QUEUE_WAIT_MIN_SECONDS` | `3` | 대기열 최소 대기 시간 |
| `QUEUE_PASS_TTL_SECONDS` | `300` | 큐 통과 토큰 유효 시간 (5분) |
| `SESSION_TTL_SECONDS` | `600` | 세션 데이터 TTL (10분) |
| `SENSITIVE_PATHS` | `/api/ticketing,...` | 큐 통과 필수 경로 |
| `REDIRECT_URL` | `/` | 큐 미통과 시 리다이렉트 대상 |

## 프로젝트 구조

```
server.py                # 보안 서버 엔트리포인트
guard/
  __init__.py
  middleware.py           # 큐 통과 토큰 검증 미들웨어
  queue.py                # 대기열 페이지 및 상태 API
  queue_token.py          # 큐 통과 토큰 발급/검증
  session_tracker.py      # Redis 세션 상태 관리
  proxy.py                # 리버스 프록시 (백엔드 전달)
  config.py               # ENV 기반 설정
  redis_client.py         # 비동기 Redis 연결
  metrics.py              # 인메모리 메트릭
examples/
  backend_app.py          # 예제 백엔드 서버 (테스트용)
```

## 운영 참고

- `GUARD_ENABLED=false` → 모든 요청을 큐 없이 백엔드에 전달
- `/_guard/health` → 보안 서버 상태 확인
- `/_guard/metrics` → 대기열 진입/통과/차단 메트릭
- 어느 백엔드 시스템이든 연동 가능 (리버스 프록시 구조)
