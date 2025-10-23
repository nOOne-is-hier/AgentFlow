# AgentFlow

> 자연어 한 줄로 **기업형 자동화 파이프라인**을 만들고, 문서 기준 **정합성 검증**까지 수행하는 PoC

![Next.js](https://img.shields.io/badge/Front-Next.js-black) ![FastAPI](https://img.shields.io/badge/Back-FastAPI-009688) ![Chroma](https://img.shields.io/badge/Vector-Chroma-6C5CE7) ![SSE](https://img.shields.io/badge/Stream-SSE-2962FF) ![Docker](https://img.shields.io/badge/Pack-Docker_Compose-2496ED)

---

## 목차

* [개요](#개요)
* [주요 기능](#주요-기능)
* [빠른 시작(권장: Docker Compose)](#빠른-시작권장-docker-compose)
* [개발 모드로 실행(로컬)](#개발-모드로-실행로컬)
* [환경 변수](#환경-변수)
* [프로젝트 구조](#프로젝트-구조)
* [아키텍처](#아키텍처)
* [API 개요](#api-개요)
* [이벤트 스트리밍(SSE)](#이벤트-스트리밍sse)
* [데모 플로우](#데모-플로우)
* [문서 기준 검증 정책](#문서-기준-검증-정책)

---

## 개요

* **WHAT**: 다양한 형태의 사무/문서에 대한 **취합/검증/산출** 업무를 **자연어 지시**로 자동화하는 엔터프라이즈 PoC.
* **WHY**: 예산/기획 등 대용량 **PDF+엑셀 대조**(대사)는 리드타임·오류가 큼 → **자연어 + UI**로 진입장벽↓, **검증/감사성**↑.
* **HOW**: 우측 **채팅** 하나로 업로드/지시/HITL/결과 렌더 → 중앙 **그래프** → **SSE**로 실행 스트림 → **XLSX** 산출.

---

## 주요 기능

* **자연어 → 그래프 자동생성**: 채팅 한 줄로 노드/엣지 파이프라인을 생성(시각 캔버스 반영).
* **정합성 검증(문서 기준)**:

  * `exists`: PDF 스니펫 근거로 부서/키워드 존재 여부 확인
  * `sum_check`: 부서 총액을 PDF 기준으로 ±0.5% 오차 허용 비교
* **HITL 승인 카드**: 검증 요약 확인 후 **승인/거절**로 이어서 실행/중단.
* **SSE 타임라인**: PLAN / ACTION / OBS / SUMMARY 이벤트 스트리밍.
* **아티팩트**: 결과 **XLSX** 생성 및 **다운로드**.

---

## 빠른 시작(권장: Docker Compose)

> 로컬에서 즉시 시연 가능한 구성이 포함되어 있습니다.

1. **환경변수 파일** 생성(옵션):

```bash
# .env (백엔드에서 사용)
OPENAI_API_KEY=<옵션>  # 없으면 로컬 요약 폴백
```

2. **빌드 & 실행**

```bash
docker compose up -d --build
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
```

3. **로그인(더미)**

* 이메일 / 사번 입력 → 세션 쿠키 발급 후 작업 화면 이동

---

## 개발 모드로 실행(로컬)

### Backend (FastAPI / Python 3.11)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # 또는 uv 사용
pip install -r requirements.txt
export OPENAI_API_KEY=<옵션>   # 없으면 로컬 요약 사용
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

### Frontend (Next.js / Node 22)

```bash
cd frontend
npm ci
# 백엔드 직접 호출
export NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev  # http://localhost:3000
```

> 동일 출처 운영이 필요하면 Next.js에 프록시 라우트를 구성하고
> 서버에서 내부 호출용 `INTERNAL_API_BASE_URL=http://backend:8000`을 사용하세요.

---

## 환경 변수

| 이름                         | 위치       | 설명                       | 기본값                     |
| -------------------------- | -------- | ------------------------ | ----------------------- |
| `OPENAI_API_KEY`           | backend  | 요약/임베딩에 사용(없으면 로컬 요약 폴백) | 없음                      |
| `NEXT_PUBLIC_API_BASE_URL` | frontend | 프런트에서 백엔드 호출 Base URL    | `http://localhost:8000` |

---

## 프로젝트 구조

```
.
├─ backend/                 # FastAPI, LangGraph, 엔진 노드
│  └─ requirements.txt
├─ frontend/                # Next.js + Tailwind + shadcn/ui
│  ├─ app/
│  ├─ components/
│  ├─ hooks/
│  └─ lib/
├─ storage/                 # 업로드/중간/아티팩트 (볼륨 마운트)
├─ chroma/                  # Chroma 영속 볼륨
├─ Dockerfile.backend
├─ Dockerfile.frontend
├─ docker-compose.yml
└─ README.md
```

---

## 아키텍처

* **Front**: Next.js + Tailwind + shadcn/ui
* **Back**: FastAPI + LangGraph(역할 체인: 쿼리 이해→계획→실행→검증→병합)
* **Vector**: Chroma (OpenAI 임베딩)
* **Stream**: SSE(`text/event-stream`) — PLAN/ACTION/OBS/SUMMARY
* **Package**: Docker Compose(프론트/백/Chroma로 로컬 시연)

**파이프라인 노드(예)**

```
parse_pdf → embed_pdf(→ build_vectorstore) → merge_xlsx → validate_with_pdf → export_xlsx
```

---

## API 개요

> 모든 호출은 세션 쿠키 사용: `credentials: "include"` / SSE는 `withCredentials: true`

| 메서드     | 경로                         | 설명                                         |
| ------- | -------------------------- | ------------------------------------------ |
| POST    | `/auth/login`              | 더미 로그인 `{ email, emp_id }`                 |
| POST    | `/auth/logout`             | 로그아웃                                       |
| POST    | `/files/upload`            | 파일 업로드 (multipart `files[]`: .pdf / .xlsx) |
| GET     | `/files`                   | 업로드 목록(및 생성 파일 목록)                         |
| POST    | `/chat/turn`               | 자연어 지시 → GraphPatch + 요약                   |
| POST    | `/workflows`               | 워크플로우 저장(전체 JSON)                          |
| POST    | `/pipeline/execute`        | 실행 시작 → `{ runId }`                        |
| GET     | `/runs/{runId}`            | 상태 조회                                      |
| **GET** | **`/runs/{runId}/events`** | **SSE 스트림**(PLAN/ACTION/OBS/SUMMARY)       |
| POST    | `/runs/{runId}/continue`   | HITL 승인/거절                                 |
| GET     | `/artifacts/{artifactId}`  | XLSX 다운로드                                  |

**로그인 요청 예**

```json
{ "email": "user@sk.com", "emp_id": "12345" }
```

---

## 이벤트 스트리밍(SSE)

클라이언트는 `EventSource(BASE/runs/{runId}/events?engine=lg, { withCredentials:true })`.

**서버 전송 포맷(예)**

```json
{
  "seq": 12,
  "ts": "2025-10-22T09:12:34+09:00",
  "type": "ACTION|PLAN|OBS|SUMMARY",
  "nodeId": "parse_pdf|embed_pdf|validate|export|hitl|assistant",
  "message": "설명",
  "detail": { "k": "v" },
  "__compact__": { "applied": true }
}
```

> 대용량일 때 서버가 요약/절단하면 `__compact__.applied=true`가 포함됩니다(클라이언트 “더보기” 제공).

---

## 데모 플로우

1. **로그인** (더미)
2. **파일 업로드** — PDF 1개 + 부서별 XLSX 다수(또는 첨부 없이 서버 기본 폴더 자동 수집)
3. **채팅 지시** — “부서별 XLSX 병합하고 문서 기준으로 검증 후 XLSX 내보내줘”
4. **그래프 자동 생성** — 중앙 캔버스에 노드/엣지 표시
5. **실행(SSE)** — PLAN/ACTION/OBS/SUMMARY 타임라인
6. **HITL 승인** — 검증 결과 확인 후 승인/거절
7. **다운로드** — 좌측 패널에서 생성된 XLSX 다운로드

---

## 문서 기준 검증 정책

* **exists**: 부서명(+회계 구분)으로 PDF 벡터 검색(k=3) → 스니펫 점수 임계 이상이면 OK
* **sum_check**: 부서 시트 **총액(예산액)** vs **PDF 총괄표** ±**0.5%** 비교
* **리포트 예시**

```json
{
  "summary": { "ok": 25, "warn": 8, "fail": 6 },
  "items": [
    { "policy": "exists", "dept": "총무과", "status": "ok", "evidence": [{ "page": 12, "snippet": "..." }] },
    { "policy": "sum_check", "dept": "복지정책과", "status": "diff",
      "expected": 119987726, "found": 103674619, "delta": -16313107,
      "evidence": [{ "page": 20, "snippet": "..." }] }
  ]
}
```
