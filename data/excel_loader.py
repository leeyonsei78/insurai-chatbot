"""
보험다모아 엑셀 파일 파서 및 캐시 로더
지원 파일: *.xls (Excel 97-2003, 보험다모아 공시자료)
"""

from __future__ import annotations
import os
import re
import json

# 엑셀 파일이 있는 디렉터리 (프로젝트 루트)
EXCEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "insmarket_excel_cache.json")

# 로드된 데이터 (프로세스 내 캐시)
_LOADED: list[dict] | None = None


def _detect_insurance_type(fname: str) -> str:
    fn = fname.lower()
    if "실손" in fname:
        return "실손의료보험"
    if "간병" in fname or "치매" in fname:
        return "간병·치매보험"
    if "치아" in fname:
        return "치아보험"
    if "종신" in fname:
        return "종신보험"
    if "질병" in fname:
        return "질병보험"
    if "상해" in fname:
        return "상해보험"
    if "저축" in fname or "금리" in fname:
        return "저축보험"
    return "기타"


def _parse_premium(raw: str) -> int | None:
    s = re.sub(r"[,\n\r\s원]", "", raw)
    try:
        v = float(s)
        return int(v) if v > 0 else None
    except Exception:
        return None


def _extract_context_from_filename(fname: str) -> dict:
    """파일명에서 성별/연령대 추출"""
    ctx = {}
    if "남자" in fname or "남성" in fname or "_남" in fname:
        ctx["gender"] = "남"
    elif "여자" in fname or "여성" in fname or "_여" in fname:
        ctx["gender"] = "여"
    m = re.search(r"(\d{2})대", fname)
    if m:
        ctx["age_group"] = m.group(1) + "대"
    return ctx


def _parse_file(filepath: str) -> list[dict]:
    try:
        import xlrd
        wb = xlrd.open_workbook(filepath)
        ws = wb.sheet_by_index(0)
    except Exception:
        return []

    fname = os.path.basename(filepath)
    ins_type = _detect_insurance_type(fname)
    file_ctx = _extract_context_from_filename(fname)

    # ── 헤더 행 찾기 ────────────────────────────────────────
    header_row = None
    for r in range(min(15, ws.nrows)):
        row_vals = [str(ws.cell_value(r, c)) for c in range(ws.ncols)]
        if "번호" in row_vals[0] or any("회사명" in v for v in row_vals):
            header_row = r
            break
    if header_row is None:
        return []

    headers = [str(ws.cell_value(header_row, c)).strip() for c in range(ws.ncols)]

    # 실손보험 포맷 감지: 보험료가 남/여 두 열로 분리
    is_silson = "남" in headers or any(
        str(ws.cell_value(header_row + 1, c)).strip() in ("남", "여")
        for c in range(ws.ncols)
    )
    # 실손은 헤더가 2행인 경우 있음
    if is_silson and header_row + 1 < ws.nrows:
        sub = [str(ws.cell_value(header_row + 1, c)).strip() for c in range(ws.ncols)]
        if any(v in ("남", "여") for v in sub):
            data_start = header_row + 2
        else:
            data_start = header_row + 1
    else:
        data_start = header_row + 1

    products: list[dict] = []
    current: dict | None = None

    for r in range(data_start, ws.nrows):
        row = [str(ws.cell_value(r, c)).strip() for c in range(ws.ncols)]
        if not any(row):
            continue

        번호_raw = row[0]
        is_new = bool(번호_raw) and 번호_raw not in ("0", "0.0", "")

        if is_new:
            if current:
                products.append(current)

            company_product_raw = row[1].replace("\r\n", "\n").replace("\r", "\n")
            lines = [l.strip() for l in company_product_raw.split("\n") if l.strip()]
            company = lines[0] if lines else ""
            product_name = " ".join(lines[1:]) if len(lines) > 1 else ""

            if is_silson:
                prem_m = _parse_premium(row[2]) if len(row) > 2 else None
                prem_f = _parse_premium(row[3]) if len(row) > 3 else None
                age_range = row[4].strip() if len(row) > 4 else ""
                notes = row[5].strip() if len(row) > 5 else ""
                current = {
                    "insurance_type": ins_type,
                    "source_file": fname,
                    "file_context": file_ctx,
                    "company": company,
                    "product_name": product_name,
                    "premium_male": prem_m,
                    "premium_female": prem_f,
                    "premium_monthly": None,
                    "age_range": age_range,
                    "notes": notes,
                    "coverages": [],
                }
            else:
                coverage_name = row[2] if len(row) > 2 else ""
                coverage_amount = row[3] if len(row) > 3 else ""
                premium_raw = row[4] if len(row) > 4 else ""
                age_range = row[5] if len(row) > 5 else ""
                notes = row[6] if len(row) > 6 else ""
                current = {
                    "insurance_type": ins_type,
                    "source_file": fname,
                    "file_context": file_ctx,
                    "company": company,
                    "product_name": product_name,
                    "premium_monthly": _parse_premium(premium_raw),
                    "premium_male": None,
                    "premium_female": None,
                    "age_range": age_range,
                    "notes": notes,
                    "coverages": [(coverage_name, coverage_amount)] if coverage_name else [],
                }
        elif current and len(row) > 2 and row[2]:
            cov_name = row[2]
            cov_amt = row[3] if len(row) > 3 else ""
            if cov_name:
                current["coverages"].append((cov_name, cov_amt))

    if current:
        products.append(current)

    return products


def load_all_excel(force_reload: bool = False) -> list[dict]:
    global _LOADED
    if _LOADED is not None and not force_reload:
        return _LOADED

    # JSON 캐시 확인
    if not force_reload and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                _LOADED = json.load(f)
            return _LOADED
        except Exception:
            pass

    # 엑셀 파일 파싱
    all_products: list[dict] = []
    for fname in sorted(os.listdir(EXCEL_DIR)):
        if not fname.endswith(".xls"):
            continue
        fpath = os.path.join(EXCEL_DIR, fname)
        products = _parse_file(fpath)
        all_products.extend(products)

    # JSON 캐시 저장
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(all_products, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    _LOADED = all_products
    return _LOADED
