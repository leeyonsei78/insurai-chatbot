"""
보험다모아 엑셀 → 지식베이스(knowledge.py) 자동 생성 스크립트

사용법:
  python scripts/build_knowledge_from_excel.py          # 미리보기 (파일 수정 안 함)
  python scripts/build_knowledge_from_excel.py --apply  # knowledge.py 실제 반영
  python scripts/build_knowledge_from_excel.py --rebuild # 반영 후 ChromaDB 재구축
"""

from __future__ import annotations
import sys, os, argparse, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from data.excel_loader import load_all_excel

# ── 지식 항목 생성기 ─────────────────────────────────────────────────────────

def _fmt_premium(p: dict, gender: str = None) -> str:
    if p.get("premium_monthly"):
        return f"{p['premium_monthly']:,}원/월"
    parts = []
    if p.get("premium_male"):
        parts.append(f"남 {p['premium_male']:,}원")
    if p.get("premium_female"):
        parts.append(f"여 {p['premium_female']:,}원")
    return (" / ".join(parts) + "/월") if parts else "정보 없음"


def _build_knowledge_by_type(ins_type: str, products: list[dict]) -> dict | None:
    """보험 유형별 지식 항목 생성"""
    if not products:
        return None

    # 보험사별 대표 상품 집계
    company_map: dict[str, list[dict]] = {}
    for p in products:
        co = p["company"]
        company_map.setdefault(co, []).append(p)

    # 보험료 오름차순 정렬된 대표 상품 목록 작성
    rows = []
    for co, prods in sorted(
        company_map.items(),
        key=lambda kv: min(
            (p.get("premium_monthly") or p.get("premium_male") or p.get("premium_female") or 999999)
            for p in kv[1]
        ),
    ):
        rep = min(
            prods,
            key=lambda p: (p.get("premium_monthly") or p.get("premium_male") or p.get("premium_female") or 999999),
        )
        prem = _fmt_premium(rep)
        age = rep.get("age_range", "")
        pname = rep["product_name"][:35]
        # 대표 보장 상위 2개
        covs = [c[0][:20] for c in rep.get("coverages", [])[:2] if c[0]]
        cov_str = ", ".join(covs) if covs else ""
        ctx = rep.get("file_context", {})
        ctx_str = f"{ctx.get('age_group','')} {ctx.get('gender',''+'성')}".strip()
        rows.append(f"- **{co}** {pname} | {prem} | 가입 {age} | {cov_str}")

    file_contexts = sorted({
        f"{p.get('file_context',{}).get('age_group','')} {p.get('file_context',{}).get('gender','')}".strip()
        for p in products if p.get("file_context")
    })
    ctx_note = ("기준 조건: " + ", ".join(c for c in file_contexts if c)) if file_contexts else ""

    content = f"""
{ins_type} 보험사별 상품 및 보험료 비교 (보험다모아 공시 기준, 2026년 6월)

{ctx_note}

## 주요 보험사별 상품 목록 (보험료 오름차순)

{chr(10).join(rows)}

## 참고 사항
- 위 보험료는 보험다모아 공시 자료 기준이며, 실제 가입 조건(건강상태·직업·특약 구성)에 따라 달라질 수 있습니다.
- 비교 시 보장 내용, 갱신 여부, 납입 기간을 함께 확인하세요.
- 정확한 견적은 각 보험사 다이렉트 사이트 또는 설계사를 통해 확인하시기 바랍니다.
    """.strip()

    type_id_map = {
        "실손의료보험": "insmarket_silson",
        "간병·치매보험": "insmarket_caregiving",
        "치아보험": "insmarket_dental",
        "종신보험": "insmarket_whole_life",
        "질병보험": "insmarket_disease",
        "상해보험": "insmarket_accident",
        "저축보험": "insmarket_savings",
    }

    kb_id = "kb_excel_" + type_id_map.get(ins_type, ins_type.replace("·", "_"))
    companies = list(company_map.keys())
    tags = [ins_type] + companies[:8]
    keywords_raw = [ins_type, "보험료", "보험다모아", "공시"] + companies[:6]

    return {
        "id": kb_id,
        "title": f"{ins_type} 보험사별 비교 (보험다모아 공시 2026.06)",
        "category": ins_type,
        "content": content,
        "tags": tags,
        "keywords": keywords_raw,
        "auto_generated": True,
        "source": "보험다모아 엑셀 공시자료",
    }


def generate_all_knowledge() -> list[dict]:
    products = load_all_excel()
    # 유형별 그룹핑
    type_groups: dict[str, list[dict]] = {}
    for p in products:
        t = p.get("insurance_type", "기타")
        type_groups.setdefault(t, []).append(p)

    result = []
    for ins_type, prods in type_groups.items():
        kb = _build_knowledge_by_type(ins_type, prods)
        if kb:
            result.append(kb)
    return result


# ── knowledge.py 반영 ─────────────────────────────────────────────────────────

def _escape_for_py_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def update_knowledge_py(new_items: list[dict]) -> None:
    knowledge_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "knowledge.py",
    )

    with open(knowledge_path, encoding="utf-8") as f:
        src = f.read()

    # 기존 auto_generated 항목 제거
    src = re.sub(
        r'\n\s*#\s*AUTO-GENERATED START.*?#\s*AUTO-GENERATED END\n',
        '\n',  # leading \n 유지 — 제거 시 ] 앞 개행이 사라져 regex 탐지 실패
        src,
        flags=re.DOTALL,
    )

    # KNOWLEDGE_BASE 리스트 닫는 ] 찾기 — 줄 시작 ']' (뒤 공백/줄바꿈 유연하게 허용)
    m = re.search(r'\n(\]\s*\n)', src)
    if not m:
        print("[오류] KNOWLEDGE_BASE 리스트 닫는 ] 를 찾을 수 없습니다.")
        return
    insert_pos = m.start() + 1  # '\n' 다음, ']' 바로 앞

    blocks = ["    # AUTO-GENERATED START — 보험다모아 엑셀 자동 생성 (수동 편집 금지)"]
    for item in new_items:
        tags_py = repr(item["tags"])
        kw_py = repr(item["keywords"])
        content_escaped = item["content"].replace("\\", "\\\\")
        block = f"""
    {{
        "id": {repr(item['id'])},
        "title": {repr(item['title'])},
        "category": {repr(item['category'])},
        "content": \"\"\"{content_escaped}\"\"\",
        "tags": {tags_py},
        "keywords": {kw_py},
        "auto_generated": True,
        "source": {repr(item.get('source', ''))},
    }},"""
        blocks.append(block)
    blocks.append("    # AUTO-GENERATED END")

    inserted = "\n".join(blocks) + "\n"
    new_src = src[:insert_pos] + inserted + src[insert_pos:]

    with open(knowledge_path, "w", encoding="utf-8") as f:
        f.write(new_src)

    print(f"[완료] knowledge.py 업데이트 — {len(new_items)}개 항목 추가")


# ── ChromaDB 재구축 ───────────────────────────────────────────────────────────

def rebuild_chroma():
    try:
        from data.knowledge import get_all_knowledge
        from rag.vectorstore import InsuranceVectorStore
        docs = get_all_knowledge()
        vs = InsuranceVectorStore.get_instance()
        vs.reset()
        count = vs.add_documents(docs)
        print(f"[완료] ChromaDB 재구축 완료 — {count}개 문서")
    except Exception as e:
        print(f"[오류] ChromaDB 재구축 실패: {e}")
        print("  → 웹에서 /rebuild 명령으로 직접 재구축하거나")
        print("    python scripts/build_vectorstore.py 를 실행하세요.")


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="보험다모아 엑셀 → 지식베이스 자동 생성")
    parser.add_argument("--apply", action="store_true", help="knowledge.py 실제 수정")
    parser.add_argument("--rebuild", action="store_true", help="수정 후 ChromaDB 재구축")
    args = parser.parse_args()

    print("엑셀 파일 파싱 중...")
    items = generate_all_knowledge()
    print(f"생성된 지식 항목: {len(items)}개\n")

    for item in items:
        print(f"  [{item['id']}] {item['title']}")
        lines = item['content'].split('\n')
        for line in lines[3:8]:
            if line.strip():
                print(f"    {line.strip()[:70]}")
        print()

    if args.apply or args.rebuild:
        update_knowledge_py(items)
        if args.rebuild:
            print("\nChromaDB 재구축 중...")
            rebuild_chroma()
    else:
        print("=" * 60)
        print("미리보기 모드입니다. 실제 반영하려면:")
        print("  python scripts/build_knowledge_from_excel.py --apply")
        print("ChromaDB까지 재구축하려면:")
        print("  python scripts/build_knowledge_from_excel.py --rebuild")


if __name__ == "__main__":
    main()
