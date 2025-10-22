from __future__ import annotations
from typing import List, Dict, Any
from openai import OpenAI
from .settings import OPENAI_API_KEY, OPENAI_CHAT_MODEL

SYSTEM_KO = """당신은 데이터 처리 PoC의 어시스턴트입니다.
- 사용자가 업로드한 PDF와 부서별 XLSX를 병합/검증하고, 무엇을/어떻게/어떤 근거로 수행했는지 요약합니다.
- 숫자는 과장 없이, 한국어로 간결히 작성하세요.
- 결과 XLSX 내부에 검증결과를 포함하지 않습니다. 대신 여기 답장에서 근거 스니펫과 수치 비교 요약을 제공합니다.
"""


def build_user_prompt(
    run_meta: Dict[str, Any], events: List[Dict[str, Any]], validation: Dict[str, Any]
) -> str:
    lines = []
    lines.append("# 실행 요약 입력")
    lines.append(f"- runId: {run_meta.get('runId')}")
    lines.append(f"- status: {run_meta.get('status')}")
    lines.append("\n## 이벤트 요약(최근 50개)")
    for ev in events[-50:]:
        t = ev.get("type")
        nid = ev.get("nodeId")
        msg = ev.get("message")
        lines.append(f"- [{t}] {nid}: {msg}")

    if validation:
        s = validation.get("summary", {})
        items = validation.get("items", [])[:10]
        lines.append("\n## 검증 요약")
        lines.append(
            f"- ok={s.get('ok',0)}, warn={s.get('warn',0)}, fail={s.get('fail',0)}"
        )
        lines.append("\n## 대표 항목(최대 10)")
        for it in items:
            if it.get("policy") == "exists":
                lines.append(
                    f"- [exists] {it.get('dept')}: {it.get('status')} (evidence={it.get('evidence')})"
                )
            else:
                lines.append(
                    f"- [sum_check] {it.get('dept')}: {it.get('status')} expected={it.get('expected')} found={it.get('found')} delta={it.get('delta')}"
                )
    return "\n".join(lines)


def generate_assistant_reply(
    run_meta: Dict[str, Any], events: List[Dict[str, Any]], validation: Dict[str, Any]
) -> str:
    if not OPENAI_API_KEY:
        # OpenAI 키가 없으면 서버가 죽지 않도록 안전한 문구 반환
        return "OpenAI API 키가 없어 기본 요약을 제공합니다. PDF 파싱, 부서별 XLSX 병합, 문서기반 exists/sum_check 검증을 수행했고, 결과 XLSX를 생성했습니다."
    client = OpenAI(api_key=OPENAI_API_KEY)
    user_prompt = build_user_prompt(run_meta, events, validation)
    resp = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_KO},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()
