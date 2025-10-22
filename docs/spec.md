# 1. 문서 개요

## 1.1 목적

* 2일 PoC로 “자연어 → 파이프라인 생성 → 실행 → 검증 → XLSX 산출” **엔드투엔드 시연**.
* **SDD(Spec Driven Development)** + **YAGNI**: 문서에 정의된 계약만 구현, 불필요 기능 배제.

## 1.2 범위 / 비범위

* **범위**: 로그인(더미), 파일 업로드, 채팅(지시/HITL/ToT·ReAct/결과), 그래프 렌더(DnD/Save/Load), 파이프라인 실행(순차), PDF 임베딩 기반 검증(`exists`/`sum_check`), XLSX 생성/다운로드.
* **비범위**: 병렬 실제 실행, 스케줄러, 권한/감사 추적, GUI로 노드 속성 편집, 고급 회계 대사.

## 1.3 참조

* 사업 개요 및 근거, 시연 시나리오 동결본, 데이터/검증 정책 확정안.

---

# 2. 시연 시나리오(동결본)

## 2.1 흐름

로그인 → 작업 UI → **우측 채팅**에서 파일 업로드·지시·HITL → 중앙 그래프 실시간 생성/조작(DnD/Save/Load) → 실행 → 검증 리포트(우측 채팅 렌더) → 좌측 사이드 패널에서 **XLSX 다운로드**.

## 2.2 데모 수용 기준

* 채팅 한 문장 지시로 그래프가 생성되고 ToT/ReAct가 단계별 스트림으로 표시.
* `exists`/`sum_check(±0.5%)` 결과가 우측 채팅에 근거 스니펫과 함께 제시.
* XLSX 산출물 다운로드 가능.

---

# 3. 시스템 경계 & 가정

* 단일 로컬 환경, 단일 사용자 데모.
* 더미 로그인(이메일+사번) → 세션 쿠키.
* 모델 키: `.env`의 `OPENAI_API_KEY`.
* 타임존/로케일: `Asia/Seoul`, 숫자 포맷 `ko-KR`.

---

# 4. 개발 환경 & 스택

* **프런트**: Next.js, Tailwind CSS, shadcn/ui
* **백엔드**: FastAPI (Python **3.11.11**, **LangGraph** 오케스트레이션, 패키지 매니저 **uv**)
* **Vector DB**: **Chroma (로컬)** — 임베딩 검색/메타 저장, PoC 적합
* **IDE**: VS Code
* **런타임**: Docker / docker-compose (로컬 시연)

> 기본 경로

```
/app/frontend   # Next.js
/app/backend    # FastAPI
/app/storage    # 파일 업로드, 아티팩트, 체크포인트
/app/chroma     # Chroma 영속 볼륨
```

---

# 5. 사용자 인터페이스 계약

## 5.1 로그인

* 필드: 이메일(placeholder `name@company.com`), 사번(placeholder `123456`)
* 성공 시 작업 UI로 라우팅.

## 5.2 작업 UI 레이아웃

* **좌측 사이드 패널**

  * 사용자 정보(이메일, 사번 끝 4자리 마스킹)
  * 섹션: **워크플로우 목록**, **파일 목록**
  * 각 항목 선택/다운로드 버튼(파일)
* **중앙 그래프 캔버스**

  * 노드/엣지 시각화(DnD/줌)
  * 읽기 전용 속성 패널(선택 시)
  * **Save/Load** 가능(파일/스토리지 기반)
* **우측 채팅 패널**(**유일한 채팅 UI**)

  * 파일 업로드(PDF, XLSX)
  * 사용자 지시 입력
  * **HITL** 확인(예/아니오)
  * **ToT/ReAct** 이벤트 스트림(PLAN/ACTION/OBS/SUMMARY)
  * 결과/검증 리포트 렌더(존댓말)

---

# 6. 멀티 에이전트 오케스트레이션(역할)

> **LangGraph 기반 역할 그래프**로 구현. 각 역할은 LangGraph 노드로 구성되며, **그래프 엣지**는 §8 Workflow의 `edges`를 그대로 매핑한다.

* **쿼리 이해 에이전트**: 입력 의도/파라미터 추출, 주의사항 도출 → 계획 에이전트로 전달.
* **계획 에이전트**: 허용된 노드·도구 카탈로그 내에서 **그래프 스펙** 생성(초안) → 실행 에이전트로 전달.
* **실행 에이전트(오케스트레이터)**: 스펙 검증 후 노드 순차 실행, 이벤트 발행.
* **검증 에이전트**: PDF 임베딩/키워드 기반 `exists`, 부서 총액 `sum_check` 수행 → 리포트 반환.
* **병합 에이전트**: 검증 통과 산출물 병합 → 최종 XLSX.
* **체크포인트**: 로컬 SQLite(`/app/storage/checkpoints.sqlite3`)로 재시작/복구 지원.
* **HITL**: 승인 시점에 `interrupt("approve")`로 정지 → 승인 수신 시 재개(§11 API 참고).

---

# 7. ToT / ReAct 이벤트 스트리밍

## 7.1 전송 방식

* **SSE** (`text/event-stream`) — 단순하고 역방향 프록시 친화적.

## 7.2 이벤트 타입

* `PLAN`(계획 수립/수정), `ACTION`(도구·노드 실행), `OBS`(관측/결과 요약), `SUMMARY`(단계 요약).

## 7.3 이벤트 페이로드(표준 키)

```json
{
  "seq": 12,
  "ts": "2025-10-22T09:12:34+09:00",
  "type": "ACTION",
  "nodeId": "parse_pdf",
  "message": "parse_pdf 노드를 시작합니다.",
  "detail": { "file": "예산서.pdf", "pageRange": "1-20" }
}
```

## 7.4 에러/중단

* `type: "OBS"`에 에러 요약 및 `detail.code`(예: `E-PDF-READ`) 포함 → 이후 `SUMMARY`로 실패 단계 정리.

## 7.5 구현 메모

* 모든 `PLAN/ACTION/OBS/SUMMARY` 이벤트는 **LangGraph 콜백(before/after node run)**에서 방출한다. **페이로드 키(§7.3)**는 그대로 유지한다.
* SSE 재연결을 위해 `id:` 헤더를 송신(Last-Event-ID 지원).

---

# 8. 파이프라인 그래프 스키마 v0.1

## 8.1 Workflow JSON

```json
{
  "id": "uuid",
  "name": "string",
  "nodes": [ /* Node[] */ ],
  "edges": [ /* Edge[] */ ],
  "createdAt": "ISO8601",
  "updatedAt": "ISO8601"
}
```

## 8.2 Node / Edge

```json
{
  "id": "string",
  "type": "parse_pdf|embed_pdf|build_vectorstore|merge_xlsx|validate_with_pdf|export_xlsx",
  "label": "string",
  "config": { "k": "v" },
  "in": ["nodeId.outKey?"],
  "out": ["outKey"]
}
```

```json
{ "from": "nodeId", "to": "nodeId" }
```

### 8.2.1 노드 최소 config & out 키

| type                | 필수 config                                                                                                 | out                 |
| ------------------- | --------------------------------------------------------------------------------------------------------- | ------------------- |
| `parse_pdf`         | `{ "pdf_path": "string", "chunk_size": 1200, "overlap": 200 }`                                            | `pdf_chunks`        |
| `embed_pdf`         | `{ "chunks_in": "node.out", "model": "text-embedding-3-small" }`                                          | `pdf_embeddings`    |
| `build_vectorstore` | `{ "embeddings_in": "node.out", "collection": "budget_pdf" }`                                             | `vs_ref`            |
| `merge_xlsx`        | `{ "xlsx_path": "string", "flatten": true, "split": "by_department" }`                                    | `merged_table`      |
| `validate_with_pdf` | `{ "table_in": "node.out", "vs_in": "node.out", "policies": ["exists","sum_check"], "tolerance": 0.005 }` | `validation_report` |
| `export_xlsx`       | `{ "table_in": "node.out", "filename": "string" }`                                                        | `artifact_path`     |

## 8.3 GraphPatch 규약(그래프 실시간 반영용)

```json
{
  "addNodes": [ /* Node */ ],
  "addEdges": [ /* Edge */ ],
  "updateLabels": [{ "id": "nodeId", "label": "string" }],
  "removeNodes": ["id?"],
  "removeEdges": [{ "from": "a", "to": "b" }]
}
```

## 8.4 저장/불러오기 계약 & LangGraph 매핑

* `POST /workflows`에 전체 `Workflow` JSON 저장, `GET /workflows/{id}`로 복원.
* `nodes[].type` → **LangGraph 노드 함수** 매핑.
* `edges[{from,to}]` → **LangGraph edge**로 연결.
  데이터 전달은 기존대로 `config.*_in`과 `in/out` 키를 파이프 해석기가 해석.

---

# 9. 데이터 스키마 & 분할 계획(확정)

## 9.1 XLSX 편평화 컬럼 스키마

* 멀티헤더 가능 → 편평화 후 아래 **기본 컬럼** 보장:

  * 문자열: `회계연도, 예산구분, 회계구분명, 부서명, 세부사업명, 통계목코드, 통계목명, 산출근거`
  * 정수(천원): `예산액, 기정액, 비교증감`
  * 재원별(있으면 모두 포함, 존재 컬럼만): `국고보조금, 지역균형발전특별회계보조금, 기금보조금, 특별교부세, 광역보조금, 특별조정교부금, 자체재원` 등
* 숫자 전처리: 천단위 구분기호 제거, 단위 **천원** 유지, 결측치 0 처리 금지(결측은 결측으로 유지).

## 9.2 시트 분할 규칙(산출물 XLSX)

* 파일명(결과): **`2025년도 제3회 일반 및 기타특별회계 추가경정예산서(세출-검색용).xlsx`**
* 시트:

  1. `개요`: 총 행수, 부서 수, 회계구분 분포, 전체 합계(예산액/기정액/비교증감)
  2. `부서명=<이름>`: 해당 부서 행만 포함(원본 컬럼 전부), 정렬 `회계구분명→세부사업명→통계목코드`

     * 마지막 행에 **부서 합계**(예산액/기정액/비교증감)
* 부서명 정규화: 공백/전각/괄호 표기 등 단순 정리(정규화 맵은 코드 내부 간단 rules).

## 9.3 PDF 파싱/임베딩 단위

* 파싱: 페이지 텍스트 추출 → **chunk_size 1200 tokens**, overlap 200(문단 경계 유지 노력)
* 메타: `page`, `offset`, `section_hint?`(제목 라인 heuristic)
* 임베딩: `text-embedding-3-small`(1536차원) with OpenAI
* Vector store: **Chroma** collection=`budget_pdf`, `id=page:offset`

## 9.4 용어/단위/정규화

* 단위: **천원**
* 핵심 관계: `비교증감 = 예산액 - 기정액`(불일치 허용; 리포트에 차이 주석 가능)
* 회계구분/부서명 문자열 비교는 **정규화 후** 수행(소문자화·공백 트림·특수기호 간소화).

---

# 10. 검증 정책(확정)

## 10.1 `exists` (텍스트 존재성)

* 키: `부서명`(+선택: `회계구분명`)
* 규칙: Chroma에서 질의어(`부서명 + 회계 키워드`) k=3 검색 → 상위 1개 스니펫이 **유의미 점수**(임계 0.2, 상대점수 기준) 이상이면 OK.
* 리포트 항목 예:

```json
{ "policy": "exists", "dept": "복지정책과", "status": "ok|miss", "evidence": [{ "page": 20, "snippet": "..." }] }
```

## 10.2 `sum_check` (부서 총액 대조)

* 비교: **부서 시트 합계(예산액)** vs PDF 조직/총괄표의 해당 부서 총액(스니펫에서 수치 파싱)
* 허용 오차: **±0.5%**
* 리포트 항목 예:

```json
{
  "policy": "sum_check",
  "dept": "복지정책과",
  "status": "ok|diff",
  "expected": 119987726,
  "found": 103674619,
  "delta": -16313107,
  "evidence": [{ "page": 20, "snippet": "..." }]
}
```

> *주: 정밀 회계 대사는 PoC 비범위. 불일치 시 “추가 검토 필요”로만 표기.*
> *계산 규칙: `delta = found - expected`.*

## 10.3 리포트 컨테이너(JSON · UI 렌더 전용)

```json
{
  "summary": { "ok": 0, "warn": 0, "fail": 0 },
  "items": [ /* exists & sum_check 항목 혼합 */ ]
}
```

## 10.4 주의/제한

* 음수 재원(반납/정산) 허용 — 검증 실패 사유 아님(주석 표기).
* 부서명이 PDF와 약간 상이하면 **정규화** 후 비교.

---

# 11. 백엔드 API 스펙 v0.1

> 모든 응답은 `application/json`(파일 다운로드 제외). 에러는 공통 포맷 사용.

## 11.1 인증

* `POST /auth/login`
  **Req** `{ "email": "string", "empno": "string" }`
  **Res** `200 { "user": { "email": "...", "empno_masked": "****" } }` (+세션쿠키)

## 11.2 파일

* `POST /files/upload` (multipart)
  **Fields**: `files[]` (pdf|xlsx)
  **Res** `200 { "files": [{ "id": "uuid", "name": "...", "type": "pdf|xlsx", "size": 12345 }] }`
* `GET /files` → 업로드 목록

## 11.3 채팅 턴 (그래프 패치 + ToT 요약)

* `POST /chat/turn`
  **Req** `{ "message": "string", "fileIds": ["uuid"] }`
  **Res** `200 { "assistant": "string", "tot": { /*요약*/ }, "graphPatch": { /*8.3*/ } }`

## 11.4 워크플로우 저장/불러오기

* `GET /workflows`
* `POST /workflows` (body: `Workflow`) → `201 { "id": "uuid" }`
* `GET /workflows/{id}` → `200 Workflow`

## 11.5 실행/상태

* `POST /pipeline/execute`
  **Req** `{ "workflowId": "uuid" }`
  **Res** `202 { "runId": "uuid" }`

* `GET /runs/{runId}`
  **Res** `200 { "status": "PLANNING|WAITING_HITL|RUNNING|SUCCEEDED|FAILED|CANCELLED", "startedAt": "...", "endedAt": null|"..." }`

* **신규** `POST /runs/{runId}/continue`
  **Req** `{ "approve": true | false, "comment"?: "string" }`
  **Res** `200 { "status": "RUNNING" | "CANCELLED" }`
  **설명**: LangGraph `interrupt("approve")` 대기 상태를 승인/거부로 해제. 거부(false) 시 런 종료(`CANCELLED` 또는 `FAILED`).

## 11.6 이벤트 스트림(SSE)

* `GET /runs/{runId}/events` → `text/event-stream`
  **Data**: §7.3의 이벤트 JSON을 `data: <json>\n\n` 형식으로 순차 전송. `id:` 포함 권장.

## 11.7 산출물

* `GET /artifacts/{artifactId}` → 파일 다운로드(`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`)

## 11.8 에러 응답 표준

```json
{ "error": { "code": "E-PDF-READ|E-XLSX-PARSE|E-NO-FILE|E-INVALID-STATE|E-HITL-CANCELLED|...", "message": "설명", "hint": "대응 가이드" } }
```

---

# 12. 내부 실행 상태머신

```
IDLE
 └─(execute)→ PLANNING                // 그래프 스냅샷 확정
 PLANNING
 └─(HITL 필요 시)→ WAITING_HITL       // LangGraph interrupt("approve")
 WAITING_HITL
 └─(continue approve=true)→ RUNNING
 └─(continue approve=false)→ FAILED|CANCELLED
 RUNNING
 ├─ 모든 노드 성공 → SUCCEEDED
 └─ 오류 발생 → FAILED
```

* WAITING_HITL은 LangGraph 인터럽트 기반 중간 정지 상태(승인 API로만 해제).
* 노드 공통: 입력 검증 실패 시 즉시 `FAILED` + `OBS` 에러 이벤트 발행.
* 각 노드 종료 시 `SUMMARY` 1건 보장.

---

# 13. 로깅 & 관측성

* **Run 이벤트 모델**: `seq, ts, type, nodeId, message, detail`
* 서버 로그: INFO(요약), DEBUG(옵션 토글).
* 체크포인트: `/app/storage/checkpoints.sqlite3` (LangGraph 기본/로컬).

---

# 14. 배포 & 환경 구성

## 14.1 Docker/Compose

* 컨테이너: `frontend`, `backend`, `chroma`(볼륨)
* 볼륨: `/app/storage`, `/app/chroma`

## 14.2 .env

* `OPENAI_API_KEY=<키>`

## 14.3 로컬 실행(참고 커맨드 예)

* 백엔드: `uv run uvicorn backend.main:app --reload`
* 프런트: `pnpm dev` 또는 `npm run dev`
* (의존성 예) `uv add langgraph langchain-core chromadb`

---

# 15. 개발 규칙 & Git 정책

## 15.1 원칙

* **기능 단위 최소 커밋**(UI 요소 하나, API 하나 등).

## 15.2 커밋 포맷

* **gitmoji + 타입 + 요약**
  예) `✨ feat: XLSX 편평화 및 부서별 시트 분할 추가`

  * 타입: `feat|fix|refactor|docs|chore|test|perf|style|build`
  * gitmoji 예: ✨(feat) 🐛(fix) ♻️(refactor) 📝(docs) 🧪(test) ♿(a11y) 📦(build)

## 15.3 브랜치

* `feature/*`, `fix/*` → `main`

## 15.4 PR(옵션)

* 제목에 동일 포맷 사용, 설명에 테스트 증거 스크린샷 첨부 권장.

---

# 16. 테스트 & 수용 기준

* **체크리스트**: 로그인 → 업로드 → `/chat/turn` → 그래프 생성/ToT → DnD/Save/Load → `/pipeline/execute` → SSE 수신 → 검증 리포트 → XLSX 다운로드.
* **경계 케이스**: 잘못된 파일 형식, 부서명 미일치, PDF 스니펫 미발견.
* **수용 기준**: §2.2 조건 충족.

---

# 17. 리스크 & 완화

* PDF/엑셀 불일치 다수 발생 가능 → `sum_check`는 **부서 총액** 한정, 불일치 시 “추가 검토 필요” 표기.
* 임베딩 품질/성능 → PDF **샘플링 추출**(chunk), k=3 조회.
* 병렬 실행/고급 편집은 비범위.

---

# 18. 변경 관리

* 버전: **v0.2-poc (LangGraph)**
* ADR(간단)

  * Vector DB: **Chroma** 채택
  * 스트리밍: **SSE** 선택
  * 노드편집 GUI 제외
  * 오케스트레이션 엔진: **LangGraph** 채택(사유: 인터럽트/HITL·체크포인트·그래프형 실행을 표준 제공)

---

# 19. 용어 사전

* **HITL**: Human-in-the-loop(중간 승인)
* **ToT/ReAct**: 추론 과정 **요약 이벤트**로 표기(모델 사유 직접 노출 아님)
* **exists / sum_check**: 텍스트 존재성 / 수치 대조 검증

---

## 부록 A. 샘플 요청/응답(JSON)

**/chat/turn (Req)**

```json
{
  "message": "두 파일을 합쳐서 부서별 집계 후 PDF 기준으로 상이/누락 검토해줘.",
  "fileIds": ["pdf-uuid","xlsx-uuid"]
}
```

**/chat/turn (Res)**

```json
{
  "assistant": "요청을 이해했습니다. 부서별 집계 후 문서 기준으로 검증하겠습니다.",
  "tot": { "steps": ["쿼리 이해", "계획 수립", "그래프 작성"] },
  "graphPatch": {
    "addNodes": [
      {"id":"parse_pdf","type":"parse_pdf","label":"PDF 파싱","config":{"pdf_path":"/app/storage/예산서.pdf","chunk_size":1200,"overlap":200},"in":[],"out":["pdf_chunks"]},
      {"id":"embed_pdf","type":"embed_pdf","label":"PDF 임베딩","config":{"chunks_in":"parse_pdf.pdf_chunks","model":"text-embedding-3-small"},"in":["parse_pdf.pdf_chunks"],"out":["pdf_embeddings"]},
      {"id":"build_vs","type":"build_vectorstore","label":"VectorStore","config":{"embeddings_in":"embed_pdf.pdf_embeddings","collection":"budget_pdf"},"in":["embed_pdf.pdf_embeddings"],"out":["vs_ref"]},
      {"id":"merge_xlsx","type":"merge_xlsx","label":"XLSX 병합","config":{"xlsx_path":"/app/storage/세출-검색용.xlsx","flatten":true,"split":"by_department"},"in":[],"out":["merged_table"]},
      {"id":"validate","type":"validate_with_pdf","label":"검증","config":{"table_in":"merge_xlsx.merged_table","vs_in":"build_vs.vs_ref","policies":["exists","sum_check"],"tolerance":0.005},"in":["merge_xlsx.merged_table","build_vs.vs_ref"],"out":["validation_report"]},
      {"id":"export","type":"export_xlsx","label":"XLSX 내보내기","config":{"table_in":"merge_xlsx.merged_table","filename":"2025년도 제3회 일반 및 기타특별회계 추가경정예산서(세출-검색용).xlsx"},"in":["merge_xlsx.merged_table"],"out":["artifact_path"]}
    ],
    "addEdges":[
      {"from":"parse_pdf","to":"embed_pdf"},
      {"from":"embed_pdf","to":"build_vs"},
      {"from":"merge_xlsx","to":"validate"},
      {"from":"build_vs","to":"validate"},
      {"from":"validate","to":"export"}
    ]
  }
}
```

**/runs/{id}/events (SSE data 예시)**

```
data: {"seq":1,"ts":"2025-10-22T09:01:00+09:00","type":"PLAN","nodeId":"plan","message":"사용자 요청을 쿼리 이해 에이전트로 전달합니다.","detail":{}}

data: {"seq":2,"ts":"2025-10-22T09:01:03+09:00","type":"SUMMARY","nodeId":"plan","message":"파이프라인 초안(6노드) 생성 완료.","detail":{"nodes":6}}
```

**검증 리포트(우측 채팅 렌더용)**

```json
{
  "summary": { "ok": 25, "warn": 8, "fail": 6 },
  "items": [
    { "policy": "exists", "dept": "총무과", "status": "ok", "evidence": [{"page":12,"snippet":"..."}] },
    { "policy": "sum_check", "dept": "복지정책과", "status": "diff", "expected": 119987726, "found": 103674619, "delta": -16313107, "evidence": [{"page":20,"snippet":"..."}] }
  ]
}
```

---

# 부록 B. 그래프 & GraphPatch 예시

## B.1 전체 Workflow 예시(JSON)

*(원문 내용과 동일, 포맷만 정리됨 — 생략 없이 유지)*

```json
{
  "id": "b8f3d0c2-3b1c-4e66-8b6b-1c2c5d4e9a01",
  "name": "구리시_3회추경_검증파이프라인",
  "nodes": [
    { "id": "parse_pdf", "type": "parse_pdf", "label": "PDF 파싱", "config": { "pdf_path": "/app/storage/예산서.pdf", "chunk_size": 1200, "overlap": 200 }, "in": [], "out": ["pdf_chunks"] },
    { "id": "embed_pdf", "type": "embed_pdf", "label": "PDF 임베딩", "config": { "chunks_in": "parse_pdf.pdf_chunks", "model": "text-embedding-3-small" }, "in": ["parse_pdf.pdf_chunks"], "out": ["pdf_embeddings"] },
    { "id": "build_vs", "type": "build_vectorstore", "label": "VectorStore", "config": { "embeddings_in": "embed_pdf.pdf_embeddings", "collection": "budget_pdf" }, "in": ["embed_pdf.pdf_embeddings"], "out": ["vs_ref"] },
    { "id": "merge_xlsx", "type": "merge_xlsx", "label": "XLSX 병합", "config": { "xlsx_path": "/app/storage/세출-검색용.xlsx", "flatten": true, "split": "by_department" }, "in": [], "out": ["merged_table"] },
    { "id": "validate", "type": "validate_with_pdf", "label": "검증", "config": { "table_in": "merge_xlsx.merged_table", "vs_in": "build_vs.vs_ref", "policies": ["exists", "sum_check"], "tolerance": 0.005 }, "in": ["merge_xlsx.merged_table", "build_vs.vs_ref"], "out": ["validation_report"] },
    { "id": "export", "type": "export_xlsx", "label": "XLSX 내보내기", "config": { "table_in": "merge_xlsx.merged_table", "filename": "2025년도 제3회 일반 및 기타특별회계 추가경정예산서(세출-검색용).xlsx" }, "in": ["merge_xlsx.merged_table"], "out": ["artifact_path"] }
  ],
  "edges": [
    { "from": "parse_pdf", "to": "embed_pdf" },
    { "from": "embed_pdf", "to": "build_vs" },
    { "from": "merge_xlsx", "to": "validate" },
    { "from": "build_vs", "to": "validate" },
    { "from": "validate", "to": "export" }
  ],
  "createdAt": "2025-10-22T09:00:00+09:00",
  "updatedAt": "2025-10-22T09:00:00+09:00"
}
```

## B.2 GraphPatch 예시(JSON)

### B.2.1 노드/엣지 추가

```json
{
  "addNodes": [
    { "id": "parse_pdf", "type": "parse_pdf", "label": "PDF 파싱", "config": { "pdf_path": "/app/storage/예산서.pdf", "chunk_size": 1200, "overlap": 200 }, "in": [], "out": ["pdf_chunks"] }
  ],
  "addEdges": []
}
```

### B.2.2 라벨 업데이트

```json
{ "updateLabels": [ { "id": "validate", "label": "정합성 검증(문서 기준)" } ] }
```

### B.2.3 연결 추가 & 제거

```json
{
  "addEdges": [ { "from": "validate", "to": "export" } ],
  "removeEdges": [ { "from": "merge_xlsx", "to": "export" } ]
}
```

### B.2.4 노드 제거

```json
{
  "removeNodes": ["build_vs"],
  "removeEdges": [
    { "from": "embed_pdf", "to": "build_vs" },
    { "from": "build_vs", "to": "validate" }
  ]
}
```

---

# 부록 C. SSE 이벤트 스트림 샘플 로그

> 전송 헤더: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`

## C.1 실행 시작~계획 수립

```
id: 1
event: message
data: {"seq":1,"ts":"2025-10-22T09:01:00+09:00","type":"PLAN","nodeId":"plan","message":"사용자로부터 지시를 수신했습니다. 쿼리 이해 에이전트로 전달합니다.","detail":{"text":"업로드한 데이터를 합쳐 검증 후 XLSX 생성"}}

id: 2
event: message
data: {"seq":2,"ts":"2025-10-22T09:01:02+09:00","type":"OBS","nodeId":"understand","message":"쿼리 이해 결과: 부서별 집계 및 문서 기준 검증 필요.","detail":{"params":{"policies":["exists","sum_check"]}}}

id: 3
event: message
data: {"seq":3,"ts":"2025-10-22T09:01:05+09:00","type":"SUMMARY","nodeId":"plan","message":"파이프라인 초안 생성(노드 6개). 중앙 캔버스에 반영합니다.","detail":{"nodes":6}}
```

## C.2 노드 실행 단계

```
id: 10
event: message
data: {"seq":10,"ts":"2025-10-22T09:01:20+09:00","type":"ACTION","nodeId":"parse_pdf","message":"PDF 파싱을 시작합니다.","detail":{"file":"예산서.pdf","chunk_size":1200}}

id: 11
event: message
data: {"seq":11,"ts":"2025-10-22T09:01:28+09:00","type":"SUMMARY","nodeId":"parse_pdf","message":"PDF 파싱 완료.","detail":{"chunks":1842}}

id: 12
event: message
data: {"seq":12,"ts":"2025-10-22T09:01:29+09:00","type":"ACTION","nodeId":"embed_pdf","message":"PDF 임베딩을 시작합니다.","detail":{"model":"text-embedding-3-small"}}
```

## C.3 검증/결과 표기

```
id: 30
event: message
data: {"seq":30,"ts":"2025-10-22T09:02:10+09:00","type":"OBS","nodeId":"validate","message":"exists 검증: 39개 부서 중 37개 확인, 2개 미발견.","detail":{"ok":37,"miss":2}}

id: 31
event: message
data: {"seq":31,"ts":"2025-10-22T09:02:16+09:00","type":"OBS","nodeId":"validate","message":"sum_check 검증: 28개 일치, 11개 차이(±0.5% 초과).","detail":{"ok":28,"diff":11}}

id: 32
event: message
data: {"seq":32,"ts":"2025-10-22T09:02:20+09:00","type":"SUMMARY","nodeId":"validate","message":"검증 요약을 우측 채팅에 렌더링합니다.","detail":{"policies":["exists","sum_check"]}}
```

## C.4 산출물 완료

```
id: 40
event: message
data: {"seq":40,"ts":"2025-10-22T09:02:35+09:00","type":"ACTION","nodeId":"export","message":"XLSX 산출물을 생성합니다.","detail":{"filename":"2025년도 제3회 일반 및 기타특별회계 추가경정예산서(세출-검색용).xlsx"}}

id: 41
event: message
data: {"seq":41,"ts":"2025-10-22T09:02:38+09:00","type":"SUMMARY","nodeId":"export","message":"XLSX 생성 완료. 좌측 '파일 목록'에서 다운로드할 수 있습니다.","detail":{"artifactId":"art-7d0d"}}
```

---

# 부록 D. XLSX/JSON 스키마 예시

## D.1 XLSX 컬럼 사전(편평화 후)

| 컬럼명           | 타입      | 필수     | 설명                   |
| ------------- | ------- | ------ | -------------------- |
| 회계연도          | string  | 선택     | 연도/차수 표기(예: 2025/3회) |
| 예산구분          | string  | 선택     | 추경/본예산 등 표기          |
| 회계구분명         | string  | **필수** | 일반회계 / (기타)특별회계 명칭   |
| 부서명           | string  | **필수** | 조직 부서 명칭(정규화 적용)     |
| 세부사업명         | string  | 선택     | 세부 사업 명칭             |
| 통계목코드         | string  | 선택     | 분류 코드(예: 201-01)     |
| 통계목명          | string  | 선택     | 분류 명칭                |
| 산출근거          | string  | 선택     | 금액 산정 근거             |
| 예산액           | int(천원) | **필수** | 이번 예산 금액(천원 단위)      |
| 기정액           | int(천원) | 선택     | 직전 예산 금액(천원 단위)      |
| 비교증감          | int(천원) | 선택     | 예산액-기정액 (천원 단위)      |
| 국고보조금         | int(천원) | 선택     | 재원별 세부(있을 때만)        |
| 지역균형발전특별회계보조금 | int(천원) | 선택     | 〃                    |
| 기금보조금         | int(천원) | 선택     | 〃 (음수 가능)            |
| 특별교부세         | int(천원) | 선택     | 〃                    |
| 광역보조금         | int(천원) | 선택     | 〃                    |
| 특별조정교부금       | int(천원) | 선택     | 〃                    |
| 자체재원          | int(천원) | 선택     | 〃                    |

> 전처리 규칙: 천단위 구분기호 제거, 단위=**천원** 유지, 공백/전각 정규화, 결측치 0 대입 금지.

## D.2 검증 리포트 JSON Schema(요약)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ValidationReport",
  "type": "object",
  "properties": {
    "summary": {
      "type": "object",
      "properties": {
        "ok": { "type": "integer" },
        "warn": { "type": "integer" },
        "fail": { "type": "integer" }
      },
      "required": ["ok","warn","fail"]
    },
    "items": {
      "type": "array",
      "items": {
        "oneOf": [
          {
            "type": "object",
            "properties": {
              "policy": { "const": "exists" },
              "dept": { "type": "string" },
              "status": { "enum": ["ok","miss"] },
              "evidence": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "page": { "type": "integer", "minimum": 1 },
                    "snippet": { "type": "string", "minLength": 5, "maxLength": 600 }
                  },
                  "required": ["page","snippet"]
                }
              }
            },
            "required": ["policy","dept","status"]
          },
          {
            "type": "object",
            "properties": {
              "policy": { "const": "sum_check" },
              "dept": { "type": "string" },
              "status": { "enum": ["ok","diff"] },
              "expected": { "type": "integer" },
              "found": { "type": "integer" },
              "delta": { "type": "integer" },
              "evidence": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "page": { "type": "integer", "minimum": 1 },
                    "snippet": { "type": "string", "minLength": 5, "maxLength": 600 }
                  },
                  "required": ["page","snippet"]
                }
              }
            },
            "required": ["policy","dept","status","expected","found"]
          }
        ]
      }
    }
  },
  "required": ["summary","items"]
}
```

## D.3 RunEvent JSON Schema(요약)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "RunEvent",
  "type": "object",
  "properties": {
    "seq": { "type": "integer", "minimum": 1 },
    "ts": { "type": "string", "format": "date-time" },
    "type": { "enum": ["PLAN","ACTION","OBS","SUMMARY"] },
    "nodeId": { "type": "string" },
    "message": { "type": "string", "minLength": 1 },
    "detail": { "type": "object" }
  },
  "required": ["seq","ts","type","message"]
}
```

## D.4 예산 XLSX 결과물 구조(시트/푸터 규칙)

* `개요` 시트:

  * 표 A: 전체 건수, 부서 수, 회계구분 분포
  * 표 B: 총합(예산액/기정액/비교증감)
* `부서명=<이름>` 시트:

  * 원본 컬럼 전부 유지
  * **마지막 행**: `합계` 레코드(예산액/기정액/비교증감 정수합)
  * 정렬: `회계구분명` → `세부사업명` → `통계목코드`
