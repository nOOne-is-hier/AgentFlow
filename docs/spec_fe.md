# v0 요구사항 스펙 + UI/디자인 가이드 (SK CI 테마)

## 0) 목적

* 2일 PoC 시연 범위 내에서 **백엔드가 이미 구현한 기능**을 전제로, **프런트/연동/폴리싱**을 마무리한다.
* 시연 플로우: 로그인 → 파일 업로드/지시(채팅) → 그래프 반영 → 실행(SSE ToT 스트림) → HITL 승인 → XLSX 다운로드 → 어시스턴트 요약 응답.

---

## 1) 현재 백엔드 상태(요약)

* API:
  `POST /auth/login`, `POST /files/upload`, `GET /files`,
  `POST /chat/turn`(GraphPatch), `POST /pipeline/execute`(runId),
  `GET /runs/{runId}`(상태), `GET /runs/{runId}/events`(SSE),
  `POST /runs/{runId}/continue`(HITL 승인/거절), `GET /artifacts/{artifactId}`(다운로드)

* 엔진 노드: `parse_pdf` → `embed_pdf(Chroma)` → `merge_xlsx` → `validate_with_pdf(exists/sum_check)` → `export_xlsx`
  ※ 검증결과는 **파일에 포함하지 않음**(서버 어시스턴트 답장으로만 전달)

* HITL: `STATE_CHECKPOINT` → `WAITING_HITL` → `/runs/{id}/continue`로 승인 시 `export_xlsx` 수행

* **어시스턴트 답장 스위치**: `OPENAI_API_KEY` 있으면 OpenAI 요약, 없으면 로컬 요약 폴백

* **SSE 압축**: 메시지 과다 시 서버가 요약/절단 및 `__compact__` 메타 포함

---

## 2) 사용자 시나리오(동결)

1. 더미 로그인
2. 우측 채팅에서 **PDF 1 + 다수 XLSX** 업로드 또는 첨부 없이 실행(서버가 `storage/splits/<latest>` 수집)
3. “부서별 XLSX들을 병합하고 문서 기준으로 검증 후 XLSX를 내보내줘” 한 문장 지시
4. 중앙 그래프가 생성되고 ToT 이벤트가 스트림으로 흐름
5. 검증 요약 OBS, `STATE_CHECKPOINT` → HITL 승인/거절
6. 승인 시 산출물 생성, 좌측에서 다운로드
7. 마지막에 **어시스턴트 요약 카드** 표출

---

## 3) 정보 구조 & 화면 구성

### 3.1 레이아웃(3-페인 AppShell)

* **좌측 사이드 패널(280px)**: 사용자/세션, 워크플로우 목록, 파일 목록(다운로드 버튼 포함)
* **중앙 그래프 캔버스**: 노드·엣지 시각화 + 상단 툴바(Save/Load/실행)
* **우측 채팅 패널(420px)**: 파일 드롭/업로드, 지시 입력, SSE 이벤트 타임라인, HITL 승인 바, 최종 요약 카드

> 반응형: `xl` 이상 3-페인, `lg`에서 좌측 패널 접힘, `md` 이하는 탭형 전환(파일/그래프/채팅)

### 3.2 상단 앱바(고정)

* 좌: 로고, 제품명 / 우: 사용자 정보(이메일, 사번 끝 4자리), 도움/설정 아이콘

---

## 4) 디자인 시스템 (SK CI 테마)

> **주의**: 아래 컬러 값은 예시. 실제 배포 시 **브랜드 가이드의 공식 HEX**로 교체.

### 4.1 컬러 토큰(CSS 변수)

```css
:root{
  --sk-red:#EA0029; --sk-orange:#FFB600;
  --sk-warm-1:#FF6A00; --sk-warm-2:#FF8C1A;

  --fg:#101012; --fg-muted:#5A5E6A;
  --bg:#FFFFFF; --bg-subtle:#F7F7F9; --border:#E7E7EE;

  --success:#18A957; --warning:#F9A825; --danger:#D32F2F; --info:#2979FF;

  --ev-plan:var(--sk-orange); --ev-action:var(--sk-warm-1);
  --ev-obs:var(--info); --ev-summary:var(--sk-red);
  --ev-hitl:var(--warning); --ev-assistant:var(--sk-orange);

  --shadow-sm:0 1px 2px rgba(16,16,18,.06);
  --shadow-md:0 4px 12px rgba(16,16,18,.10);
  --radius-lg:16px;
}
```

### 4.2 타이포 & 아이콘

* 폰트: Inter/Spoqa/본고딕 계열, 숫자 `tabular-nums`
* 아이콘(lucide-react): PLAN `Map`, ACTION `Play`, OBS `Eye`, SUMMARY `CheckCircle`, HITL `Hand`, ASSIST `MessageSquareText`

### 4.3 그래디언트(선택)

* CTA/프로그레스: `linear-gradient(90deg, var(--sk-red), var(--sk-orange))`

---

## 5) 컴포넌트 스펙

* **AppShell**: Sticky AppBar, 사이드 패널 토글(`lg` 이하)
* **로그인 폼**: 이메일/사번 → `/auth/login` 성공 시 라우팅
* **파일 업로드(드롭존)**: `.pdf,.xlsx` 다중, 진행률, 오류 토스트
* **파일 목록(좌측)**: 파일타입 아이콘/이름/크기/시각, 아티팩트는 다운로드 버튼
* **그래프 캔버스 + 툴바**: 라벨/타입/간단 config 읽기전용, Save/Load/실행
* **SSE 타임라인(우측)**: 카드형 표시(아래 매핑 적용), `__compact__`시 말줄임+더보기
* **HITL 승인 바**: `WAITING_HITL` 수신 시 sticky 노출, 승인/거절/코멘트 → `/runs/{id}/continue`
* **채팅 입력창**: 지시 텍스트, 파일 첨부, Enter 전송/Shift+Enter 줄바꿈
* **어시스턴트 요약 카드**: Markdown 렌더, 강조색 `--ev-assistant`

---

## 6) 이벤트 ↔ 스타일 매핑

| type            | nodeId 예  | 좌측선              | 아이콘               | 제목 예               |
| --------------- | --------- | ---------------- | ----------------- | ------------------ |
| PLAN            | plan      | `--ev-plan`      | Map               | 실행 계획 수립 (N 노드)    |
| ACTION          | parse_pdf | `--ev-action`    | Play              | parse_pdf 시작       |
| OBS             | validate  | `--ev-obs`       | Eye               | 검증 요약 OK/WARN/FAIL |
| SUMMARY         | export    | `--ev-summary`   | CheckCircle       | export 완료          |
| HITL(OBS)       | hitl      | `--ev-hitl`      | Hand              | 승인 대기 중            |
| ASSISTANT_REPLY | assistant | `--ev-assistant` | MessageSquareText | 실행 요약              |

---

## 7) 상호작용 & 상태

* 실행 중 실행 버튼 스피너, 오류 SUMMARY(runtime 실패) 카드에서 “다시 실행”
* SSE 끊김 시 1→2→4… 최대 30s 재시도(지수백오프)

---

## 8) 접근성 & i18n

* `aria-live="polite"`(SSE 컨테이너), 포커스 링 `outline-offset-2` 브랜드 색
* 날짜/숫자 `ko-KR`, 시간대 `Asia/Seoul`

---

## 9) 환경/설정

* `.env`: `OPENAI_API_KEY`(선택), `OPENAI_ASSIST_MODEL=gpt-4o-mini`(기본)
* Tailwind: 위 CSS 변수 바인딩, shadcn/ui 사용

---

## 10) 완료 기준(DoD)

* [ ] PLAN/ACTION/OBS/SUMMARY/HITL/ASSISTANT 모두 렌더
* [ ] `__compact__` 기반 말줄임 + **더보기**
* [ ] HITL 승인/거절 → export_xlsx 수행 & `artifact_id` 확인
* [ ] 좌측 패널 아티팩트 다운로드
* [ ] 그래프 패치 실시간 반영
* [ ] 어시스턴트 요약(마크다운) 렌더
* [ ] SK CI 테마 일관 적용 & 반응형
* [ ] 업로드 누락/SSE 실패/거절 등 기본 오류 UX

---

## 11) QA 체크 포인트(샘플 이벤트 기반)

* `OBS/validate`: `{ok,warn,fail}` 카드가 파란 계열(`--ev-obs`)로 표기
* `OBS/hitl`: 승인 바 노출 → 승인 후 `artifact_id` 수신
* `ASSISTANT_REPLY`: 마크다운 + 길이 제한 시 **더보기** 토글

---

## 12) 구현 힌트 (CSS 베이스)

```css
@layer base{
  :root{ /* 컬러 토큰 */ }
  body{ color:var(--fg); background:var(--bg); }
  .card{ border:1px solid var(--border); border-radius:var(--radius-lg); box-shadow:var(--shadow-sm); }
  .ev-plan{ border-left:4px solid var(--ev-plan); }
  .ev-action{ border-left:4px solid var(--ev-action); }
  .ev-obs{ border-left:4px solid var(--ev-obs); }
  .ev-summary{ border-left:4px solid var(--ev-summary); }
  .ev-hitl{ border-left:4px solid var(--ev-hitl); }
  .ev-assistant{ border-left:4px solid var(--ev-assistant); }
}
```

---

## 13) 브랜드 적용 지침(요약)

* 주요 액션(실행/승인): SK Warm Gradient 버튼(레거시 대응 시 단색 `--sk-red`)
* 강조 정보(요약/CTA): `--sk-orange` 포인트
* 데이터 영역은 중립 톤 유지, 포인트는 **선/보더/좌측선** 위주

---

## 14) 클라이언트–서버 **통신 규격** (Local & Docker Desktop)

### 14.1 공통 원칙

* HTTP/1.1, **JSON(UTF-8)**, SSE는 `text/event-stream` + `Cache-Control: no-cache` + `Connection: keep-alive`

* **세션 쿠키 사용**: 로그인 후 `session` 쿠키 발급 → 프런트는 **반드시**

  * `fetch(..., { credentials: "include" })`
  * `new EventSource(url, { withCredentials: true })`(SSE)

* CORS: 시연 안정화를 위해 **프록시 패턴(Next.js /api 경유)** 권장

### 14.2 엔드포인트 요약

| 메서드     | 경로                         | 설명                                   |
| ------- | -------------------------- | ------------------------------------ |
| POST    | `/auth/login`              | 더미 로그인(세션 쿠키)                        |
| POST    | `/files/upload`            | multipart `files[]`(pdf/xlsx)        |
| GET     | `/files`                   | 업로드 목록                               |
| POST    | `/chat/turn`               | 그래프 패치 생성(§8.3 스키마)                  |
| POST    | `/workflows`               | 워크플로우 저장                             |
| GET     | `/workflows/{id}`          | 워크플로우 조회                             |
| POST    | `/pipeline/execute`        | 실행 시작 → `{ runId }`                  |
| GET     | `/runs/{runId}`            | 실행 상태                                |
| **GET** | **`/runs/{runId}/events`** | **SSE 스트림** (ToT/OBS/HITL/ASSISTANT) |
| POST    | `/runs/{runId}/continue`   | HITL 승인/거절                           |
| GET     | `/artifacts/{artifactId}`  | XLSX 다운로드                            |

**SSE 이벤트 페이로드**

```json
{
  "seq": 12,
  "ts": "2025-10-22T09:12:34+09:00",
  "type": "PLAN|ACTION|OBS|SUMMARY",
  "nodeId": "parse_pdf|embed_pdf|validate|export|hitl|assistant",
  "message": "설명",
  "detail": { "k": "v" },
  "__compact__": { "applied": true, "notes": ["..."] }
}
```

> `ASSISTANT_REPLY`: `type:"SUMMARY"`, `nodeId:"assistant"`, `detail.text`(Markdown)

### 14.3 로컬(dev) 규격

* 포트: 프런트 `http://localhost:3000`, 백엔드 `http://localhost:8000`
* 프런트 `.env.local`

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

* 호출 예시

```ts
const API = process.env.NEXT_PUBLIC_API_BASE_URL!;
await fetch(`${API}/auth/login`,{
  method:"POST", headers:{ "Content-Type":"application/json" },
  credentials:"include", body:JSON.stringify({ email, empno })
});
const es = new EventSource(`${API}/runs/${runId}/events?engine=lg`,{ withCredentials:true });
```

### 14.4 Docker Desktop(Compose) 규격

* 브라우저 기준 경로: `http://localhost:3000`(프론트), `http://localhost:8000`(백엔드)
* 컨테이너 간은 서비스명 사용: `http://backend:8000`

**compose 예시**

```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - USE_LANGGRAPH=1
    volumes:
      - ./storage:/app/storage
      - ./chroma:/app/chroma
    command: uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      - NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
      - INTERNAL_API_BASE_URL=http://backend:8000
    depends_on: [backend]
```

**Next.js 프록시(권장) – SSE 예시**

```ts
// app/api/proxy/runs/[id]/events/route.ts
export async function GET(req:Request,{params}:{params:{id:string}}){
  const backend = process.env.INTERNAL_API_BASE_URL!;
  const url = `${backend}/runs/${params.id}/events?engine=lg`;
  const res = await fetch(url,{ headers:{ cookie: req.headers.get("cookie") ?? "" }, cache:"no-store" });
  return new Response(res.body,{
    headers:{
      "Content-Type":"text/event-stream",
      "Cache-Control":"no-cache",
      "Connection":"keep-alive"
    }
  });
}
```

**프런트 래퍼(권장)**

```ts
// api.ts
const API = process.env.NEXT_PUBLIC_API_BASE_URL!;
export async function post(path:string, body:any){
  const r = await fetch(`${API}${path}`,{
    method:"POST", headers:{ "Content-Type":"application/json" },
    credentials:"include", body:JSON.stringify(body)
  });
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}
export function openSSE(path:string){
  return new EventSource(`${API}${path}`,{ withCredentials:true });
}
```

**리버스 프록시(Nginx 등) 시 SSE 주의**

```
proxy_http_version 1.1;
proxy_set_header Connection "";
proxy_buffering off;
proxy_read_timeout 1h;
send_timeout 1h;
gzip off;
```

---

## 15) 오류/타임아웃/재연결

* **SSE 재연결**: 브라우저 기본 재시도 + 1→2→4… 30s 최대
* **Last-Event-ID**: 서버가 `id:` 헤더 송신(자동 이어받기)
* **업로드 제한**: 브라우저/프록시 `max body size` 50~100MB 권장
* **API 타임아웃**: 일반 30s, SSE 60분+

---

## 16) 통신 체크리스트

* [ ] 로컬: `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`
* [ ] Compose: 브라우저는 `localhost`, 내부는 `backend:8000`
* [ ] 쿠키 전송: `credentials:"include"` / `withCredentials:true`
* [ ] 프록시 사용 시 CORS 이슈 제거 확인
* [ ] SSE 프록시 설정(`proxy_buffering off` 등) 확인
