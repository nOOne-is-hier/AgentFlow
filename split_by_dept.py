#!/usr/bin/env python3
"""
원본 통합 XLSX에서 '부서명'(D열) 기준으로 행을 분할하여
각 부서별 파일 {{부서명}}.xlsx로 내보내는 스크립트.

사용 예시:
    python split_by_dept.py \
        --input "./storage/2025년도 제3회 일반 및 기타특별회계 추가경정예산서(세출-검색용).xlsx"
        --outdir "./storage/splits"

요구 라이브러리:
    pandas, openpyxl

동작 요약:
 1) 모든 시트를 읽어 그대로(타입 변환 최소화) 세로 병합
 2) '부서명' 열로 그룹핑(없으면 D열(0-index 3) 사용 시도)
 3) 각 그룹을 그대로 새 통합문서로 저장 (시트명: '데이터')
 4) 파일명은 부서명 기준으로 생성하며, 파일명에 부적절한 문자는 '_'로 치환
"""

import argparse
import os
import re
from pathlib import Path
import pandas as pd


def sanitize_filename(name: str) -> str:
    """부서명을 안전한 파일명으로 치환 (한글/영문/숫자/._- 유지)."""
    if name is None:
        name = "미지정"
    name = str(name).strip()
    if not name:
        name = "미지정"
    # 제어문자/슬래시 등 제거
    safe = re.sub(r"[^0-9A-Za-z가-힣_.\-]+", "_", name)
    # 너무 긴 경우 절단(윈도 경로 제한 고려)
    return safe[:150]


def infer_dept_column(df: pd.DataFrame, prefer_name: str = "부서명") -> str:
    """우선 '부서명'이라는 헤더를 찾고, 없으면 4번째 컬럼(D열)을 반환."""
    cols = [str(c).strip() for c in df.columns]
    if prefer_name in cols:
        return prefer_name
    # D열(0-index 3) 시도
    if len(cols) >= 4:
        return cols[3]
    raise KeyError("'부서명' 열을 찾지 못했고, D열 대체도 불가합니다.")


def read_all_sheets(path: Path) -> pd.DataFrame:
    """모든 시트를 읽어 세로 병합. 값은 object로 유지해 원본에 가깝게."""
    xls = pd.ExcelFile(path)
    frames = []
    for sh in xls.sheet_names:
        # dtype=object로 원본 타입 보존 최대화
        df = xls.parse(sh, dtype=object)
        frames.append(df)
    if not frames:
        raise ValueError("빈 통합문서입니다.")
    # 컬럼명 공백 정리(좌우)
    frames = [f.rename(columns=lambda c: str(c).strip()) for f in frames]
    merged = pd.concat(frames, ignore_index=True)
    return merged


def split_by_dept(input_path: Path, outdir: Path, sheet_name: str | None = None) -> list[Path]:
    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일이 존재하지 않습니다: {input_path}")

    outdir = outdir / input_path.stem
    outdir.mkdir(parents=True, exist_ok=True)

    if sheet_name:
        df = pd.read_excel(input_path, sheet_name=sheet_name, dtype=object)
        df = df.rename(columns=lambda c: str(c).strip())
    else:
        df = read_all_sheets(input_path)

    dept_col = infer_dept_column(df, "부서명")

    # 그룹핑을 위해 결측 부서명을 '미지정'으로 대체하되, 데이터 값은 그대로 보존
    gb = df.copy()
    gb[dept_col] = gb[dept_col].astype(object)
    gb[dept_col] = gb[dept_col].where(gb[dept_col].notna() & (gb[dept_col].astype(str).str.strip() != ""), "미지정")

    written: list[Path] = []
    for dept, g in gb.groupby(dept_col, dropna=False):
        fname = sanitize_filename(dept) + ".xlsx"
        fpath = outdir / fname
        with pd.ExcelWriter(fpath, engine="openpyxl") as w:
            # 원본 행을 그대로 적재(정렬/형변환/필터 제거 없음)
            g.to_excel(w, index=False, sheet_name="데이터")
        written.append(fpath)
    return written


def main():
    parser = argparse.ArgumentParser(description="'부서명' 기준 XLSX 분할 스크립트")
    parser.add_argument("--input", required=True, help="원본 통합 XLSX 경로")
    parser.add_argument("--outdir", default="./splits", help="출력 폴더 (기본: ./splits/<원본파일명>/)")
    parser.add_argument("--sheet", default=None, help="특정 시트만 분할하고 싶을 때 시트명 지정 (기본: 모든 시트 병합)")
    args = parser.parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)

    files = split_by_dept(input_path, outdir, sheet_name=args.sheet)
    print(f"[OK] 분할 완료: {len(files)}개 파일 생성")
    for p in files[:10]:
        print(" -", p)
    if len(files) > 10:
        print(f" ... 외 {len(files)-10}개")


if __name__ == "__main__":
    main()
