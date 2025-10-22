from __future__ import annotations
import os
from pathlib import Path


# ── .env 자동 로드 ─────────────────────────────────────────────────────────────
# 우선순위:
#  1) ENV_FILE 환경변수로 지정한 경로
#  2) 프로젝트 루트(.env)  -> 보통 backend/와 같은 레벨
#  3) backend 폴더 내부(.env)
def _load_dotenv():
    try:
        from dotenv import load_dotenv
    except Exception:
        # python-dotenv가 없으면 그냥 패스 (런타임에서 env 직접 주입해야 함)
        return

    here = Path(__file__).resolve().parent  # .../backend
    root = here.parent  # 프로젝트 루트 (backend와 같은 레벨)
    candidates = []

    env_file = os.getenv("ENV_FILE")
    if env_file:
        candidates.append(Path(env_file))

    candidates += [root / ".env", here / ".env"]

    for p in candidates:
        if p.exists():
            # override=False: 이미 셸/도커 환경에 들어온 값은 덮어쓰지 않음
            load_dotenv(p.as_posix(), override=False)


# .env 로딩 실행
_load_dotenv()

# ── OpenAI ─────────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
OPENAI_EMBED_MODEL: str = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
OPENAI_CHAT_MODEL: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT: str = Path.cwd().as_posix()
STORAGE: str = (Path(ROOT) / "storage").as_posix()
UPLOADS: str = (Path(STORAGE) / "uploads").as_posix()
WF_DIR: str = (Path(STORAGE) / "workflows").as_posix()
RUN_DIR: str = (Path(STORAGE) / "runs").as_posix()
ART_DIR: str = (Path(STORAGE) / "artifacts").as_posix()
TMP_DIR: str = (Path(STORAGE) / "tmp").as_posix()

# ── Vector DB (Chroma) ─────────────────────────────────────────────────────────
CHROMA_DIR: str = (Path(ROOT) / "chroma").as_posix()
CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "budget_pdf")

# ── Misc ───────────────────────────────────────────────────────────────────────
APP_VERSION: str = "0.5.1-poc"
TZ_NAME: str = "Asia/Seoul"
FILES_INDEX: str = (Path(STORAGE) / "files.index.json").as_posix()

# 디렉터리 생성
Path(UPLOADS).mkdir(parents=True, exist_ok=True)
Path(WF_DIR).mkdir(parents=True, exist_ok=True)
Path(RUN_DIR).mkdir(parents=True, exist_ok=True)
Path(ART_DIR).mkdir(parents=True, exist_ok=True)
Path(TMP_DIR).mkdir(parents=True, exist_ok=True)
Path(CHROMA_DIR).mkdir(parents=True, exist_ok=True)
