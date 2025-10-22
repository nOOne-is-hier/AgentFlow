## 0. 오프닝 (임팩트)

### 1) 타이틀 — “자연어로 만드는 기업형 자동화 파이프라인”

* 말하기: “안녕하세요. 오늘은 **자연어 한 줄**로 **기업용 자동화 파이프라인**을 만들고, 문서 기준 **정합성 검증**까지 끝내는 PoC를 소개합니다.”
* 화면:

  * 메인 타이포: “Natural Language → Pipeline + UI → Validation → XLSX”
  * 서브: “Next.js / FastAPI / Chroma / OpenAI / SSE / Docker”

### 2) 콜드오픈 데모(60초)

* 말하기: “데모 먼저 보겠습니다. **‘두 파일 합쳐서 검증 후 XLSX 생성’**이라고 채팅에 입력하면… 그래프가 생성되고, 실행 후 **다운로드 토스트**가 뜹니다.”
* 화면:

  * [애니메이션] 채팅 입력 → 그래프 노드 자동 생성 → 실행 진행바 → “download.xlsx” 토스트
  * 캡션: “우측 채팅 = 단일 인터페이스(업로드/지시/HITL/ToT/결과)”

---

## WHAT: 우리는 무엇을 만드는가

### 3) Executive Summary

* 말하기: “문서·스프레드시트 기반의 **취합/검증/산출** 업무를 **자연어 지시**로 자동화합니다. **B2B 온프렘** 우선, 내부자료 **정합성 검증**을 핵심 가치로 삼았습니다.”
* 화면: 3단 카드 — Problem / Solution / Impact (시간·오류·학습비용 절감)

### 4) 제품 한눈에(유저 여정)

* 말하기: “로그인 → 파일 업로드 → 채팅 지시 → 그래프 자동생성(DnD/Save/Load) → 실행 → **검증 리포트** → XLSX 다운로드까지 한 화면에서 끝납니다.”
* 화면: [이미지] 사용자 여정 다이어그램

### 5) PoC 시나리오(구리시 예산)

* 말하기: “구리시 공개 자료(**PDF 541p, XLSX**)를 사용해 실제처럼 시연합니다. 페이지·파일은 시 홈페이지에 공개돼 있습니다.” ([구리시청][1])
* 화면: [이미지] 문서 썸네일 2장 + 출처 표기

### 6) 핵심 기능(슬라이드)

* 말하기: “**한 개의 우측 채팅**으로 업로드·지시·HITL·ToT/ReAct·결과 렌더를 모두 수행합니다. 중앙 캔버스는 **그래프 DnD & Save/Load**만 제공합니다(편집은 채팅으로).”
* 화면: [이미지] UI 3분할(좌패널/캔버스/우측 채팅) 와이어프레임

---

## WHY: 왜 지금 이것인가

### 7) Pain & 기회

* 말하기: “대부분의 예산·기획 업무는 **대용량 PDF+엑셀 취합/대사**가 핵심입니다. 사람 손으로 하면 **리드타임과 오류**가 큽니다. **자연어 + UI**로 진입장벽을 낮출 때입니다.”
* 화면: [도표] 수작업 단계 vs 자동화 단계

### 8) 시장·경쟁(요약)

* 말하기: “Zapier/Make/Retool/n8n은 워크플로우 표준입니다. 엔터프라이즈 보안·가시성·온프렘을 중시하는 국내 수요도 큽니다.”

  * Zapier **기업 보안·컴플라이언스(SOC2/GDPR)**, Retool **워크플로우(크론/웹훅)**, Make **시각 오케스트레이션**·엔터프라이즈 보안, n8n **온프렘·Docker** 제공. ([help.zapier.com][2])
* 화면: [표] 기능 비교(시각오케스트레이션/온프렘/보안표기/에이전틱 지원)

### 9) 차별화 포인트

* 말하기: “우리는 **자연어→그래프 자동생성 + ToT 시각화 + 문서 기준 정합성 검증**에 집중합니다. B2B 온프렘 적합성을 기본값으로 설계했습니다.”
* 화면: [아이콘] NL 파서 / Vector 검증 / HITL

### 10) 비즈니스 가치

* 말하기: “**리드타임 단축, 오류 감소, 컴플라이언스 대응, 현업 자가구축**이 핵심 가치입니다. 특히 **검증(Exists/Sum)**은 ‘그냥 자동화’가 아닌 **감사 가능한 자동화**를 만듭니다.”
* 화면: [차트] 전/후 KPI(처리시간, 누락율)

---

## HOW1: 우리는 **어떻게 만들었는가** (기술)

### 11) 시스템 개요(아키텍처)

* 말하기: “**Next.js+Tailwind(shadcn)** 프런트, **FastAPI** 백엔드, **Chroma**로 벡터 검색, **OpenAI 임베딩**, 이벤트는 **SSE**로 스트리밍합니다.”

  * Next.js는 **풀스택 React 프레임워크**, Tailwind는 **유틸리티-퍼스트 CSS**, shadcn/ui는 **복사-확장형 컴포넌트**. ([Next.js][3])
  * Chroma는 **오픈소스 벡터DB**, 로컬 실행 쉬움. ([Chroma Docs][4])
  * SSE는 서버→브라우저 단방향 스트림(EventSource). ([MDN 웹 문서][5])
* 화면: [이미지] 아키텍처 블록 다이어그램

### 12) 멀티 에이전트 오케스트레이션(역할 체인)

* 말하기: “**단일 모델**을 역할 프롬프트로 체인화해 **쿼리이해→계획→실행→검증→병합**을 수행합니다. 이벤트는 **PLAN/ACTION/OBS/SUMMARY**로 표준화.”
* 화면: [이미지] 5단계 파이프 + 이벤트 스트림 타임라인

### 13) 파이프라인 스키마(그래프)

* 말하기: “노드는 `parse_pdf / embed_pdf / build_vectorstore / merge_xlsx / validate_with_pdf / export_xlsx`. **GraphPatch**로 중앙 캔버스에 실시간 반영.”
* 화면: [코드블럭 요약] 노드 config 키, 엣지 연결 예시(텍스트)

### 14) ToT / ReAct 스트리밍

* 말하기: “모델의 상세 사유 대신, **행동 중심 이벤트**(계획·실행·관측·요약)를 스트림으로 보여줍니다. 표준 **`text/event-stream`** 규격을 따릅니다.” ([MDN 웹 문서][6])
* 화면: [텍스트 이미지] SSE 샘플 로그 3건

### 15) 데이터 스키마 & 분할

* 말하기: “XLSX 멀티헤더를 **편평화**하고, **개요 시트 + 부서별 시트**로 분할·합계합니다. 단위는 **천원**.”
* 화면: [표] 컬럼 사전(회계구분/부서명/예산액/기정액/비교증감…)
* 각주: “원본 데이터는 구리시 공개자료.” ([구리시청][1])

### 16) 검증 정책(Exists + SumCheck)

* 말하기: “`exists`는 부서명 키워드를 **PDF 스니펫**으로 확인, `sum_check`는 **부서 총액**을 문서 기준으로 ±0.5% 비교합니다.”
* 화면: [예시]

  * exists: “복지정책과” → p.20 스니펫
  * sum_check: expected 119,987,726 / found 103,674,619 → diff 표시

### 17) Docker 패키징(가산점 포인트)

* 말하기: “**Docker Compose**로 프런트/백/Chroma를 묶어 **`docker compose up`** 한 번에 시연 가능합니다. Compose와 Dockerfile은 공식 스펙을 따릅니다.” ([Docker Documentation][7])
* 화면: [텍스트 이미지] `docker compose up -d` / 간단한 compose.yaml 스니펫

---

## HOW2: **이 프로젝트를 어떻게 수행했는가** (학습/프로세스)

### 18) v0 빠른 프로토타이핑

* 말하기: “**콜드오픈 가능한 최소 루프**를 먼저 만들었습니다. ‘채팅 한 줄 → 그래프 생성 → 실행 → XLSX’가 1분 내로 보이도록 범위를 자르고, 병렬 실행 등은 제외했습니다.”
* 화면: [체크리스트] 범위 내/외

### 19) Spec→Vibe Engineering(SDD 실현)

* 말하기: “**ChatGPT로 명세를 고정**하고, **계약(JSON 스키마·API)**을 먼저 확정한 뒤 코드에 반영했습니다. 이 흐름이 **납기/품질**을 지켰습니다.”
* 화면: [이미지] 명세→타입정의→엔드포인트→데모 루프 다이어그램

### 20) 개발환경 & 규칙

* 말하기: “**uv + Python 3.11.11 / VSCode**. 프런트는 **Next.js + Tailwind + shadcn/ui**. **기능 단위 커밋** 원칙, **gitmoji + 타입** 포맷(예: `✨ feat:`).”
* 화면: [텍스트] 커밋 포맷 규칙 예시

### 21) 납기·품질 관리

* 말하기: “수용 기준을 **데모 시퀀스**로 정의하고, 경계 테스트(파일 오류/스니펫 미발견)를 체크했습니다. 벡터 검색은 **Chroma 로컬**로 안정화.” ([Chroma Docs][8])
* 화면: [체크리스트] 수용 기준 / 경계 케이스

---

## 마무리

### 22) PoC 결과 & 한계

* 말하기: “**된다**를 증명했습니다. 다만 부서 총액 불일치 등 **회계 대사 정밀화**는 다음 단계 과제입니다. 병렬 실행·권한·템플릿도 로드맵으로.”
* 화면: [표] 된다/안된다

### 23) 로드맵(2주/2달)

* 말하기: “2주—스케줄러·권한·템플릿. 2달—내부 API 카탈로그, 멀티 문서 비교, 감사 리포트.”
* 화면: [타임라인] 2주/2달 마일스톤

### 24) Go-To-Market(요약)

* 말하기: “초기 타깃은 **공공·금융·제조**. 파일 기반 PoV → 내부 시스템 연동으로 확장. 보안·컴플라이언스는 벤치마크 서비스 기준을 준용.”

  * (참고: 경쟁사 엔터프라이즈 보안 레퍼런스) ([help.zapier.com][2])
* 화면: [퍼널] PoV → 파일·API 통합 → 확산

### 25) Call to Action

* 말하기: “**귀 조직의 파일 샘플**과 **온프렘 시연 환경**을 제공해 주시면 **1주 PoV** 제안 드립니다.”
* 화면: [버튼 이미지] “PoV 시작하기”

### 26) Q&A

* 말하기: “감사합니다. 질문 받겠습니다.”
* 화면: 간단 로고

---

## (선택) 백업 슬라이드에 쓸 수 있는 근거 자료 링크

* **구리시 예산 페이지**(PDF/XLSX 공개) ([구리시청][1])
* **Brity Works**(삼성SDS 협업/자동화·보안) ([Samsung SDS][9])
* **LG CNS AgenticWorks 발표 기사**(에이전틱 플랫폼 출시) ([Korea Herald][10])
* **Make(전 인테그로마트) AI 오케스트레이션/보안** ([Make][11])
* **Retool Workflows**(잡/ETL/스케줄/웹훅) ([docs.retool.com][12])
* **n8n**(셀프호스팅·Docker·온프렘) ([n8n.io][13])
* **SSE 표준/가이드**(WHATWG/MDN) ([html.spec.whatwg.org][14])
* **Chroma**(오픈소스 벡터DB, 로컬 실행) ([Chroma Docs][4])
* **OpenAI 임베딩 가이드/모델**(text-embedding-3) ([OpenAI 플랫폼][15])
* **Docker Compose·Dockerfile** 공식 문서 ([Docker Documentation][7])

---

### 발표 팁(10–12분 기준)

* 2번(콜드오픈)에 **가장 많은 에너지**를 씁니다. 시연 성공이 분위기를 좌우합니다.
* 11~17번(HOW1)은 **한 장당 30–40초**로 템포있게.
* 19번(Spec→Vibe)에서 **명세 캡처 1장 + 커밋 로그 1장**을 보여주면 납기·품질에 강하게 먹힙니다.

[1]: https://www.guri.go.kr/www/selectBbsNttView.do?bbsNo=10&integrDeptCode=&key=324&nttNo=130854&pageIndex=1&searchCnd=all&searchCtgry=&searchKrwd=&utm_source=chatgpt.com "열린행정 > 재정현황 > 예산서 - 구리시"
[2]: https://help.zapier.com/hc/en-us/articles/8496181993613-Security-and-Compliance?utm_source=chatgpt.com "Security and Compliance"
[3]: https://nextjs.org/docs?utm_source=chatgpt.com "Next.js Docs | Next.js"
[4]: https://docs.trychroma.com/?utm_source=chatgpt.com "Chroma Docs: Introduction"
[5]: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events?utm_source=chatgpt.com "Server-sent events - Web APIs | MDN - Mozilla"
[6]: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events?utm_source=chatgpt.com "Using server-sent events - Web APIs | MDN - Mozilla"
[7]: https://docs.docker.com/compose/?utm_source=chatgpt.com "Docker Compose"
[8]: https://docs.trychroma.com/getting-started?utm_source=chatgpt.com "Getting Started - Chroma Docs"
[9]: https://www.samsungsds.com/en/workspace/workspace.html?utm_source=chatgpt.com "Automation/Collaboration | Enterprise IT Solutions"
[10]: https://www.koreaherald.com/article/10561390?utm_source=chatgpt.com "LG CNS unveils agentic AI to boost corporate productivity"
[11]: https://www.make.com/en?utm_source=chatgpt.com "Make | AI Workflow Automation Software & Tools | Make"
[12]: https://docs.retool.com/workflows/?utm_source=chatgpt.com "Retool Workflows documentation"
[13]: https://n8n.io/?utm_source=chatgpt.com "AI Workflow Automation Platform & Tools - n8n"
[14]: https://html.spec.whatwg.org/multipage/server-sent-events.html?utm_source=chatgpt.com "9.2 Server-sent events - HTML Standard - WhatWG"
[15]: https://platform.openai.com/docs/guides/embeddings/what-are-embeddings?%3Butm_campaign=airflow-in-action-bam&%3Butm_medium=web&utm_cta=website-homepage-hero-live-demo%3Fwtime&wtime=4s&utm_source=chatgpt.com "Vector embeddings - OpenAI API"
