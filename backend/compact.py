from __future__ import annotations
from typing import Any, Dict, List, Tuple, Union

# ====== 기본 한도 (원하면 settings.py로 빼서 환경변수화 가능) ======
MAX_EVENT_TEXT_CHARS = 800  # 이벤트 내 단일 텍스트 최대 길이
MAX_SNIPPET_CHARS = 180  # 스니펫 미리보기 길이
MAX_ARRAY_ITEMS = 6  # 배열은 앞쪽 N개만 노출
MAX_STATE_BYTES = 32_000  # state 전체 직렬화 바이트 상한(거칠게)

TextLike = Union[str, bytes]


def _shorten_text(s: TextLike, limit: int = MAX_EVENT_TEXT_CHARS) -> Tuple[str, bool]:
    if isinstance(s, bytes):
        try:
            s = s.decode("utf-8", errors="replace")
        except Exception:
            s = str(s)
    s = str(s)
    if len(s) <= limit:
        return s, False
    head = limit - 1
    return s[:head] + "…", True


def _short_snippet(s: TextLike, limit: int = MAX_SNIPPET_CHARS) -> str:
    t, _ = _shorten_text(s, limit)
    return t


def _compact_list(
    lst: List[Any],
    item_limit: int = MAX_ARRAY_ITEMS,
    per_text_limit: int = MAX_SNIPPET_CHARS,
):
    """리스트는 앞쪽 N개만 유지, 텍스트 필드는 스니펫으로 축약."""
    truncated = False
    out = []
    for i, it in enumerate(lst):
        if i >= item_limit:
            truncated = True
            break
        if isinstance(it, dict):
            d2 = {}
            for k, v in it.items():
                if isinstance(v, (str, bytes)):
                    d2[k] = _short_snippet(v, per_text_limit)
                elif isinstance(v, list):
                    d2[k], _ = _compact_list(
                        v, item_limit=item_limit, per_text_limit=per_text_limit
                    )
                else:
                    d2[k] = v
            out.append(d2)
        elif isinstance(it, (str, bytes)):
            out.append(_short_snippet(it, per_text_limit))
        else:
            out.append(it)
    meta = {
        "total": len(lst),
        "shown": len(out),
        "truncated": truncated or (len(lst) > len(out)),
    }
    return out, meta


def _sizeof(obj: Any) -> int:
    try:
        import json

        return len(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return 0


def compact_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    """
    거대한 이벤트(detail/state/pdf_chunks/텍스트 배열 등)를
    프리뷰 중심으로 '요약/자르기' 하여 전송 크기를 제한한다.
    - 원본을 클라이언트에 모두 보내지 않는다(요구사항: "시간 없으니 자르거나 요약").
    - UI가 '확장' 버튼을 그릴 수 있도록 __compact 메타 정보 동봉.
    """
    if not isinstance(ev, dict):
        return ev
    e = dict(ev)  # shallow copy

    detail = e.get("detail")
    compact_meta = {"applied": False, "notes": []}

    # 1) detail.state 가 거대하면 요약
    if isinstance(detail, dict) and "state" in detail:
        st = detail["state"]
        if isinstance(st, dict):
            st_size = _sizeof(st)
            # 대표적으로 pdf_chunks 폭주 방지
            if "pdf_chunks" in st and isinstance(st["pdf_chunks"], list):
                chunks = st["pdf_chunks"]
                compacted, meta = _compact_list(
                    chunks, item_limit=MAX_ARRAY_ITEMS, per_text_limit=MAX_SNIPPET_CHARS
                )
                st_preview = dict(st)
                st_preview["pdf_chunks"] = compacted
                st_preview["__pdf_chunks_meta__"] = meta
                compact_meta["applied"] = True
                compact_meta["notes"].append(f"state.pdf_chunks truncated: {meta}")
                detail["state"] = st_preview

            # state 전체 크기 상한
            if _sizeof(detail["state"]) > MAX_STATE_BYTES:
                # 핵심 키만 남기고 나머지는 제거
                keep_keys = [
                    "merged_path",
                    "validation_report",
                    "artifact_id",
                    "__pdf_chunks_meta__",
                ]
                new_state = {k: v for k, v in detail["state"].items() if k in keep_keys}
                new_state["__state_truncated__"] = True
                compact_meta["applied"] = True
                compact_meta["notes"].append("state size limit -> kept core keys")
                detail["state"] = new_state

    # 2) detail 내 문자열/배열 일반 축약
    def _walk(obj):
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if isinstance(v, (str, bytes)):
                    t, trunc = _shorten_text(v, MAX_EVENT_TEXT_CHARS)
                    if trunc:
                        compact_meta["applied"] = True
                        compact_meta["notes"].append(f"detail.{k} text truncated")
                    out[k] = t
                elif isinstance(v, list):
                    arr, meta = _compact_list(v, MAX_ARRAY_ITEMS, MAX_SNIPPET_CHARS)
                    if meta.get("truncated"):
                        compact_meta["applied"] = True
                        compact_meta["notes"].append(
                            f"detail.{k} list truncated: {meta}"
                        )
                    out[k] = arr
                    out[f"__{k}_meta__"] = meta
                else:
                    out[k] = _walk(v)
            return out
        elif isinstance(obj, list):
            arr, meta = _compact_list(obj, MAX_ARRAY_ITEMS, MAX_SNIPPET_CHARS)
            if meta.get("truncated"):
                compact_meta["applied"] = True
                compact_meta["notes"].append(f"list truncated: {meta}")
            return arr
        else:
            return obj

    if isinstance(detail, dict):
        e["detail"] = _walk(detail)

    # 3) message 문자열도 상한
    if isinstance(e.get("message"), (str, bytes)):
        t, trunc = _shorten_text(e["message"], MAX_EVENT_TEXT_CHARS)
        e["message"] = t
        if trunc:
            compact_meta["applied"] = True
            compact_meta["notes"].append("message truncated")

    # 4) 메타 부착
    if compact_meta["applied"]:
        e.setdefault("__compact__", compact_meta)

    return e
