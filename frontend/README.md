# Budget Validation System - Frontend

SK CI 예산 검증 자동화 시스템의 프론트엔드 애플리케이션입니다.

## 기술 스택

- **Framework**: Next.js 16 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS 4
- **UI Components**: shadcn/ui + Radix UI
- **Graph Visualization**: React Flow
- **Markdown**: react-markdown
- **State Management**: React Hooks

## 시작하기

### 필수 요구사항

- Node.js 18.x 이상
- npm 또는 yarn

### 설치

\`\`\`bash
cd frontend
npm install
\`\`\`

### 환경 변수 설정

`.env.local` 파일을 생성하고 다음 내용을 추가하세요:

\`\`\`env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
\`\`\`

### 개발 서버 실행

\`\`\`bash
npm run dev
\`\`\`

브라우저에서 [http://localhost:3000](http://localhost:3000)을 열어 확인하세요.

### 빌드

\`\`\`bash
npm run build
npm start
\`\`\`

## 주요 기능

### 1. 로그인
- 더미 인증 (이메일 + 사번)
- `/login` 페이지

### 2. 파일 관리
- 드래그 앤 드롭 업로드
- PDF, XLSX 파일 지원
- 업로드된 파일 목록
- 생성된 아티팩트 다운로드

### 3. 워크플로우 그래프
- React Flow 기반 시각화
- 노드 타입별 색상 구분
- 실행/저장 기능

### 4. 채팅 인터페이스
- 자연어 지시 입력
- SSE 실시간 이벤트 스트림
- 이벤트 타입별 카드 렌더링

### 5. HITL 승인
- 검증 리포트 표시
- 승인/거절 버튼
- 코멘트 입력

### 6. 어시스턴트 요약
- 마크다운 렌더링
- 접기/펼치기 기능

## 프로젝트 구조

\`\`\`
frontend/
├── app/                    # Next.js App Router
│   ├── login/             # 로그인 페이지
│   ├── workspace/         # 작업 공간
│   ├── globals.css        # 전역 스타일
│   └── layout.tsx         # 루트 레이아웃
├── components/            # React 컴포넌트
│   ├── ui/               # shadcn/ui 컴포넌트
│   ├── app-shell.tsx     # 3-페인 레이아웃
│   ├── file-upload.tsx   # 파일 업로드
│   ├── file-list.tsx     # 파일 목록
│   ├── graph-canvas.tsx  # 그래프 시각화
│   ├── chat-panel.tsx    # 채팅 패널
│   ├── event-card.tsx    # SSE 이벤트 카드
│   └── ...
├── hooks/                 # Custom React Hooks
│   ├── use-sse.ts        # SSE 훅
│   └── use-toast.ts      # Toast 훅
├── lib/                   # 유틸리티
│   ├── api.ts            # API 클라이언트
│   └── utils.ts          # 헬퍼 함수
├── types/                 # TypeScript 타입
│   └── index.ts
└── package.json
\`\`\`

## API 연동

백엔드 API는 `http://localhost:8000`에서 실행되어야 합니다.

주요 엔드포인트:
- `POST /auth/login` - 로그인
- `POST /files/upload` - 파일 업로드
- `GET /files` - 파일 목록
- `POST /chat/turn` - 채팅 메시지
- `POST /pipeline/execute` - 파이프라인 실행
- `GET /runs/{runId}/events` - SSE 이벤트 스트림
- `POST /runs/{runId}/continue` - HITL 승인

## 접근성

- ARIA 레이블 및 역할 적용
- 키보드 네비게이션 지원
- 스크린 리더 호환
- 포커스 링 스타일

## 반응형 디자인

- `xl` 이상: 3-페인 고정 레이아웃
- `lg`: 좌측 패널 토글
- `md` 이하: 모바일 최적화 (오버레이)

## 라이선스

MIT
