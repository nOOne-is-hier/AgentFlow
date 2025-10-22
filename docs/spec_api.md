# API 스펙 (v0 연동용 최종본)

## 공통

* **Base URL (로컬)**: `http://localhost:8000`
* **인증**: 세션 쿠키(`Set-Cookie: session=...`)

  * 프런트 호출 시 항상 `credentials: "include"`
  * SSE는 `new EventSource(url, { withCredentials: true })`
* **헤더**

  * JSON: `Content-Type: application/json`
  * 업로드: `multipart/form-data`
  * SSE: `text/event-stream`
* **오류 포맷(공통)**

  ```json
  {
    "error": {
      "code": "BAD_REQUEST|UNAUTHORIZED|NOT_FOUND|CONFLICT|INTERNAL",
      "message": "사유 설명",
      "detail": {}
    }
  }
  ```

---

## 1) 로그인

### `POST /auth/login`

더미 로그인 → 세션 쿠키 발급

**Request (JSON)**

```json
{ "email": "user@example.com", "empno": "123456" }
```

**Response 200 (JSON)**

```json
{ "user": { "email": "user@example.com", "empno": "123456" } }
```

**Headers**

* `Set-Cookie: session=...; Path=/; HttpOnly; SameSite=Lax`

**에러**

* 400 누락 필드, 401 인증 실패

---

## 2) 파일 업로드/목록

### `POST /files/upload`

PDF/XLSX 다중 업로드

**Request (multipart/form-data)**

* `files[]`: 하나 이상(.pdf, .xlsx)

**Response 200 (JSON)**

```json
{
  "files": [
    {
      "id": "file-uuid",
      "name": "예산서.pdf",
      "size": 1234567,
      "mime": "application/pdf",
      "uploadedAt": "2025-10-22T06:20:00Z"
    }
  ]
}
```

**에러**

* 400 잘못된 확장자, 413 파일 너무 큼

---

### `GET /files`

업로드 목록 조회

**Response 200 (JSON)**

```json
{
  "files": [
    { "id": "file-uuid", "name": "예산서.pdf", "size": 1234567, "mime": "application/pdf", "uploadedAt": "..." },
    { "id": "file-uuid2", "name": "부서A.xlsx", "size": 34567, "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "uploadedAt": "..." }
  ],
  "artifacts": [
    { "id": "art-fe489ed7", "name": "2025년도 제3회 ... (세출-검색용).xlsx", "createdAt": "..." }
  ]
}
```

---

## 3) 그래프/지시(선택: 시연용)

### `POST /chat/turn`

사용자 지시(프롬프트)→ 워크플로우 패치(시연/선택 기능)

**Request (JSON)**

```json
{
  "text": "부서별 XLSX를 병합하고 문서 기준으로 검증 후 내보내줘",
  "mode": "append"  // "append"|"replace"
}
```

**Response 200 (JSON)**

```json
{ "workflow": { /* 아래 §5의 워크플로우 스키마 */ } }
```

---

## 4) 파이프라인 실행

### `POST /pipeline/execute`

워크플로우 실행 시작 → `runId` 발급

**Request (JSON)**

```json
{
  "workflow": {
    "id": "wf-xxxx",
    "name": "Budget-Validation",
    "nodes": [
      {
        "id": "parse_pdf",
        "type": "parse_pdf",
        "label": "PDF 파싱",
        "config": { "pdf_path": "C:/path/to/file.pdf", "chunk_size": 1200, "overlap": 200 },
        "in": [],
        "out": ["pdf_chunks"]
      },
      {
        "id": "embed_pdf",
        "type": "embed_pdf",
        "label": "PDF 임베딩(Chroma)",
        "config": { "chunks_in": "parse_pdf.pdf_chunks", "reset": true },
        "in": ["parse_pdf.pdf_chunks"],
        "out": ["vs_ref"]
      },
      {
        "id": "merge_xlsx",
        "type": "merge_xlsx",
        "label": "XLSX 병합",
        "config": {
          "xlsx_paths": ["C:/.../부서A.xlsx", "C:/.../부서B.xlsx"],
          "flatten": true,
          "split": "by_department"
        },
        "in": [],
        "out": ["merged_table"]
      },
      {
        "id": "validate",
        "type": "validate_with_pdf",
        "label": "검증(exists/sum_check)",
        "config": { "table_in": "merge_xlsx.merged_table", "tolerance": 0.005 },
        "in": ["merge_xlsx.merged_table"],
        "out": ["validation_report"]
      },
      {
        "id": "export",
        "type": "export_xlsx",
        "label": "XLSX 내보내기",
        "config": {
          "table_in": "merge_xlsx.merged_table",
          "filename": "2025년도 제3회 ... (세출-검색용).xlsx"
        },
        "in": ["merge_xlsx.merged_table"],
        "out": ["artifact_path"]
      }
    ],
    "edges": [
      { "from": "parse_pdf", "to": "embed_pdf" },
      { "from": "merge_xlsx", "to": "validate" },
      { "from": "validate", "to": "export" }
    ]
  }
}
```

> **참고**: `xlsx_paths`를 비우면 서버가 `storage/splits/<latest>`를 자동 수집(시연 기본).

**Response 200 (JSON)**

```json
{ "runId": "2c0dfa18-d919-43ef-a069-534decbcaf45", "status": "QUEUED" }
```

**에러**

* 400 워크플로우 유효성 실패, 500 내부 오류

---

## 5) 실행 상태 조회

### `GET /runs/{runId}`

현재 실행 상태 + 메타

**Response 200 (JSON)**

```json
{
  "runId": "2c0dfa18-d919-43ef-a069-534decbcaf45",
  "status": "RUNNING|SUCCEEDED|FAILED|WAITING_HITL|CANCELLED",
  "startedAt": "2025-10-22T06:55:25.965100Z",
  "endedAt": "2025-10-22T06:55:33.839391Z",
  "artifactId": "art-2c0dfa18",
  "workflow": { /* 요청 시 전달한 워크플로우 echo */ }
}
```

**에러**

* 404 runId 없음

---

## 6) 실행 이벤트 스트림 (SSE)

### `GET /runs/{runId}/events?engine=lg`

실시간 ToT/OBS/HITL/요약 이벤트 스트림

* `engine=lg`(기본) 사용 권장

**Response (SSE)**

```
id: 2
event: message
data: {
  "type": "PLAN|ACTION|OBS|SUMMARY",
  "nodeId": "parse_pdf|embed_pdf|validate|export|hitl|assistant|runtime",
  "message": "설명 텍스트",
  "detail": { "k": "v" },
  "ts": "2025-10-22T07:10:24.706510+00:00",
  "seq": 1,
  "__compact__": { "applied": true, "notes": ["..."] }
}
```

**이벤트 타입 & 페이로드**

* `PLAN` — 실행 계획 수립

  ```json
  { "detail": { "nodes": 5 } }
  ```
* `ACTION` — 노드 시작

  ```json
  { "nodeId": "parse_pdf", "message": "parse_pdf(parse_pdf) 시작" }
  ```
* `OBS` — 중간 관찰치/체크포인트

  * `parse_pdf`: `{"chunks": 755, "pages": 548}`
  * `embed_pdf`: `{"count": 755}`
  * `merge_xlsx`: `{"rows": 1587}`
  * `validate`: `{"ok": 2, "warn": 2, "fail": 0}`
  * `hitl/STATE_CHECKPOINT`:

    ```json
    {
      "state": {
        "merged_path": "C:/.../tmp\\2c0dfa18_merged.csv",
        "validation_report": {
          "summary": {"ok":2,"warn":2,"fail":0},
          "items": [ /* 증거 스니펫 배열 (길면 서버가 압축) */ ]
        }
      }
    }
    ```
  * `hitl/WAITING_HITL`: 승인 대기 진입
* `SUMMARY` — 단계 완료/실패/최종 요약

  * 노드 완료: `{"keys":["..."], "__keys_meta__":{"total":2,"shown":2,"truncated":false}}`
  * 런타임 실패: `{"message":"실패: ..."}`
  * **어시스턴트 답장**: `nodeId:"assistant"`, `message:"ASSISTANT_REPLY"`, `detail.text`(Markdown)

**길이 최적화(중요)**

* 서버가 장문을 **절단/요약**하면

  * 상위 필드에 `__compact__.applied=true`
  * 길이 제한이 적용된 필드에는 `__keys_meta__` 또는 `__items_meta__` 포함

---

## 7) HITL 승인/거절

### `POST /runs/{runId}/continue`

HITL 상태(`WAITING_HITL`)에서 승인/거절

**Request (JSON)**

```json
{ "action": "approve", "comment": "내보내기 진행" }
// 또는
{ "action": "reject", "comment": "취소합니다" }
```

**Response 200 (JSON)**

```json
{ "runId": "2c0dfa18-...", "status": "RUNNING|CANCELLED" }
```

* `approve` → 서버가 즉시 `export_xlsx` 수행(이벤트로 진행 상황 송신)
* `reject` → 실행 취소(SSE에 `"사용자 거부로 취소"` 요약 표시)

**에러**

* 409 현재 상태가 승인 대기 아님

---

## 8) 산출물 다운로드

### `GET /artifacts/{artifactId}`

최종 XLSX 다운로드

**Response 200 (binary)**

* Headers:

  * `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  * `Content-Disposition: attachment; filename="2025년도 제3회 ... (세출-검색용).xlsx"`

**에러**

* 404 artifactId 없음

---

## 9) 워크플로우 스키마(요약)

```ts
type Workflow = {
  id: string;
  name: string;
  nodes: Node[];
  edges: { from: string; to: string }[];
  createdAt?: string; updatedAt?: string;
};

type Node =
| {
    id: "parse_pdf";
    type: "parse_pdf";
    label?: string;
    config: { pdf_path: string; chunk_size?: number; overlap?: number };
    in: []; out: ["pdf_chunks"];
  }
| {
    id: "embed_pdf";
    type: "embed_pdf";
    label?: string;
    config: { chunks_in: string; reset?: boolean };
    in: [string]; out: ["vs_ref"];
  }
| {
    id: "merge_xlsx";
    type: "merge_xlsx";
    label?: string;
    config: {
      xlsx_paths?: string[]; // 없으면 storage/splits/<latest> 자동 수집
      flatten?: boolean;
      split?: "by_department" | string;
    };
    in: []; out: ["merged_table"];
  }
| {
    id: "validate";
    type: "validate_with_pdf";
    label?: string;
    config: { table_in: string; tolerance?: number };
    in: [string]; out: ["validation_report"];
  }
| {
    id: "export";
    type: "export_xlsx";
    label?: string;
    config: { table_in: string; filename: string };
    in: [string]; out: ["artifact_path"];
  };
```

---

## 10) 프런트 연동 예시

```ts
// 로그인
await fetch(`${API}/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  credentials: "include",
  body: JSON.stringify({ email, empno })
});

// 실행
const { runId } = await fetch(`${API}/pipeline/execute`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  credentials: "include",
  body: JSON.stringify({ workflow })
}).then(r => r.json());

// SSE 구독
const es = new EventSource(`${API}/runs/${runId}/events?engine=lg`, { withCredentials: true });
es.onmessage = (ev) => {
  const payload = JSON.parse(ev.data);
  // type/nodeId/message/detail/__compact__ 처리
};

// HITL 승인
await fetch(`${API}/runs/${runId}/continue`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  credentials: "include",
  body: JSON.stringify({ action: "approve", comment: "진행" })
});

// 산출물 다운로드 링크
const href = `${API}/artifacts/${artifactId}`;
```

---

## 11) 상태 값 요약

* 런 상태: `QUEUED` → `RUNNING` → (`WAITING_HITL` → `RUNNING`) → `SUCCEEDED | FAILED | CANCELLED`
* 이벤트 타입: `PLAN`, `ACTION`, `OBS`, `SUMMARY`(어시스턴트 포함), `runtime 실패`도 `SUMMARY`로 전달

---

## 12) 주의사항

* SSE는 프록시/게이트웨이에서 **버퍼링 끔**(proxy_buffering off) 필요
* 대용량 이벤트는 서버가 요약/절단 → `__compact__` 플래그로 클라이언트에서 “더보기” 토글 제공
* OpenAI 요약 스위치: 서버 `.env`에 `OPENAI_API_KEY`가 있으면 OpenAI 응답, 없으면 로컬 요약 (클라이언트 변경 불필요)
