"""
보험 상담 챗봇 웹 인터페이스
- API 크레딧 있을 때: Claude 오케스트레이터 사용 (Live Mode)
- 크레딧 없을 때: 로컬 도구 + 스마트 응답 (Mock Mode)

실행: python web_app.py
접속: http://localhost:5000
"""

import sys
import os
import re
import json
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, render_template_string, Response, stream_with_context

app = Flask(__name__)

# ── 세션 저장소 ───────────────────────────────────────────
sessions = {}  # session_id -> {chatbot, context, mode}


# ── Mock 컨텍스트 ──────────────────────────────────────────
class MockContext:
    def __init__(self):
        self.age = None
        self.gender = "남"
        self.budget = None
        self.last_products = []
        self.last_type = None


def extract_info(text, ctx):
    m = re.search(r'(\d{2,3})\s*세', text)
    if m:
        ctx.age = int(m.group(1))
    else:
        m = re.search(r'(\d+)0\s*대', text)
        if m:
            ctx.age = int(m.group(1)) * 10 + 5

    if any(k in text for k in ['남성', '남자', '남 ', '아빠', '아버지']):
        ctx.gender = '남'
    elif any(k in text for k in ['여성', '여자', '여 ', '엄마', '어머니']):
        ctx.gender = '여'

    m = re.search(r'(\d+)\s*만\s*원', text)
    if m:
        ctx.budget = int(m.group(1)) * 10000


def detect_intent(text, ctx):
    if '비교' in text and ctx.last_products:
        return 'compare'
    if any(k in text for k in ['암보험', '암 보험', '암진단', '면역항암', '항암']):
        return 'cancer'
    if any(k in text for k in ['블록체인', 'blockchain']) and any(k in text for k in ['덴탈', '치과', '임플란트', '치아', '보험']):
        return 'dental_blockchain'
    if any(k in text for k in ['덴탈', '치과', '임플란트', '스케일링', '충치', '잇몸', '치아']):
        return 'dental'
    if any(k in text for k in ['실손', '실비', '의료비', '병원비', '의료보험']):
        return 'health'
    if any(k in text for k in ['생명보험', '종신보험', '정기보험', '사망보험', '사망보장']):
        return 'life'
    if any(k in text for k in ['추천', '포트폴리오', '어떤 보험', '뭐가 좋', '어디가 좋']):
        return 'recommend'
    if any(k in text for k in ['보험료', '얼마', '가격', '월납']):
        return 'premium'
    if any(k in text for k in ['안녕', '처음', '시작']):
        return 'greeting'
    return 'knowledge'


def mock_response(message, ctx):
    from tools.product_tools import search_products, compare_products, get_premium_estimate
    from tools.rag_tools import retrieve_insurance_knowledge

    extract_info(message, ctx)
    intent = detect_intent(message, ctx)
    age = ctx.age or 40
    gender = ctx.gender or '남'

    # ── 인사 ──────────────────────────────────────────────
    if intent == 'greeting':
        return (
            "안녕하세요! **보험 상담 AI 어시스턴트**입니다.\n\n"
            "생명보험, 실손의료보험, 암보험, 덴탈(치과)보험 상담을 도와드립니다.\n\n"
            "나이, 성별, 예산을 알려주시면 더 정확한 추천이 가능해요!\n\n"
            "> 예시: *\"45세 남성, 월 20만원 예산으로 암보험 추천해줘\"*"
        )

    # ── 암보험 ────────────────────────────────────────────
    elif intent == 'cancer':
        raw = json.loads(search_products(insurance_type='실손의료보험', subtype='암보험', age=age))
        results = raw.get('results', [])
        ctx.last_products = [r['id'] for r in results[:3]]
        ctx.last_type = '암보험'

        lines = [f"## 암보험 추천 ({age}세 {gender}성 기준)\n"]
        for i, p in enumerate(results[:3], 1):
            try:
                pr = json.loads(get_premium_estimate(p['id'], age, gender))
                pstr = pr.get('premium_formatted', f"{p['monthly_premium_reference']:,}원/월")
            except Exception:
                pstr = f"{p['monthly_premium_reference']:,}원/월"

            lines += [
                f"### {i}. {p['name']}",
                f"| 항목 | 내용 |",
                f"|------|------|",
                f"| 회사 | {p['company']} |",
                f"| 월 보험료 | **{pstr}** |",
                f"| 주요 보장 | {', '.join(p.get('key_coverage', [])[:3])} |",
                f"| 특징 | {p.get('key_features', ['-'])[0]} |",
                f"| 장점 | {p.get('pros', ['-'])[0]} |",
                "",
            ]
        lines.append("> 💡 **체크포인트**: 면책기간 90일 / 비갱신형은 보험료 고정 / 진단금 2,000만원 이상 권장")
        lines.append("\n\"두 상품 비교해줘\" 또는 특정 상품 보험료 문의도 가능합니다!")
        return '\n'.join(lines)

    # ── 블록체인 덴탈보험 ─────────────────────────────────
    elif intent == 'dental_blockchain':
        raw = json.loads(search_products(insurance_type='덴탈보험', needs=['블록체인'], age=age))
        results = raw.get('results', [])
        # 라이나생명(dental_005) 1순위 보장
        lina = [r for r in results if r['id'] == 'dental_005']
        others = [r for r in results if r['id'] != 'dental_005']
        results = lina + others
        if not lina:
            # 전체 검색에서라도 가져오기
            all_raw = json.loads(search_products(insurance_type='덴탈보험'))
            all_results = all_raw.get('results', [])
            lina = [r for r in all_results if r['id'] == 'dental_005']
            results = lina + [r for r in results if r['id'] != 'dental_005']
        ctx.last_products = [r['id'] for r in results[:3]]
        ctx.last_type = '덴탈보험'

        lines = [
            f"## 블록체인 덴탈(치과)보험 추천 ({age}세 {gender}성 기준)\n",
            "> 블록체인 기반 보험은 **라이나생명 블록체인치아보험 스마트**를 강력 추천드립니다!\n",
        ]
        for i, p in enumerate(results[:3], 1):
            try:
                pr = json.loads(get_premium_estimate(p['id'], age, gender))
                pstr = pr.get('premium_formatted', f"{p['monthly_premium_reference']:,}원/월")
            except Exception:
                pstr = f"{p['monthly_premium_reference']:,}원/월"

            badge = " ⭐ **블록체인 추천**" if p['id'] == 'dental_005' else ""
            lines += [
                f"### {i}. {p['name']}{badge}",
                f"| 항목 | 내용 |",
                f"|------|------|",
                f"| 회사 | {p['company']} |",
                f"| 월 보험료 | **{pstr}** |",
                f"| 주요 보장 | {', '.join(p.get('key_coverage', [])[:3])} |",
                f"| 특징 | {p.get('key_features', ['-'])[0]} |",
                "",
            ]
        lines.append("> 💡 **블록체인 장점**: 스마트 계약 자동 청구 / 서류 불필요 / 보험금 이력 투명 공개")
        lines.append("> ⚠️ **필수 확인**: 임플란트 대기기간 **180일** — 가입 즉시 보장 안 됩니다!")
        return '\n'.join(lines)

    # ── 덴탈보험 ──────────────────────────────────────────
    elif intent == 'dental':
        needs = []
        if '임플란트' in message:
            needs.append('임플란트')
        raw = json.loads(search_products(insurance_type='덴탈보험', needs=needs or None, age=age))
        results = raw.get('results', [])
        ctx.last_products = [r['id'] for r in results[:3]]
        ctx.last_type = '덴탈보험'

        lines = [f"## 덴탈(치과)보험 추천 ({age}세 {gender}성 기준)\n"]
        for i, p in enumerate(results[:3], 1):
            try:
                pr = json.loads(get_premium_estimate(p['id'], age, gender))
                pstr = pr.get('premium_formatted', f"{p['monthly_premium_reference']:,}원/월")
            except Exception:
                pstr = f"{p['monthly_premium_reference']:,}원/월"

            lines += [
                f"### {i}. {p['name']}",
                f"| 항목 | 내용 |",
                f"|------|------|",
                f"| 회사 | {p['company']} |",
                f"| 월 보험료 | **{pstr}** |",
                f"| 주요 보장 | {', '.join(p.get('key_coverage', [])[:3])} |",
                f"| 특징 | {p.get('key_features', ['-'])[0]} |",
                "",
            ]
        lines.append("> 💡 **필수 확인**: 임플란트 대기기간 **180일** / 충치치료 **90일** — 가입 즉시 보장 안 됩니다!")
        return '\n'.join(lines)

    # ── 실손보험 ──────────────────────────────────────────
    elif intent == 'health':
        raw = json.loads(search_products(insurance_type='실손의료보험', age=age))
        results = [r for r in raw.get('results', []) if r.get('subtype') != '암보험'][:3]
        ctx.last_products = [r['id'] for r in results]
        ctx.last_type = '실손의료보험'

        lines = [f"## 실손의료보험 추천 ({age}세 {gender}성 기준)\n"]
        for i, p in enumerate(results, 1):
            try:
                pr = json.loads(get_premium_estimate(p['id'], age, gender))
                pstr = pr.get('premium_formatted', f"{p['monthly_premium_reference']:,}원/월")
            except Exception:
                pstr = f"{p['monthly_premium_reference']:,}원/월"

            lines += [
                f"### {i}. {p['name']}",
                f"| 항목 | 내용 |",
                f"|------|------|",
                f"| 회사 | {p['company']} |",
                f"| 유형 | {p.get('subtype', '-')} |",
                f"| 월 보험료 | **{pstr}** |",
                f"| 장점 | {p.get('pros', ['-'])[0]} |",
                f"| 단점 | {p.get('cons', ['-'])[0]} |",
                "",
            ]
        lines.append("> 💡 신규 가입은 **4세대 실손**만 가능합니다. 비급여 본인부담 30% 적용.")
        return '\n'.join(lines)

    # ── 생명보험 ──────────────────────────────────────────
    elif intent == 'life':
        raw = json.loads(search_products(insurance_type='생명보험', age=age))
        results = raw.get('results', [])[:3]
        ctx.last_products = [r['id'] for r in results]
        ctx.last_type = '생명보험'

        lines = [f"## 생명보험 추천 ({age}세 {gender}성 기준)\n"]
        for i, p in enumerate(results, 1):
            try:
                pr = json.loads(get_premium_estimate(p['id'], age, gender))
                pstr = pr.get('premium_formatted', f"{p['monthly_premium_reference']:,}원/월")
            except Exception:
                pstr = f"{p['monthly_premium_reference']:,}원/월"

            cov_amount = p.get('coverage_amount', 0)
            lines += [
                f"### {i}. {p['name']}",
                f"| 항목 | 내용 |",
                f"|------|------|",
                f"| 회사 | {p['company']} |",
                f"| 유형 | {p.get('subtype', '-')} |",
                f"| 보장금액 | {cov_amount // 10000:,}만원 |" if cov_amount else f"| 특징 | {p.get('key_features', ['-'])[0]} |",
                f"| 월 보험료 | **{pstr}** |",
                f"| 장점 | {p.get('pros', ['-'])[0]} |",
                "",
            ]
        lines.append("> 💡 부양가족 있다면 **종신보험** / 일정 기간만 보장 원하면 **정기보험**이 유리합니다.")
        return '\n'.join(lines)

    # ── 비교 ──────────────────────────────────────────────
    elif intent == 'compare' and ctx.last_products:
        ids = ctx.last_products[:2]
        raw = json.loads(compare_products(ids))
        products = raw.get('products', [])
        if len(products) < 2:
            return "비교할 상품이 부족합니다. 먼저 상품을 검색해 주세요."

        p0, p1 = products[0], products[1]
        pm0 = p0.get('monthly_premiums', {})
        pm1 = p1.get('monthly_premiums', {})
        v0 = next((v for k, v in pm0.items() if gender in k), next(iter(pm0.values()), 0))
        v1 = next((v for k, v in pm1.items() if gender in k), next(iter(pm1.values()), 0))

        lines = [f"## {p0['name']} vs {p1['name']}\n"]
        lines += [
            f"| 구분 | {p0['company']} | {p1['company']} |",
            f"|------|------|------|",
            f"| 월 보험료 | **{v0:,}원** | **{v1:,}원** |",
        ]

        cov0 = p0.get('coverage', {})
        cov1 = p1.get('coverage', {})
        all_keys = list(dict.fromkeys(list(cov0.keys())[:3] + list(cov1.keys())[:3]))
        for ck in all_keys[:4]:
            c0 = str(cov0.get(ck, '-'))[:25]
            c1 = str(cov1.get(ck, '-'))[:25]
            lines.append(f"| {ck} | {c0} | {c1} |")

        pros0 = ', '.join(p0.get('pros', ['-'])[:2])
        pros1 = ', '.join(p1.get('pros', ['-'])[:2])
        lines.append(f"| 장점 | {pros0} | {pros1} |")
        cons0 = p0.get('cons', ['-'])[0]
        cons1 = p1.get('cons', ['-'])[0]
        lines.append(f"| 단점 | {cons0} | {cons1} |")
        lines.append("")

        cheaper = p0['name'] if v0 <= v1 else p1['name']
        lines.append(f"**결론**: 보험료 절약 → **{cheaper}** / 보장 범위는 세부 특약 비교 후 결정 권장")
        return '\n'.join(lines)

    # ── 포트폴리오 추천 ────────────────────────────────────
    elif intent == 'recommend':
        budget_str = f"월 {ctx.budget // 10000:,}만원" if ctx.budget else "예산 미정"
        lines = [f"## {age}세 {gender}성 맞춤 보험 포트폴리오\n",
                 f"**기준**: {age}세 / {gender}성 / {budget_str}\n"]

        cats = [
            ('실손의료보험', None),
            ('실손의료보험', '암보험'),
            ('덴탈보험', None),
        ]
        total = 0
        for i, (ins_type, subtype) in enumerate(cats, 1):
            kwargs = {'insurance_type': ins_type, 'age': age}
            if subtype:
                kwargs['subtype'] = subtype
            raw = json.loads(search_products(**kwargs))
            results = raw.get('results', [])
            if not results:
                continue
            p = results[0]
            label = subtype or ins_type
            try:
                pr = json.loads(get_premium_estimate(p['id'], age, gender))
                prem = pr.get('estimated_monthly_premium', p['monthly_premium_reference'])
                pstr = pr.get('premium_formatted', f"{prem:,}원/월")
            except Exception:
                prem = p['monthly_premium_reference']
                pstr = f"{prem:,}원/월"
            total += prem
            lines += [
                f"### {i}순위 · {label}",
                f"**{p['name']}** ({p['company']})",
                f"- 월 보험료: **{pstr}**",
                f"- 주요 보장: {', '.join(p.get('key_coverage', [])[:3])}",
                f"- 추천 이유: {p.get('pros', ['기본 보장 충실'])[0]}",
                "",
            ]

        lines += [
            "---",
            f"**예상 총 월 보험료: {total:,}원**\n",
            "> 실제 보험료는 건강상태, 직업, 특약 구성에 따라 달라질 수 있습니다.",
        ]
        return '\n'.join(lines)

    # ── 보험료 조회 ────────────────────────────────────────
    elif intent == 'premium':
        if not ctx.last_products:
            return "어떤 상품의 보험료를 알고 싶으신가요?\n먼저 상품을 검색해 주세요.\n예) *\"실손보험 추천해줘\"*"

        lines = [f"## 보험료 조회 ({age}세 / {gender}성)\n"]
        for pid in ctx.last_products[:3]:
            try:
                pr = json.loads(get_premium_estimate(pid, age, gender))
                lines += [
                    f"**{pr['product_name']}** ({pr['company']})",
                    f"- 월 보험료: **{pr['premium_formatted']}**",
                    f"- 연간 보험료: {pr['annual_premium']}",
                    f"- 참고: {pr.get('note', '')}",
                    "",
                ]
            except Exception:
                pass
        return '\n'.join(lines)

    # ── 지식 검색 (RAG) ────────────────────────────────────
    else:
        raw = json.loads(retrieve_insurance_knowledge(message, top_k=2))
        results = raw.get('results', [])
        if not results:
            return (
                "죄송합니다, 관련 정보를 찾지 못했습니다.\n\n"
                "다음과 같이 질문해 보세요:\n"
                "- \"암보험 추천해줘\"\n"
                "- \"임플란트 치과보험 대기기간\"\n"
                "- \"실손보험 3세대 4세대 차이\"\n"
                "- \"40대 남성 보험 포트폴리오 추천\""
            )

        lines = []
        for r in results:
            lines.append(f"## {r['title']}\n")
            content = r['content']
            if len(content) > 700:
                content = content[:700] + "..."
            lines.append(content)
            lines.append("")
        score = results[0].get('relevance_score')
        if score:
            lines.append(f"\n*관련도: {score:.0%}*")
        return '\n'.join(lines)


# ── HTML 템플릿 ───────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>보험 상담 AI</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #f0f4f8; height: 100vh; display: flex; flex-direction: column; }

  /* Header */
  .header {
    background: linear-gradient(135deg, #1d4ed8, #2563eb);
    color: white;
    padding: 14px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  }
  .header-icon { font-size: 28px; }
  .header-title { font-size: 18px; font-weight: 700; }
  .header-sub { font-size: 12px; opacity: 0.85; margin-top: 2px; }
  .mode-selector {
    margin-left: auto;
    position: relative;
  }
  .mode-badge {
    background: rgba(255,255,255,0.2);
    border: 1px solid rgba(255,255,255,0.4);
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }
  .mode-badge:hover { background: rgba(255,255,255,0.3); }
  .mode-badge.live { background: rgba(34,197,94,0.3); border-color: rgba(34,197,94,0.6); }
  .mode-badge.mock { background: rgba(251,191,36,0.3); border-color: rgba(251,191,36,0.6); }
  .mode-dropdown {
    display: none;
    position: absolute;
    right: 0;
    top: calc(100% + 6px);
    background: white;
    border-radius: 10px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    overflow: hidden;
    z-index: 100;
    min-width: 150px;
  }
  .mode-dropdown.open { display: block; }
  .mode-option {
    padding: 10px 16px;
    font-size: 13px;
    color: #1e293b;
    cursor: pointer;
    white-space: nowrap;
  }
  .mode-option:hover { background: #f1f5f9; }

  /* Chat area */
  #chat {
    flex: 1;
    overflow-y: auto;
    padding: 20px 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* Message bubbles */
  .msg { display: flex; gap: 10px; max-width: 85%; }
  .msg.user { margin-left: auto; flex-direction: row-reverse; }
  .msg.bot { margin-right: auto; }

  .avatar {
    width: 36px; height: 36px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; flex-shrink: 0;
  }
  .msg.user .avatar { background: #2563eb; color: white; }
  .msg.bot .avatar { background: #e2e8f0; }

  .bubble {
    padding: 12px 16px;
    border-radius: 16px;
    line-height: 1.6;
    font-size: 14px;
    max-width: 100%;
    word-break: break-word;
  }
  .msg.user .bubble {
    background: #2563eb;
    color: white;
    border-bottom-right-radius: 4px;
  }
  .msg.bot .bubble {
    background: white;
    color: #1e293b;
    border-bottom-left-radius: 4px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);
  }

  /* Markdown styles inside bot bubble */
  .bubble h2 { font-size: 15px; color: #1d4ed8; margin: 0 0 10px; padding-bottom: 6px; border-bottom: 2px solid #dbeafe; }
  .bubble h3 { font-size: 14px; color: #374151; margin: 12px 0 6px; }
  .bubble table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 13px; }
  .bubble th, .bubble td { border: 1px solid #e2e8f0; padding: 6px 10px; text-align: left; }
  .bubble th { background: #f1f5f9; font-weight: 600; }
  .bubble tr:nth-child(even) td { background: #f8fafc; }
  .bubble strong { color: #1d4ed8; }
  .bubble ul, .bubble ol { padding-left: 18px; margin: 6px 0; }
  .bubble li { margin: 3px 0; }
  .bubble blockquote { border-left: 3px solid #2563eb; padding-left: 10px; color: #64748b; margin: 8px 0; font-size: 13px; }
  .bubble em { color: #64748b; font-style: normal; }
  .bubble p { margin: 6px 0; }
  .bubble code { background: #f1f5f9; padding: 2px 5px; border-radius: 4px; font-size: 12px; }

  /* Typing indicator */
  .typing { display: flex; gap: 5px; align-items: center; padding: 12px 16px; }
  .typing span {
    width: 8px; height: 8px; background: #94a3b8;
    border-radius: 50%; animation: bounce 1.2s infinite;
  }
  .typing span:nth-child(2) { animation-delay: 0.2s; }
  .typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes bounce {
    0%, 60%, 100% { transform: translateY(0); }
    30% { transform: translateY(-6px); }
  }

  /* Quick buttons */
  .quick-buttons {
    display: flex; gap: 8px; flex-wrap: wrap; padding: 0 16px 12px;
  }
  .qbtn {
    background: white; border: 1px solid #d1d5db;
    border-radius: 20px; padding: 6px 14px;
    font-size: 12px; cursor: pointer; color: #374151;
    transition: all 0.2s;
  }
  .qbtn:hover { background: #dbeafe; border-color: #2563eb; color: #1d4ed8; }

  /* Input area */
  .input-area {
    background: white;
    padding: 12px 16px;
    border-top: 1px solid #e2e8f0;
    display: flex;
    gap: 10px;
    align-items: flex-end;
  }
  #input {
    flex: 1;
    border: 1px solid #d1d5db;
    border-radius: 24px;
    padding: 10px 16px;
    font-size: 14px;
    outline: none;
    resize: none;
    max-height: 120px;
    min-height: 42px;
    line-height: 1.5;
    font-family: inherit;
    transition: border-color 0.2s;
  }
  #input:focus { border-color: #2563eb; }
  #send {
    background: #2563eb; color: white;
    border: none; border-radius: 50%;
    width: 42px; height: 42px;
    cursor: pointer; font-size: 18px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    transition: background 0.2s;
  }
  #send:hover { background: #1d4ed8; }
  #send:disabled { background: #94a3b8; cursor: not-allowed; }

  .reset-btn {
    background: none; border: none; color: #94a3b8;
    cursor: pointer; font-size: 20px; padding: 4px;
    flex-shrink: 0;
  }
  .reset-btn:hover { color: #ef4444; }

  /* Streaming tool status */
  .tool-status {
    display: none;
    font-size: 12px;
    color: #2563eb;
    background: #dbeafe;
    border-radius: 12px;
    padding: 4px 10px;
    margin-bottom: 6px;
    width: fit-content;
    animation: pulse 1.5s infinite;
  }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.5; } }

  /* Streaming cursor blink */
  .stream-cursor {
    display: inline-block;
    width: 2px;
    height: 14px;
    background: #2563eb;
    margin-left: 2px;
    vertical-align: middle;
    animation: blink 0.8s step-end infinite;
  }
  @keyframes blink { 0%,100% { opacity:1; } 50% { opacity:0; } }

  /* ── Tab Navigation ── */
  .tab-nav {
    display: flex;
    background: #1e40af;
    padding: 0 16px;
    gap: 4px;
  }
  .tab-btn {
    padding: 10px 18px;
    font-size: 13px;
    font-weight: 600;
    color: rgba(255,255,255,0.65);
    border: none;
    background: transparent;
    cursor: pointer;
    border-bottom: 3px solid transparent;
    transition: all 0.2s;
    white-space: nowrap;
  }
  .tab-btn:hover { color: white; }
  .tab-btn.active { color: white; border-bottom-color: #60a5fa; }
  .tab-btn.demo-tab { border-bottom-color: #f59e0b; }
  .tab-btn.demo-tab.active { border-bottom-color: #f59e0b; color: #fef3c7; }
  .tab-panel { display: none; flex: 1; overflow: hidden; flex-direction: column; }
  .tab-panel.active { display: flex; }

  /* ── Demo Tab ── */
  .demo-panel {
    flex: 1; overflow-y: auto; padding: 20px; background: #0f172a;
  }
  .demo-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #0f2040 100%);
    border: 1px solid #334155; border-radius: 14px;
    padding: 22px 24px; margin-bottom: 20px; text-align: center;
  }
  .demo-title {
    font-size: 18px; font-weight: 800; color: #f8fafc; margin-bottom: 8px;
    letter-spacing: -0.3px;
  }
  .demo-subtitle {
    font-size: 12.5px; color: #94a3b8; line-height: 1.7;
  }
  .demo-subtitle strong { color: #60a5fa; }
  .demo-section-title {
    font-size: 13px; font-weight: 700; color: #f59e0b;
    padding: 10px 14px; margin-bottom: 12px;
    background: rgba(245,158,11,0.08); border-left: 3px solid #f59e0b;
    border-radius: 6px;
  }
  .demo-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
    gap: 12px; margin-bottom: 20px;
  }
  .demo-card {
    background: #1e293b; border: 1px solid #334155; border-radius: 12px;
    padding: 16px; cursor: pointer; transition: all 0.2s;
  }
  .demo-card:hover {
    border-color: #60a5fa; background: #1e3a5f;
    transform: translateY(-2px); box-shadow: 0 4px 16px rgba(96,165,250,0.15);
  }
  .demo-card-num {
    font-size: 11px; font-weight: 700; color: #f59e0b;
    margin-bottom: 6px; letter-spacing: 0.5px;
  }
  .demo-card-title {
    font-size: 14px; font-weight: 700; color: #f1f5f9; margin-bottom: 6px;
  }
  .demo-card-persona {
    font-size: 12px; color: #60a5fa; margin-bottom: 8px; font-weight: 600;
  }
  .demo-card-desc {
    font-size: 12px; color: #94a3b8; line-height: 1.6; margin-bottom: 8px;
  }
  .demo-card-data {
    font-size: 10.5px; color: #475569; background: rgba(71,85,105,0.3);
    border-radius: 6px; padding: 5px 8px; margin-bottom: 8px;
  }
  .demo-card-before-after {
    font-size: 11.5px; color: #cbd5e1; line-height: 1.6;
  }
  .before-tag {
    display: inline-block; background: #7f1d1d; color: #fca5a5;
    border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: 700;
    margin-right: 4px;
  }
  .after-tag {
    display: inline-block; background: #14532d; color: #86efac;
    border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: 700;
    margin: 0 4px;
  }
  .demo-result-title {
    font-size: 13px; font-weight: 700; color: #60a5fa;
    padding: 12px 16px; border-bottom: 1px solid #334155;
    background: #1e293b; border-radius: 10px 10px 0 0;
  }
  #demo-chat {
    background: #1e293b; border-radius: 0 0 10px 10px;
    padding: 16px; min-height: 120px;
  }
  #demo-chat .msg { margin-bottom: 14px; }
  #demo-chat .bubble {
    background: #0f172a; border: 1px solid #334155; border-radius: 10px;
    padding: 14px 16px; font-size: 13px; color: #e2e8f0; line-height: 1.7;
  }
  #demo-chat .bubble table {
    width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 12px;
  }
  #demo-chat .bubble th {
    background: #1e3a5f; color: #93c5fd; padding: 6px 10px;
    border: 1px solid #334155; text-align: left;
  }
  #demo-chat .bubble td {
    padding: 6px 10px; border: 1px solid #334155; color: #cbd5e1;
  }
  #demo-chat .bubble tr:nth-child(even) td { background: #172032; }
  #demo-chat .bubble code {
    background: #0f172a; border: 1px solid #334155;
    border-radius: 4px; padding: 1px 5px; font-size: 12px; color: #a5b4fc;
  }
  #demo-chat .bubble strong { color: #60a5fa; }
  #demo-chat .tool-indicator {
    font-size: 11px; color: #f59e0b; padding: 6px 10px;
    background: rgba(245,158,11,0.08); border-radius: 6px; margin-bottom: 6px;
  }

  /* ── Credit Portfolio Panel ── */
  .credit-panel {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    background: #f0f4f8;
  }
  .credit-guide {
    background: white;
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  }
  .credit-guide h3 { font-size: 14px; color: #1e40af; margin-bottom: 10px; }
  .score-sources {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 8px;
  }
  .score-source-card {
    flex: 1;
    min-width: 140px;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 12px 14px;
    background: #f8fafc;
    cursor: pointer;
    transition: all 0.15s;
  }
  .score-source-card:hover { border-color: #3b82f6; background: #eff6ff; }
  .score-source-card .source-logo { font-size: 22px; margin-bottom: 4px; }
  .score-source-card .source-name { font-size: 13px; font-weight: 700; color: #1e293b; }
  .score-source-card .source-desc { font-size: 11px; color: #64748b; margin-top: 3px; }
  .score-source-card .source-link {
    font-size: 11px; color: #2563eb; margin-top: 6px;
    text-decoration: none; display: inline-block;
  }
  .credit-form {
    background: white;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    margin-bottom: 16px;
  }
  .credit-form h3 { font-size: 14px; color: #1e293b; font-weight: 700; margin-bottom: 14px; }
  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  .form-group { display: flex; flex-direction: column; gap: 5px; }
  .form-group.full { grid-column: 1 / -1; }
  .form-group label { font-size: 12px; font-weight: 600; color: #475569; }
  .form-group input, .form-group select {
    padding: 9px 12px;
    border: 1.5px solid #e2e8f0;
    border-radius: 8px;
    font-size: 13px;
    outline: none;
    transition: border-color 0.15s;
    background: white;
  }
  .form-group input:focus, .form-group select:focus { border-color: #3b82f6; }
  .score-input-wrap { position: relative; }
  .score-input-wrap input { padding-right: 40px; width: 100%; }
  .score-badge {
    position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
    font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 10px;
  }
  .score-badge.tier1 { background: #dcfce7; color: #16a34a; }
  .score-badge.tier2 { background: #dbeafe; color: #1d4ed8; }
  .score-badge.tier3 { background: #fef3c7; color: #d97706; }
  .score-badge.tier4 { background: #fee2e2; color: #dc2626; }
  .score-badge.tier5 { background: #f1f5f9; color: #64748b; }
  .score-avg-note { font-size: 11px; color: #64748b; margin-top: 4px; }
  .gen-btn {
    width: 100%;
    margin-top: 16px;
    padding: 13px;
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    color: white;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    transition: opacity 0.2s;
  }
  .gen-btn:hover { opacity: 0.92; }
  .gen-btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .credit-result {
    background: white;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  }
  .credit-result-header {
    display: flex; align-items: center; gap: 10px;
    padding-bottom: 12px;
    border-bottom: 1px solid #f1f5f9;
    margin-bottom: 14px;
  }
  .credit-result-header .score-pill {
    background: #eff6ff; border: 1.5px solid #bfdbfe;
    color: #1d4ed8; font-weight: 700; font-size: 13px;
    padding: 4px 12px; border-radius: 20px;
  }
  .credit-result-body { line-height: 1.7; font-size: 13.5px; color: #1e293b; }
  .credit-result-body table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 12.5px; }
  .credit-result-body th { background: #f8fafc; padding: 7px 10px; border: 1px solid #e2e8f0; text-align: left; font-weight: 600; }
  .credit-result-body td { padding: 7px 10px; border: 1px solid #e2e8f0; }
  .credit-result-body h3 { font-size: 14px; margin: 14px 0 6px; color: #1e40af; }
  .credit-result-body h4 { font-size: 13px; margin: 10px 0 5px; color: #374151; }
  .credit-result-body ul, .credit-result-body ol { padding-left: 18px; margin: 5px 0; }
  .credit-result-body blockquote { border-left: 3px solid #3b82f6; padding-left: 12px; color: #475569; margin: 8px 0; }
  .credit-loading {
    display: flex; align-items: center; gap: 10px;
    padding: 30px; justify-content: center; color: #64748b; font-size: 14px;
  }
  .credit-loading .spin {
    width: 22px; height: 22px; border: 3px solid #e2e8f0;
    border-top-color: #3b82f6; border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .extra-section {
    border: 1.5px dashed #e2e8f0;
    border-radius: 10px;
    margin-top: 16px;
    overflow: hidden;
  }
  .extra-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 11px 14px;
    background: #f8fafc;
    cursor: pointer;
    user-select: none;
    font-size: 13px;
    font-weight: 600;
    color: #374151;
  }
  .extra-section-header:hover { background: #f1f5f9; }
  .extra-section-toggle { transition: transform 0.2s; font-size: 12px; color: #94a3b8; }
  .extra-section-toggle.open { transform: rotate(180deg); }
  .extra-section-body {
    padding: 14px;
    display: none;
    border-top: 1.5px dashed #e2e8f0;
  }
  .extra-section-body.open { display: block; }
  .financial-summary {
    background: #f0f9ff;
    border: 1px solid #bae6fd;
    border-radius: 8px;
    padding: 10px 14px;
    margin-top: 12px;
    font-size: 12px;
    color: #0c4a6e;
    display: none;
  }
  .financial-summary.visible { display: block; }
  .financial-summary-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 3px 0;
    border-bottom: 1px solid #e0f2fe;
  }
  .financial-summary-row:last-child { border-bottom: none; }
  .risk-badge {
    display: inline-block;
    padding: 1px 7px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
  }
  .risk-low  { background: #dcfce7; color: #16a34a; }
  .risk-med  { background: #fef3c7; color: #d97706; }
  .risk-high { background: #fee2e2; color: #dc2626; }
  /* 종합 적합도 점수 카드 */
  .composite-score-card {
    background: linear-gradient(135deg, #1e40af 0%, #1d4ed8 100%);
    border-radius: 12px;
    padding: 18px 20px;
    color: white;
    margin-bottom: 16px;
  }
  .composite-score-card .cs-title {
    font-size: 12px; font-weight: 600; opacity: 0.8; margin-bottom: 4px;
  }
  .composite-score-card .cs-score {
    font-size: 32px; font-weight: 800; letter-spacing: -1px;
  }
  .composite-score-card .cs-grade {
    display: inline-block; background: rgba(255,255,255,0.2);
    border-radius: 20px; padding: 3px 12px; font-size: 12px;
    font-weight: 700; margin-left: 10px; vertical-align: middle;
  }
  .composite-score-card .cs-base {
    font-size: 11px; opacity: 0.75; margin-top: 4px;
  }
  .composite-score-card .cs-risk {
    display: inline-block; margin-top: 8px;
    padding: 4px 10px; border-radius: 8px; font-size: 11px; font-weight: 700;
  }
  .cs-risk-normal { background: #dcfce7; color: #15803d; }
  .cs-risk-caution { background: #fef3c7; color: #b45309; }
  .cs-risk-mid    { background: #fed7aa; color: #c2410c; }
  .cs-risk-high   { background: #fee2e2; color: #dc2626; }
  .adj-list {
    margin-top: 10px; display: flex; flex-direction: column; gap: 4px;
  }
  .adj-item {
    display: flex; justify-content: space-between; align-items: center;
    background: rgba(255,255,255,0.1); border-radius: 6px;
    padding: 5px 10px; font-size: 11px;
  }
  .adj-delta-pos { color: #86efac; font-weight: 700; }
  .adj-delta-neg { color: #fca5a5; font-weight: 700; }
  .adj-delta-zer { color: rgba(255,255,255,0.5); }
  /* 의료이력 체크박스 */
  .medical-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 7px;
    margin-bottom: 10px;
  }
  .medical-check {
    display: flex; align-items: center; gap: 7px;
    padding: 7px 10px;
    border: 1.5px solid #e2e8f0; border-radius: 8px;
    cursor: pointer; font-size: 12px; color: #374151;
    transition: all 0.15s; user-select: none;
  }
  .medical-check:hover { border-color: #93c5fd; background: #eff6ff; }
  .medical-check input[type=checkbox] { accent-color: #2563eb; width: 14px; height: 14px; }
  .medical-check.checked { border-color: #2563eb; background: #eff6ff; font-weight: 600; }
  /* 점수 분해 카드 (결과 영역 상단) */
  .score-breakdown-card {
    background: #f8fafc; border: 1.5px solid #e2e8f0;
    border-radius: 10px; padding: 14px 16px; margin-bottom: 14px;
    font-size: 12.5px;
  }
  .score-breakdown-card h4 {
    font-size: 12px; font-weight: 700; color: #1e40af;
    margin: 0 0 10px; display: flex; align-items: center; gap: 6px;
  }
  .sbc-row {
    display: flex; justify-content: space-between;
    padding: 4px 0; border-bottom: 1px solid #f1f5f9; color: #374151;
  }
  .sbc-row:last-child { border-bottom: none; }
  .sbc-pos { color: #16a34a; font-weight: 700; }
  .sbc-neg { color: #dc2626; font-weight: 700; }
  .sbc-zer { color: #94a3b8; }

  /* 약관대출 카드 */
  .policy-loan-card {
    background: #f0f9ff; border: 1px solid #bae6fd;
    border-radius: 10px; padding: 16px; margin-bottom: 16px; font-size: 13px;
  }
  .policy-loan-card h4 { margin: 0 0 4px; color: #0369a1; font-size: 14px; font-weight: 700; }
  .loan-subtitle { color: #64748b; font-size: 11.5px; margin: 0 0 12px; }
  .loan-table-wrap { overflow-x: auto; }
  .loan-table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 520px; }
  .loan-table th, .loan-table td {
    border: 1px solid #bae6fd; padding: 6px 10px; text-align: right; white-space: nowrap;
  }
  .loan-table th:first-child, .loan-table td:first-child,
  .loan-table th:nth-child(2), .loan-table td:nth-child(2) { text-align: left; }
  .loan-table thead th { background: #e0f2fe; font-weight: 700; color: #0369a1; }
  .loan-table .loan-total-row td { background: #dbeafe; font-weight: 700; border-top: 2px solid #93c5fd; }
  .inelig-section { margin-top: 10px; font-size: 11.5px; color: #64748b; }
  .inelig-badge {
    display: inline-block; background: #f1f5f9; border: 1px solid #e2e8f0;
    border-radius: 4px; padding: 1px 7px; margin: 2px 2px; font-size: 11px; color: #64748b;
  }
  .loan-disclaimer { color: #94a3b8; font-size: 10.5px; margin: 10px 0 0; line-height: 1.5; }
  .loan-basis { margin-top: 10px; }
  .loan-basis summary {
    cursor: pointer; font-size: 11.5px; color: #0369a1; font-weight: 600;
    user-select: none; outline: none; list-style: none; padding: 4px 0;
  }
  .loan-basis summary::-webkit-details-marker { display: none; }
  .loan-basis-body { margin-top: 8px; }
  .loan-basis-formula { font-size: 11.5px; color: #334155; margin: 0 0 8px; }
  .loan-basis-table td, .loan-basis-table th { font-size: 11px; padding: 4px 8px; }
  .loan-basis-table td { color: #475569; }

  /* 보험 가입 링크 버튼 */
  .ins-link-btn {
    display: inline-block; padding: 3px 9px; border-radius: 4px;
    background: #1d4ed8; color: #fff !important; font-size: 11px; font-weight: 600;
    text-decoration: none !important; white-space: nowrap;
    transition: background 0.15s;
  }
  .ins-link-btn:hover { background: #1e40af; }
  .ins-link-damoah { background: #0369a1; }
  .ins-link-damoah:hover { background: #075985; }
  /* 채팅 버블 내 테이블 가입 링크 열 */
  .bubble table th:last-child,
  .bubble table td:last-child,
  #credit-result-body table th:last-child,
  #credit-result-body table td:last-child { white-space: nowrap; text-align: center; }

  /* ── Health Risk Panel ── */
  .health-panel {
    flex: 1; overflow-y: auto; padding: 20px; background: #f0f4f8;
  }
  .health-form-card {
    background: white; border-radius: 12px; padding: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 16px;
  }
  .health-form-card h3 { font-size: 14px; color: #1e293b; font-weight: 700; margin-bottom: 14px; }
  .health-section-label {
    font-size: 12px; font-weight: 700; color: #047857;
    margin: 14px 0 8px; padding-bottom: 4px; border-bottom: 1.5px solid #d1fae5;
  }
  .health-gen-btn {
    width: 100%; margin-top: 16px; padding: 13px;
    background: linear-gradient(135deg, #059669, #047857);
    color: white; border: none; border-radius: 10px;
    font-size: 14px; font-weight: 700; cursor: pointer; transition: opacity 0.2s;
  }
  .health-gen-btn:hover { opacity: 0.92; }
  .health-gen-btn:disabled { opacity: 0.55; cursor: not-allowed; }
  /* 위험도 게이지 */
  .risk-gauge-card {
    background: white; border-radius: 12px; padding: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 16px;
  }
  .risk-gauge-title { font-size: 14px; font-weight: 700; color: #1e293b; margin-bottom: 14px; }
  .risk-bar-track {
    width: 100%; height: 16px; border-radius: 8px;
    background: linear-gradient(to right, #22c55e 0%, #eab308 40%, #f97316 65%, #ef4444 100%);
    position: relative; margin-bottom: 6px;
  }
  .risk-bar-pointer {
    position: absolute; top: -6px; width: 28px; height: 28px; border-radius: 50%;
    background: white; border: 3px solid #374151; transform: translateX(-50%);
    transition: left 0.8s cubic-bezier(0.34,1.56,0.64,1);
    box-shadow: 0 2px 6px rgba(0,0,0,0.2);
  }
  .risk-bar-labels {
    display: flex; justify-content: space-between;
    font-size: 10.5px; color: #94a3b8; margin-bottom: 14px;
  }
  .risk-score-num { font-size: 30px; font-weight: 800; letter-spacing: -1px; color: #1e293b; }
  .risk-band-chip {
    display: inline-block; padding: 3px 12px; border-radius: 20px;
    font-size: 13px; font-weight: 700; margin-left: 10px; vertical-align: middle;
  }
  .risk-band-low  { background: #dcfce7; color: #15803d; }
  .risk-band-mid  { background: #fef3c7; color: #b45309; }
  .risk-band-high { background: #fee2e2; color: #dc2626; }
  .hr-model-note { font-size: 10.5px; color: #94a3b8; margin-top: 3px; }
  /* 임상 플래그 */
  .flag-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
  .flag-chip {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;
    background: #fef3c7; color: #92400e; border: 1px solid #fde68a;
  }
  .flag-chip-ok { background: #dcfce7; color: #166534; border-color: #bbf7d0; }
  /* 추천 보험 유형 태그 */
  .ins-type-tags { display: flex; flex-wrap: wrap; gap: 7px; margin: 10px 0 12px; }
  .ins-type-tag {
    padding: 5px 14px; border-radius: 20px; font-size: 12.5px; font-weight: 600;
    background: #eff6ff; color: #1d4ed8; border: 1.5px solid #bfdbfe;
  }
  .hr-guidance {
    font-size: 12.5px; color: #475569; line-height: 1.6; padding: 10px 12px;
    background: #f0fdf4; border-radius: 8px; border-left: 3px solid #22c55e;
  }
  /* 상품 카드 */
  .product-type-sec {
    border: 1.5px solid #e2e8f0; border-radius: 10px; margin-bottom: 10px; overflow: hidden;
  }
  .product-type-hdr {
    background: #f8fafc; padding: 10px 14px; font-size: 13px; font-weight: 700;
    color: #1e40af; display: flex; justify-content: space-between; align-items: center;
    cursor: pointer; user-select: none;
  }
  .product-type-hdr:hover { background: #eff6ff; }
  .product-cards-body { padding: 10px 14px; }
  .hr-product-card {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 12px 14px; margin-bottom: 8px;
  }
  .hr-product-card:last-child { margin-bottom: 0; }
  .hr-prod-name { font-weight: 700; color: #1e293b; font-size: 13px; margin-bottom: 2px; }
  .hr-prod-co { color: #64748b; font-size: 11.5px; margin-bottom: 7px; }
  .hr-prod-row {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 12.5px; padding: 2px 0; color: #374151;
  }
  .hr-prod-premium { font-weight: 700; color: #1d4ed8; }
  /* 면책 고지 */
  .health-disclaimer {
    background: #fefce8; border: 1px solid #fde68a; border-radius: 8px;
    padding: 12px 14px; font-size: 11.5px; color: #92400e;
    margin-bottom: 16px; line-height: 1.7;
  }
  /* 이노베이션 존 배지 */
  .inno-zone-badge {
    display:inline-flex; align-items:center; gap:5px;
    background:#eff6ff; border:1px solid #bfdbfe; border-radius:6px;
    padding:4px 10px; font-size:11px; color:#1d4ed8; font-weight:600;
    margin-bottom:10px;
  }
  /* 암 위험 바 */
  .cancer-bar-wrap { margin: 6px 0; }
  .cancer-bar-label { display:flex; justify-content:space-between; font-size:12px; color:#334155; margin-bottom:3px; }
  .cancer-bar-track { height:10px; background:#e2e8f0; border-radius:5px; overflow:hidden; }
  .cancer-bar-fill  { height:100%; border-radius:5px; transition:width 0.4s ease; }
  .cancer-surv { font-size:11px; color:#64748b; margin-top:2px; }
  .cancer-risk-summary { display:flex; align-items:center; gap:10px; margin-bottom:12px; }
  .cancer-band-chip {
    padding:3px 10px; border-radius:20px; font-size:12px; font-weight:700;
  }
  .cancer-band-high { background:#fee2e2; color:#991b1b; }
  .cancer-band-mid  { background:#fef3c7; color:#92400e; }
  .cancer-band-low  { background:#dcfce7; color:#166534; }
  /* BFC 분위 바 */
  .bfc-tier-bar { height:14px; border-radius:6px; margin:8px 0; transition:width 0.4s ease; }
  .bfc-tier-row { display:flex; justify-content:space-between; font-size:12px; color:#334155; margin-top:4px; }
  /* 건강검진 데이터 소스 카드 */
  .health-source-cards {
    display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px;
  }
  .health-source-card {
    flex: 1; min-width: 120px; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 11px 13px; background: #f8fafc; cursor: pointer; transition: all 0.15s;
  }
  .health-source-card:hover { border-color: #22c55e; background: #f0fdf4; }
  .health-source-card .src-icon { font-size: 20px; margin-bottom: 4px; }
  .health-source-card .src-name { font-size: 12.5px; font-weight: 700; color: #1e293b; }
  .health-source-card .src-desc { font-size: 11px; color: #64748b; margin-top: 2px; line-height: 1.4; }
  /* 건강검진 가져오기 상세 가이드 탭 */
  .health-guide-tabs { display:flex; gap:0; border-bottom:2px solid #e2e8f0; margin:10px 0 0; flex-wrap:wrap; }
  .hg-tab { padding:7px 14px; font-size:12.5px; font-weight:600; cursor:pointer;
    color:#64748b; border:none; border-bottom:2px solid transparent; margin-bottom:-2px;
    background:none; transition:all 0.15s; }
  .hg-tab.active { color:#047857; border-bottom-color:#047857; }
  .hg-pane { display:none; padding:12px 0 0; }
  .hg-pane.active { display:block; }
  .hg-steps { list-style:none; padding:0; margin:0; }
  .hg-step { display:flex; gap:10px; align-items:flex-start; padding:7px 0;
    border-bottom:1px solid #f1f5f9; font-size:12.5px; line-height:1.55; color:#334155; }
  .hg-step:last-child { border-bottom:none; }
  .hg-num { flex-shrink:0; width:20px; height:20px; border-radius:50%;
    background:#047857; color:white; font-size:11px; font-weight:700;
    display:flex; align-items:center; justify-content:center; }
  .hg-app-table { width:100%; border-collapse:collapse; font-size:12px; margin-top:6px; }
  .hg-app-table th { background:#f0fdf4; padding:7px 10px; border:1px solid #d1fae5;
    text-align:left; font-size:11.5px; color:#065f46; font-weight:700; }
  .hg-app-table td { padding:8px 10px; border:1px solid #e5e7eb; font-size:12px;
    color:#334155; vertical-align:top; line-height:1.55; }
  .hg-app-table tr:hover td { background:#f9fafb; }
  .hg-link { display:inline-block; margin-top:10px; font-size:12px;
    color:#047857; font-weight:600; text-decoration:none; }
  .hg-link:hover { text-decoration:underline; }
  /* PDF 드롭존 */
  .pdf-drop-zone {
    border: 2px dashed #d1d5db; border-radius: 10px; padding: 22px 16px;
    text-align: center; cursor: pointer; transition: all 0.2s; background: #fafafa;
  }
  .pdf-drop-zone:hover, .pdf-drop-zone.dragover {
    border-color: #047857; background: #f0fdf4;
  }
  .pdf-drop-icon { font-size: 28px; margin-bottom: 6px; }
  .pdf-drop-text { font-size: 13px; font-weight: 600; color: #374151; }
  .pdf-drop-sub  { font-size: 11px; color: #94a3b8; margin-top: 3px; }
  .pdf-or-divider {
    display: flex; align-items: center; gap: 10px;
    margin: 14px 0; font-size: 12px; color: #94a3b8;
  }
  .pdf-or-divider::before, .pdf-or-divider::after {
    content: ''; flex: 1; height: 1px; background: #e2e8f0;
  }
  /* 텍스트 붙여넣기 */
  .paste-area {
    width: 100%; min-height: 88px; padding: 10px 12px;
    border: 1.5px solid #e2e8f0; border-radius: 8px; font-size: 12px;
    font-family: inherit; resize: vertical; outline: none; color: #374151;
    transition: border-color 0.15s; line-height: 1.5; background: #fafafa;
  }
  .paste-area:focus { border-color: #22c55e; background: white; }
  .parse-btn {
    margin-top: 8px; padding: 8px 18px;
    background: #047857; color: white; border: none; border-radius: 8px;
    font-size: 13px; font-weight: 600; cursor: pointer; transition: opacity 0.15s;
  }
  .parse-btn:hover { opacity: 0.88; }
  .parse-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  /* AI 추천 카드 */
  .ai-rec-card {
    background: white; border-radius: 12px; padding: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 16px;
    border-top: 3px solid #6d28d9;
  }
  .ai-rec-card-title {
    display: flex; align-items: center; gap: 8px;
    font-size: 14px; font-weight: 700; color: #1e293b; margin-bottom: 14px;
  }
  .ai-rec-btn {
    width: 100%; padding: 12px;
    background: linear-gradient(135deg, #7c3aed, #5b21b6);
    color: white; border: none; border-radius: 10px;
    font-size: 14px; font-weight: 700; cursor: pointer; transition: opacity 0.2s;
  }
  .ai-rec-btn:hover { opacity: 0.9; }
  .ai-rec-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .ai-rec-body {
    line-height: 1.7; font-size: 13.5px; color: #1e293b; margin-top: 14px;
  }
  .ai-rec-body h2 { font-size: 15px; color: #5b21b6; margin: 0 0 10px; padding-bottom: 6px; border-bottom: 2px solid #ede9fe; }
  .ai-rec-body h3 { font-size: 14px; color: #374151; margin: 14px 0 6px; }
  .ai-rec-body h4 { font-size: 13px; color: #374151; margin: 10px 0 5px; }
  .ai-rec-body table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 12.5px; }
  .ai-rec-body th { background: #f5f3ff; padding: 7px 10px; border: 1px solid #ddd6fe; text-align: left; font-weight: 600; }
  .ai-rec-body td { padding: 7px 10px; border: 1px solid #e5e7eb; }
  .ai-rec-body ul, .ai-rec-body ol { padding-left: 18px; margin: 5px 0; }
  .ai-rec-body blockquote { border-left: 3px solid #7c3aed; padding-left: 12px; color: #475569; margin: 8px 0; }
  .ai-rec-body strong { color: #5b21b6; }
  .ai-rec-body p { margin: 6px 0; }

  /* ── DIOBIO Wellness Tab ── */
  .tab-btn.diobio-tab { border-bottom-color: #10b981; }
  .tab-btn.diobio-tab.active { border-bottom-color: #34d399; color: #d1fae5; }
  .diobio-panel { flex: 1; overflow-y: auto; background: #f0fdf4; }

  /* Landing */
  .db-landing {
    min-height: 100%; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 48px 24px; text-align: center;
    background: linear-gradient(160deg,#ecfdf5 0%,#d1fae5 55%,#a7f3d0 100%);
  }
  .db-logo { font-size: 52px; margin-bottom: 12px; }
  .db-brand { font-size: 30px; font-weight: 900; color: #064e3b; letter-spacing: -1px; margin-bottom: 10px; }
  .db-tagline { font-size: 14.5px; color: #065f46; line-height: 1.8; max-width: 340px; margin: 0 auto 32px; }
  .db-tagline em { font-style: normal; color: #047857; font-weight: 700; }
  .db-cta-main {
    background: linear-gradient(135deg,#10b981,#059669); color: white;
    border: none; border-radius: 50px; padding: 16px 38px;
    font-size: 16px; font-weight: 700; cursor: pointer;
    box-shadow: 0 4px 20px rgba(16,185,129,.4); transition: all .2s;
    letter-spacing: -.3px;
  }
  .db-cta-main:hover { transform: translateY(-2px); box-shadow: 0 6px 26px rgba(16,185,129,.5); }
  .db-features { display: flex; gap: 14px; margin-top: 36px; flex-wrap: wrap; justify-content: center; }
  .db-feat {
    background: white; border-radius: 14px; padding: 14px 18px;
    text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,.06);
    min-width: 90px; font-size: 12px; color: #065f46;
  }
  .db-feat i { font-size: 22px; display: block; margin-bottom: 6px; font-style: normal; }

  /* Survey */
  .db-survey { padding: 20px 20px 32px; max-width: 620px; margin: 0 auto; }
  .db-progress { margin-bottom: 22px; }
  .db-step-meta { font-size: 11px; color: #6b7280; margin-bottom: 8px; display: flex; justify-content: space-between; }
  .db-pbar { height: 6px; background: #d1fae5; border-radius: 10px; overflow: hidden; }
  .db-pbar-fill { height: 100%; background: linear-gradient(90deg,#10b981,#059669); border-radius: 10px; transition: width .4s; }
  .db-step-title { font-size: 19px; font-weight: 800; color: #064e3b; margin-bottom: 6px; letter-spacing: -.5px; line-height: 1.3; }
  .db-step-sub { font-size: 12.5px; color: #6b7280; margin-bottom: 20px; }

  /* Option Cards */
  .db-opts { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; }
  .db-opts.col1 { grid-template-columns: 1fr; }
  .db-opts.col3 { grid-template-columns: 1fr 1fr 1fr; }
  .db-opt {
    background: white; border: 2px solid #d1fae5; border-radius: 12px;
    padding: 14px 12px; cursor: pointer; transition: all .15s;
    text-align: center; font-size: 13px; color: #374151; font-weight: 500;
  }
  .db-opt:hover { border-color: #10b981; background: #f0fdf4; }
  .db-opt.sel { border-color: #10b981; background: #ecfdf5; color: #065f46; font-weight: 700; }
  .db-opt-ic { font-size: 22px; display: block; margin-bottom: 6px; }

  /* Lifestyle Qs */
  .db-q { background: white; border-radius: 12px; padding: 14px 16px; margin-bottom: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.05); }
  .db-q-lbl { font-size: 13.5px; font-weight: 600; color: #1f2937; margin-bottom: 10px; }
  .db-q-row { display: flex; gap: 6px; }
  .db-q-o {
    flex: 1; background: #f9fafb; border: 1.5px solid #e5e7eb; border-radius: 8px;
    padding: 9px 6px; text-align: center; font-size: 11.5px; color: #6b7280;
    cursor: pointer; transition: all .15s; font-weight: 500;
  }
  .db-q-o:hover { border-color: #10b981; color: #065f46; background: #f0fdf4; }
  .db-q-o.sel { border-color: #10b981; background: #ecfdf5; color: #065f46; font-weight: 700; }

  /* Safety Check */
  .db-safety-note { background: #fffbeb; border: 1px solid #fde68a; border-radius: 10px; padding: 12px 14px; font-size: 12px; color: #92400e; margin-bottom: 14px; line-height: 1.6; }
  .db-chk-item {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 12px 14px; background: white; border-radius: 10px;
    margin-bottom: 8px; cursor: pointer; border: 1.5px solid #e5e7eb; transition: border-color .15s;
  }
  .db-chk-item.on { border-color: #ef4444; background: #fef2f2; }
  .db-chk-item input { width: 16px; height: 16px; margin-top: 1px; accent-color: #ef4444; flex-shrink: 0; }
  .db-chk-text { font-size: 13px; color: #374151; }

  /* Navigation */
  .db-nav { display: flex; gap: 10px; margin-top: 8px; }
  .db-btn-p {
    background: white; border: 2px solid #d1d5db; color: #6b7280;
    border-radius: 50px; padding: 12px 22px; font-size: 14px; font-weight: 600;
    cursor: pointer; transition: all .15s; white-space: nowrap;
  }
  .db-btn-p:hover { border-color: #9ca3af; color: #374151; }
  .db-btn-n {
    flex: 1; background: linear-gradient(135deg,#10b981,#059669);
    color: white; border: none; border-radius: 50px;
    padding: 13px 20px; font-size: 14px; font-weight: 700;
    cursor: pointer; transition: all .2s; box-shadow: 0 2px 10px rgba(16,185,129,.3);
  }
  .db-btn-n:hover { transform: translateY(-1px); box-shadow: 0 4px 14px rgba(16,185,129,.4); }

  /* Result */
  .db-result { padding: 20px 20px 40px; max-width: 620px; margin: 0 auto; }
  .db-res-hero {
    text-align: center; padding: 28px 20px;
    background: linear-gradient(135deg,#ecfdf5,#d1fae5);
    border-radius: 18px; margin-bottom: 18px;
  }
  .db-res-icon { font-size: 54px; margin-bottom: 10px; }
  .db-res-type { font-size: 11.5px; font-weight: 700; color: #10b981; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 6px; }
  .db-res-name { font-size: 20px; font-weight: 900; color: #064e3b; letter-spacing: -.5px; margin-bottom: 12px; line-height: 1.3; }
  .db-res-desc { font-size: 13px; color: #374151; line-height: 1.75; max-width: 400px; margin: 0 auto; }
  .db-med-alert { background: #fff7ed; border: 1.5px solid #fb923c; border-radius: 12px; padding: 14px 16px; margin-bottom: 16px; font-size: 13px; color: #92400e; line-height: 1.7; }
  .db-sol-hd { font-size: 11px; font-weight: 700; color: #10b981; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 10px; }
  .db-sol-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
  .db-sol-card { background: white; border-radius: 12px; padding: 14px; box-shadow: 0 1px 6px rgba(0,0,0,.06); }
  .db-sol-card-h { font-size: 12px; font-weight: 700; color: #374151; margin-bottom: 6px; }
  .db-sol-card-b { font-size: 12px; color: #6b7280; line-height: 1.65; }
  .db-ctas { display: flex; flex-direction: column; gap: 10px; margin-top: 20px; }
  .db-btn-kakao { background: #FEE500; color: #191600; border: none; border-radius: 12px; padding: 15px; font-size: 14px; font-weight: 700; cursor: pointer; text-align: center; }
  .db-btn-kakao:hover { opacity: .9; }
  .db-btn-green { background: linear-gradient(135deg,#10b981,#059669); color: white; border: none; border-radius: 12px; padding: 15px; font-size: 14px; font-weight: 700; cursor: pointer; text-align: center; }
  .db-btn-green:hover { opacity: .9; }
  .db-btn-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .db-btn-out { background: white; border: 2px solid #d1fae5; color: #065f46; border-radius: 12px; padding: 12px; font-size: 13px; font-weight: 600; cursor: pointer; text-align: center; }
  .db-btn-out:hover { background: #ecfdf5; }
  .db-privacy { font-size: 11px; color: #9ca3af; line-height: 1.65; background: #f9fafb; border-radius: 10px; padding: 12px 14px; margin-top: 6px; }
  .db-restart { background: transparent; border: 1.5px solid #d1d5db; color: #9ca3af; border-radius: 10px; padding: 12px; font-size: 13px; cursor: pointer; width: 100%; margin-top: 10px; }
  .db-restart:hover { border-color: #9ca3af; color: #6b7280; }

  /* DIOBIO Modals */
  .db-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,.55); z-index:2000; align-items:center; justify-content:center; padding:16px; }
  .db-overlay.open { display:flex; }
  .db-modal { background:white; border-radius:20px; width:100%; max-width:480px; max-height:88vh; overflow-y:auto; box-shadow:0 20px 60px rgba(0,0,0,.3); }
  .db-modal-hd { display:flex; align-items:center; justify-content:space-between; padding:18px 20px 14px; border-bottom:1px solid #f0fdf4; position:sticky; top:0; background:white; z-index:1; }
  .db-modal-title { font-size:16px; font-weight:800; color:#064e3b; }
  .db-modal-close { background:#f3f4f6; border:none; font-size:14px; cursor:pointer; color:#6b7280; padding:6px 10px; border-radius:8px; font-weight:700; }
  .db-modal-body { padding:20px; }
  .db-form-group { margin-bottom:14px; }
  .db-form-label { font-size:12.5px; font-weight:700; color:#374151; margin-bottom:6px; display:block; }
  .db-form-input { width:100%; padding:11px 14px; border:1.5px solid #d1fae5; border-radius:10px; font-size:14px; box-sizing:border-box; outline:none; font-family:inherit; }
  .db-form-input:focus { border-color:#10b981; }
  .db-form-select { width:100%; padding:11px 14px; border:1.5px solid #d1fae5; border-radius:10px; font-size:14px; background:white; box-sizing:border-box; font-family:inherit; }
  .db-form-select:focus { border-color:#10b981; outline:none; }
  .db-submit-btn { width:100%; background:linear-gradient(135deg,#10b981,#059669); color:white; border:none; border-radius:12px; padding:14px; font-size:15px; font-weight:700; cursor:pointer; margin-top:4px; }
  .db-submit-btn:hover { opacity:.9; }
  .db-food-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .db-food-card { background:#f0fdf4; border:1.5px solid #d1fae5; border-radius:14px; padding:14px; }
  .db-food-card-name { font-size:13px; font-weight:700; color:#065f46; margin-bottom:4px; }
  .db-food-card-desc { font-size:11.5px; color:#6b7280; line-height:1.55; margin-bottom:8px; }
  .db-food-tags { display:flex; flex-wrap:wrap; gap:4px; margin-bottom:10px; }
  .db-food-tag { background:#d1fae5; color:#065f46; font-size:10px; font-weight:600; padding:3px 8px; border-radius:20px; }
  .db-food-add { width:100%; background:white; border:1.5px solid #10b981; color:#065f46; border-radius:8px; padding:8px; font-size:12px; font-weight:600; cursor:pointer; }
  .db-food-add:hover { background:#ecfdf5; }
  .db-glp1-banner { background:linear-gradient(135deg,#eff6ff,#dbeafe); border:1.5px solid #93c5fd; border-radius:14px; padding:16px; margin-bottom:16px; }
  .db-glp1-title { font-size:14px; font-weight:800; color:#1d4ed8; margin-bottom:8px; }
  .db-glp1-body { font-size:12.5px; color:#1e40af; line-height:1.7; }
  .db-glp1-cta { display:inline-block; margin-top:10px; background:#1d4ed8; color:white; border:none; border-radius:8px; padding:10px 16px; font-size:12.5px; font-weight:700; cursor:pointer; }
  .db-landing-cards { display:grid; grid-template-columns:1fr 1fr; gap:10px; width:100%; max-width:360px; margin-top:28px; }
  .db-landing-card { background:white; border-radius:14px; padding:14px 12px; text-align:center; box-shadow:0 2px 10px rgba(0,0,0,.07); }
  .db-landing-card-ic { font-size:26px; margin-bottom:6px; }
  .db-landing-card-nm { font-size:12.5px; font-weight:700; color:#065f46; margin-bottom:3px; }
  .db-landing-card-ds { font-size:11px; color:#9ca3af; line-height:1.5; }
  .db-new-badge { display:inline-block; background:#ef4444; color:white; font-size:9.5px; font-weight:700; padding:2px 6px; border-radius:20px; vertical-align:middle; margin-left:4px; letter-spacing:.3px; }

  @media(max-width:480px) {
    .db-opts { grid-template-columns: 1fr 1fr; }
    .db-opts.col3 { grid-template-columns: 1fr 1fr; }
    .db-sol-grid { grid-template-columns: 1fr; }
    .db-btn-row { grid-template-columns: 1fr; }
  }

  /* 신용점수 개선 시뮬레이터 */
  .score-sim-card { background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:18px; margin-bottom:14px; }
  .score-sim-title { font-size:13.5px; font-weight:700; color:#1e293b; margin-bottom:12px; display:flex; align-items:center; gap:6px; }
  .score-sim-scenario { background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:12px; margin-bottom:8px; }
  .score-sim-target { font-size:12px; font-weight:700; color:#3b82f6; margin-bottom:4px; }
  .score-sim-gap { font-size:11px; color:#64748b; margin-bottom:6px; }
  .score-sim-steps { list-style:none; padding:0; margin:0 0 6px; }
  .score-sim-steps li { font-size:11.5px; color:#334155; padding:2px 0; display:flex; align-items:center; gap:4px; }
  .score-sim-steps li::before { content:'→'; color:#3b82f6; font-weight:700; }
  .score-sim-benefits { display:flex; flex-wrap:wrap; gap:4px; margin-top:6px; }
  .score-sim-benefit { background:#dbeafe; color:#1d4ed8; font-size:10.5px; padding:2px 7px; border-radius:20px; }
  .score-sim-achieved { background:#dcfce7; color:#15803d; font-size:10.5px; padding:2px 7px; border-radius:20px; }

  /* 5축 레이더 차트 */
  .radar-chart-card { background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:18px; margin-bottom:14px; }
  .radar-chart-title { font-size:13.5px; font-weight:700; color:#1e293b; margin-bottom:12px; display:flex; align-items:center; gap:6px; }
  #credit-radar-canvas { max-width:280px; margin:0 auto; display:block; }

  /* 보험료 납입이력 가점 안내 */
  .premium-hist-card { background:linear-gradient(135deg,#f0fdf4,#dcfce7); border:1px solid #bbf7d0; border-radius:14px; padding:14px; margin-bottom:14px; }
  .premium-hist-title { font-size:13px; font-weight:700; color:#166534; margin-bottom:8px; }
  .premium-hist-row { display:flex; justify-content:space-between; align-items:center; font-size:12px; color:#15803d; padding:3px 0; border-bottom:1px dashed #bbf7d0; }
  .premium-hist-row:last-child { border-bottom:none; }
  .premium-hist-pts { font-weight:700; color:#16a34a; }

  /* Health-Credit 가점 카드 (웰니스) */
  .hr-hc-bonus-card { background:linear-gradient(135deg,#eff6ff,#dbeafe); border:1px solid #bfdbfe; border-radius:14px; padding:14px; margin-bottom:14px; }
  .hr-hc-bonus-title { font-size:13px; font-weight:700; color:#1e40af; margin-bottom:10px; display:flex; align-items:center; gap:6px; }
  .hr-hc-bonus-row { display:flex; justify-content:space-between; font-size:12px; padding:3px 0; color:#1d4ed8; }
  .hr-hc-bonus-total { font-size:14px; font-weight:800; color:#1e3a8a; margin-top:8px; padding-top:8px; border-top:1px solid #bfdbfe; display:flex; justify-content:space-between; }
  .hr-hc-bonus-note { font-size:10.5px; color:#3b82f6; margin-top:6px; }

  /* 음식 상품 링크 버튼 */
  .db-food-link { display:block; width:100%; text-align:center; padding:7px; background:#f0f9ff; border:1px solid #bae6fd; border-radius:8px; color:#0369a1; font-size:12px; font-weight:600; text-decoration:none; margin-top:6px; cursor:pointer; }
  .db-food-link:hover { background:#e0f2fe; }

  /* 웰니스 여행 카드 */
  .db-travel-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .db-travel-card { background:#f0f9ff; border:1.5px solid #bae6fd; border-radius:14px; padding:14px; }
  .db-travel-card-name { font-size:13px; font-weight:700; color:#0c4a6e; margin-bottom:4px; }
  .db-travel-card-desc { font-size:11.5px; color:#6b7280; line-height:1.55; margin-bottom:8px; }
  .db-travel-tags { display:flex; flex-wrap:wrap; gap:4px; margin-bottom:10px; }
  .db-travel-tag { background:#e0f2fe; color:#0369a1; font-size:10px; font-weight:600; padding:3px 8px; border-radius:20px; }
  .db-travel-link { display:block; width:100%; text-align:center; padding:7px; background:white; border:1.5px solid #38bdf8; color:#0369a1; border-radius:8px; font-size:12px; font-weight:600; text-decoration:none; cursor:pointer; }
  .db-travel-link:hover { background:#e0f2fe; }
</style>
</head>
<body>

<div class="header">
  <div class="header-icon">🛡️</div>
  <div>
    <div class="header-title">보험 상담 AI 어시스턴트</div>
    <div class="header-sub">종신 · 실손 · 암 · 치아 · 간병·치매 · 연금보험</div>
  </div>
  <div class="mode-selector" id="modeSelector">
    <div class="mode-badge" id="modeBadge" onclick="toggleModeDropdown()">확인 중... ▾</div>
    <div class="mode-dropdown" id="modeDropdown">
      <div class="mode-option" onclick="setMode('auto')">🔄 Auto (자동)</div>
      <div class="mode-option" onclick="setMode('live')">🟢 Live Mode</div>
      <div class="mode-option" onclick="setMode('mock')">🔧 Mock Mode</div>
    </div>
  </div>
</div>

<!-- Tab Navigation -->
<div class="tab-nav">
  <button class="tab-btn active" onclick="switchTab('chat')">💬 보험 상담</button>
  <button class="tab-btn" onclick="switchTab('credit')">💳 신용점수 포트폴리오</button>
  <button class="tab-btn" onclick="switchTab('health')">🏥 건강위험 포트폴리오</button>
  <button class="tab-btn demo-tab" onclick="switchTab('demo')">🏆 대회 데모</button>
  <button class="tab-btn diobio-tab" onclick="switchTab('diobio')">🌿 DIOBIO 웰니스</button>
</div>

<!-- Tab: 보험 상담 -->
<div class="tab-panel active" id="tab-chat">
  <div id="chat"></div>
  <div class="quick-buttons">
    <button class="qbtn" onclick="quickSend('40대 남성 암보험 추천해줘')">암보험 추천</button>
    <button class="qbtn" onclick="quickSend('40대 남성 치아보험 추천해줘')">치아보험</button>
    <button class="qbtn" onclick="quickSend('실손보험 보험사별 비교해줘')">실손보험 비교</button>
    <button class="qbtn" onclick="quickSend('간병보험·치매보험 추천해줘')">간병·치매보험</button>
    <button class="qbtn" onclick="quickSend('45세 남성 보험 포트폴리오 추천해줘')">포트폴리오 추천</button>
    <button class="qbtn" onclick="quickSend('실손보험 4세대 5세대 차이 알려줘')">4세대 vs 5세대</button>
  </div>
  <div class="input-area">
    <button class="reset-btn" onclick="resetChat()" title="대화 초기화">🔄</button>
    <textarea id="input" placeholder="보험에 대해 무엇이든 물어보세요..." rows="1"
      onkeydown="handleKey(event)" oninput="autoResize(this)"></textarea>
    <button id="send" onclick="sendMessage()">➤</button>
  </div>
</div>

<!-- Tab: 신용점수 포트폴리오 -->
<div class="tab-panel" id="tab-credit">
  <div class="credit-panel">

    <!-- 신용점수 확인 안내 -->
    <div class="credit-guide">
      <h3>📊 신용점수 확인 방법 (무료)</h3>
      <p style="font-size:12.5px;color:#475569;margin-bottom:8px;">아래 앱·사이트에서 신용점수를 무료로 확인 후 입력하세요. NICE·KCB 중 하나만 입력해도 됩니다.</p>
      <div class="score-sources">
        <div class="score-source-card" onclick="openUrl('https://toss.im')">
          <div class="source-logo">💚</div>
          <div class="source-name">토스</div>
          <div class="source-desc">KCB 점수 무료 조회<br>(앱 → 신용점수)</div>
          <span class="source-link">toss.im →</span>
        </div>
        <div class="score-source-card" onclick="openUrl('https://www.kakaopay.com')">
          <div class="source-logo">💛</div>
          <div class="source-name">카카오페이</div>
          <div class="source-desc">NICE 점수 무료 조회<br>(앱 → 신용점수 조회)</div>
          <span class="source-link">kakaopay.com →</span>
        </div>
        <div class="score-source-card" onclick="openUrl('https://credit.co.kr')">
          <div class="source-logo">🏛️</div>
          <div class="source-name">NICE 지키미</div>
          <div class="source-desc">NICE 공식 조회<br>(1회/월 무료)</div>
          <span class="source-link">credit.co.kr →</span>
        </div>
        <div class="score-source-card" onclick="openUrl('https://www.allcredit.co.kr')">
          <div class="source-logo">📋</div>
          <div class="source-name">올크레딧(KCB)</div>
          <div class="source-desc">KCB 공식 조회<br>(1회/월 무료)</div>
          <span class="source-link">allcredit.co.kr →</span>
        </div>
      </div>
    </div>

    <!-- 입력 폼 -->
    <div class="credit-form">
      <h3>✏️ 정보 입력</h3>
      <div class="form-grid">
        <div class="form-group">
          <label>나이</label>
          <input type="number" id="cf-age" placeholder="예: 42" min="20" max="70" value="">
        </div>
        <div class="form-group">
          <label>성별</label>
          <select id="cf-gender">
            <option value="남">남성</option>
            <option value="여">여성</option>
          </select>
        </div>
        <div class="form-group">
          <label>월 보험료 예산 (만원)</label>
          <input type="number" id="cf-budget" placeholder="예: 20" min="5" max="100" value="">
        </div>
        <div class="form-group">
          <label>기혼/미혼</label>
          <select id="cf-married">
            <option value="">선택 안함</option>
            <option value="기혼">기혼</option>
            <option value="미혼">미혼</option>
          </select>
        </div>
        <div class="form-group">
          <label>NICE 신용점수 <span style="font-weight:400;color:#94a3b8">(토스·카카오페이·NICE 지키미)</span></label>
          <div class="score-input-wrap">
            <input type="number" id="cf-nice" placeholder="없으면 비워두세요 (300~1000)"
              min="300" max="1000" oninput="updateScoreBadge('nice')">
            <span class="score-badge" id="badge-nice"></span>
          </div>
        </div>
        <div class="form-group">
          <label>KCB 신용점수 <span style="font-weight:400;color:#94a3b8">(토스·올크레딧)</span></label>
          <div class="score-input-wrap">
            <input type="number" id="cf-kcb" placeholder="없으면 비워두세요 (300~1000)"
              min="300" max="1000" oninput="updateScoreBadge('kcb')">
            <span class="score-badge" id="badge-kcb"></span>
          </div>
        </div>
        <div class="form-group full">
          <div class="score-avg-note" id="score-avg-note"></div>
        </div>
        <div class="form-group full">
          <label>현재 가입 보험 (선택)</label>
          <input type="text" id="cf-existing" placeholder="예: 실손보험 가입, 암보험 없음">
        </div>
        <div class="form-group full">
          <label>건강 특이사항 (선택)</label>
          <input type="text" id="cf-health" placeholder="예: 고혈압 약 복용 중, 특이사항 없음">
        </div>
      </div>
      <!-- 금융데이터 입력 -->
      <div class="extra-section">
        <div class="extra-section-header" onclick="toggleSection('financial')">
          <span>💰 금융데이터 <span style="font-weight:400;color:#94a3b8;font-size:11px">— 선택 입력 (더 정확한 추천)</span></span>
          <span class="extra-section-toggle" id="toggle-financial">▼</span>
        </div>
        <div class="extra-section-body" id="body-financial">
          <div class="form-grid">
            <div class="form-group">
              <label>연소득 (만원/년)</label>
              <input type="number" id="cf-income" placeholder="예: 4500" min="0" oninput="updateFinancialSummary()">
            </div>
            <div class="form-group">
              <label>금융자산 (만원)</label>
              <input type="number" id="cf-assets" placeholder="예: 3000 (예금·적금·주식 등)" min="0" oninput="updateFinancialSummary()">
            </div>
            <div class="form-group">
              <label>부채·대출 잔액 (만원)</label>
              <input type="number" id="cf-debt" placeholder="예: 5000" min="0" oninput="updateFinancialSummary()">
            </div>
            <div class="form-group">
              <label>현재 납입 보험료 (만원/월)</label>
              <input type="number" id="cf-current-premium" placeholder="예: 10" min="0" oninput="updateFinancialSummary()">
            </div>
          </div>
          <div class="financial-summary" id="financial-summary"></div>
        </div>
      </div>

      <!-- 대안데이터 입력 -->
      <div class="extra-section">
        <div class="extra-section-header" onclick="toggleSection('alt')">
          <span>📊 대안데이터 <span style="font-weight:400;color:#94a3b8;font-size:11px">— 선택 입력 (신용평가 보완)</span></span>
          <span class="extra-section-toggle" id="toggle-alt">▼</span>
        </div>
        <div class="extra-section-body" id="body-alt">
          <div class="form-grid">
            <div class="form-group">
              <label>직업 유형</label>
              <select id="cf-employment">
                <option value="">선택 안함</option>
                <option value="정규직">정규직 (직장인)</option>
                <option value="비정규직">비정규직 (계약직·파견)</option>
                <option value="자영업">자영업·사업자</option>
                <option value="프리랜서">프리랜서·독립계약</option>
                <option value="공무원">공무원·교직원</option>
                <option value="무직">무직·구직 중</option>
              </select>
            </div>
            <div class="form-group">
              <label>거주 형태</label>
              <select id="cf-housing">
                <option value="">선택 안함</option>
                <option value="자가">자가 (본인 소유)</option>
                <option value="전세">전세</option>
                <option value="월세">월세·반전세</option>
                <option value="가족거주">가족 소유 (무상거주)</option>
                <option value="기타">기타</option>
              </select>
            </div>
            <div class="form-group">
              <label>통신비 납부 이력</label>
              <select id="cf-telecom">
                <option value="">선택 안함</option>
                <option value="정상납부">정상납부 (지연 없음)</option>
                <option value="지연경험">지연 경험 있음</option>
                <option value="연체경험">연체 경험 있음</option>
              </select>
            </div>
            <div class="form-group">
              <label>공과금 납부 이력</label>
              <select id="cf-utility">
                <option value="">선택 안함</option>
                <option value="정상납부">정상납부 (지연 없음)</option>
                <option value="지연경험">지연 경험 있음</option>
                <option value="연체경험">연체 경험 있음</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- 최근 5년 치료 내역 -->
      <div class="extra-section">
        <div class="extra-section-header" onclick="toggleSection('medical')">
          <span>🏥 최근 5년 치료 내역 <span style="font-weight:400;color:#94a3b8;font-size:11px">— 선택 입력 (심사 유형 최적화)</span></span>
          <span class="extra-section-toggle" id="toggle-medical">▼</span>
        </div>
        <div class="extra-section-body" id="body-medical">
          <p style="font-size:11.5px;color:#64748b;margin:0 0 10px">최근 5년 내 진단·치료 이력이 있는 항목을 선택하세요. 심사 유형(일반/간편/무심사) 결정에 활용됩니다.</p>
          <div class="medical-grid" id="medical-grid">
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="암·종양 치료"> 암·종양 치료
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="심장질환"> 심장질환 (협심증·심근경색)
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="뇌질환"> 뇌질환 (뇌졸중·뇌경색)
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="당뇨병"> 당뇨병
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="고혈압"> 고혈압
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="간질환"> 간질환 (간경화·간염)
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="신장질환"> 신장질환
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="척추·관절질환"> 척추·관절질환
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="정신건강 질환"> 정신건강 질환
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="기타 질환"> 기타 질환
            </label>
          </div>
          <div class="form-grid" style="margin-top:4px">
            <div class="form-group">
              <label>최근 5년 입원 횟수</label>
              <select id="cf-hospitalization">
                <option value="">없음</option>
                <option value="1회">1회</option>
                <option value="2회">2회</option>
                <option value="3회 이상">3회 이상</option>
              </select>
            </div>
            <div class="form-group">
              <label>현재 복용 약물 (선택)</label>
              <input type="text" id="cf-medications" placeholder="예: 혈압약, 당뇨약">
            </div>
          </div>
        </div>
      </div>

      <button class="gen-btn" id="gen-btn" onclick="generatePortfolio()">
        💳 신용점수 반영 포트폴리오 생성
      </button>
    </div>

    <!-- 결과 -->
    <div class="credit-result" id="credit-result" style="display:none">
      <div class="credit-result-header">
        <span style="font-size:16px">📋</span>
        <span style="font-weight:700;font-size:14px">맞춤형 보험 포트폴리오</span>
        <span class="score-pill" id="result-score-pill"></span>
        <button onclick="document.getElementById('credit-result').style.display='none'"
          style="margin-left:auto;background:none;border:none;cursor:pointer;color:#94a3b8;font-size:18px">✕</button>
      </div>
      <!-- 종합 적합도 점수 카드 (JS로 채움) -->
      <div id="composite-score-card-area"></div>
      <div id="policy-loan-card-area"></div>
      <!-- 5축 레이더 차트 -->
      <div class="radar-chart-card" id="radar-chart-card" style="display:none">
        <div class="radar-chart-title">
          <span style="font-size:16px">📡</span>
          <span>신용 다차원 평가 레이더</span>
          <span class="inno-zone-badge" style="margin-left:auto">이노베이션 존</span>
        </div>
        <canvas id="credit-radar-canvas" width="280" height="280"></canvas>
      </div>
      <!-- 보험료 납입이력 신용 가점 안내 -->
      <div class="premium-hist-card" id="premium-hist-card" style="display:none">
        <div class="premium-hist-title">보험료 납입이력 신용 가점 안내</div>
        <div id="premium-hist-body"></div>
        <div style="font-size:10.5px;color:#15803d;margin-top:6px">
          ※ 보험료 정기 납부 이력은 CB사 대안 신용 데이터로 활용되어 신용점수 가산점 부여 가능
        </div>
      </div>
      <!-- 신용점수 개선 시뮬레이터 -->
      <div id="score-sim-area"></div>
      <div class="credit-result-body" id="credit-result-body"></div>
    </div>

  </div>
</div>

<!-- Tab: 건강위험 포트폴리오 -->
<div class="tab-panel" id="tab-health">
  <div class="health-panel">

    <!-- 소개 + 사용 방법 -->
    <div class="credit-guide">
      <h3>🏥 건강검진 기반 보험 위험 분석 (CareLink)</h3>
      <p style="font-size:12.5px;color:#475569;margin-bottom:4px;">건강검진 수치를 입력하면 만성질환(당뇨·대사) 위험도를 예측하고, 맞춤 보험 유형과 보험다모아 실제 상품을 추천합니다.</p>
      <p style="font-size:11.5px;color:#94a3b8;margin-bottom:10px">나이·성별만 입력해도 동작하며, 수치가 많을수록 더 정확합니다 (AUC ≈ 0.78).</p>

      <!-- 사용 방법 아코디언 -->
      <div style="border-top:1px solid #e2e8f0;padding-top:10px">
        <div style="display:flex;align-items:center;justify-content:space-between;cursor:pointer"
          onclick="toggleSection('hr-howto')">
          <span style="font-size:12.5px;font-weight:700;color:#047857">📖 사용 방법 보기</span>
          <span class="extra-section-toggle" id="toggle-hr-howto" style="font-size:12px;color:#94a3b8">▼</span>
        </div>
        <div class="extra-section-body" id="body-hr-howto">
          <div style="margin-top:12px;display:flex;flex-direction:column;gap:10px">

            <div style="display:flex;gap:12px;align-items:flex-start">
              <div style="flex-shrink:0;width:26px;height:26px;border-radius:50%;background:#dcfce7;color:#15803d;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center">1</div>
              <div>
                <div style="font-size:12.5px;font-weight:700;color:#1e293b;margin-bottom:2px">건강검진 데이터 가져오기 (선택)</div>
                <div style="font-size:12px;color:#475569">「📂 건강검진 데이터 가져오기」를 클릭해 펼친 뒤,<br>
                  <strong>PDF 업로드</strong>(국민건강보험공단·나의건강기록 앱에서 저장한 PDF)하거나<br>
                  결과지 텍스트를 <strong>붙여넣기</strong>하면 수치가 자동 입력됩니다.</div>
              </div>
            </div>

            <div style="display:flex;gap:12px;align-items:flex-start">
              <div style="flex-shrink:0;width:26px;height:26px;border-radius:50%;background:#dcfce7;color:#15803d;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center">2</div>
              <div>
                <div style="font-size:12.5px;font-weight:700;color:#1e293b;margin-bottom:2px">수치 입력</div>
                <div style="font-size:12px;color:#475569"><strong>나이·성별</strong>은 필수, 나머지는 선택입니다.<br>
                  키·몸무게 입력 시 BMI가 자동 계산됩니다.</div>
              </div>
            </div>

            <div style="display:flex;gap:12px;align-items:flex-start">
              <div style="flex-shrink:0;width:26px;height:26px;border-radius:50%;background:#dcfce7;color:#15803d;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center">3</div>
              <div>
                <div style="font-size:12.5px;font-weight:700;color:#1e293b;margin-bottom:2px">「위험 분석」 클릭</div>
                <div style="font-size:12px;color:#475569">당뇨·대사 <strong>위험 점수(게이지)</strong>, 임상 플래그(비만·고혈압 등),<br>
                  위험에 맞는 <strong>보험다모아 실제 상품</strong>이 표시됩니다.</div>
              </div>
            </div>

            <div style="display:flex;gap:12px;align-items:flex-start">
              <div style="flex-shrink:0;width:26px;height:26px;border-radius:50%;background:#dcfce7;color:#15803d;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center">4</div>
              <div>
                <div style="font-size:12.5px;font-weight:700;color:#1e293b;margin-bottom:2px">「AI 맞춤 추천 받기」 클릭</div>
                <div style="font-size:12px;color:#475569">GPT-4o가 위험도를 해석하고 <strong>우선순위별 보험 포트폴리오</strong>를 표 형식으로 추천합니다.<br>
                  표 오른쪽 <strong>「가입하기」버튼</strong>으로 보험사 사이트로 바로 이동 가능합니다.</div>
              </div>
            </div>

            <div style="background:#f0fdf4;border-radius:8px;padding:9px 12px;font-size:11.5px;color:#166534;margin-top:2px">
              ⚠️ 이 분석은 <strong>예방·보장 강화 목적</strong>의 참고 정보이며, 의학적 진단이 아닙니다.<br>
              보험 가입 심사·거절의 근거로 사용되지 않습니다.
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 건강검진 데이터 가져오기 -->
    <div class="health-form-card">
      <div style="display:flex;align-items:center;justify-content:space-between;cursor:pointer"
        onclick="toggleSection('health-source')">
        <h3 style="margin:0">📂 건강검진 데이터 가져오기</h3>
        <span class="extra-section-toggle" id="toggle-health-source">▼</span>
      </div>
      <div class="extra-section-body" id="body-health-source">
        <p style="font-size:12.5px;color:#475569;margin-bottom:10px">
          국민건강보험공단 앱·사이트에서 건강검진 결과를 확인하거나,
          결과 통보서 내용을 붙여넣으면 수치를 자동으로 입력해 드립니다.
        </p>
        <!-- 탭 가이드 -->
        <div class="health-guide-tabs">
          <button class="hg-tab active" onclick="hrGuideTab(this,'hg-web')">🖥️ PC 웹사이트</button>
          <button class="hg-tab" onclick="hrGuideTab(this,'hg-mhw')">📲 나의 건강기록 앱</button>
        </div>

        <!-- 방법 1: nhis.or.kr PC -->
        <div class="hg-pane active" id="hg-web">
          <ul class="hg-steps">
            <li class="hg-step"><div class="hg-num">1</div><div><strong>nhis.or.kr</strong> 접속</div></li>
            <li class="hg-step"><div class="hg-num">2</div><div>상단 메뉴 <strong>"건강iN"</strong> 클릭</div></li>
            <li class="hg-step"><div class="hg-num">3</div><div>공동인증서 / 간편인증(카카오·네이버·PASS)으로 <strong>로그인</strong></div></li>
            <li class="hg-step"><div class="hg-num">4</div><div>나의건강관리 → 건강검진 → <strong>건강검진 결과 조회</strong></div></li>
            <li class="hg-step"><div class="hg-num">5</div><div>연도 선택 후 검진 결과 확인</div></li>
            <li class="hg-step"><div class="hg-num">6</div><div><strong>"결과 인쇄"</strong> 버튼 클릭 → 인쇄 화면에서 <strong>PDF로 저장</strong> → 아래 PDF 업로드 이용</div></li>
          </ul>
          <a class="hg-link" href="https://www.nhis.or.kr" target="_blank" rel="noopener">nhis.or.kr 바로가기 →</a>
        </div>

<!-- 방법 3: 나의 건강기록 앱 (마이헬스웨이) -->
        <div class="hg-pane" id="hg-mhw">
          <div style="background:#fefce8;border:1px solid #fde68a;border-radius:8px;padding:10px 12px;font-size:12px;color:#92400e;margin-bottom:12px">
            ⚠️ myhealthway.go.kr PC 웹은 <strong>앱 다운로드 안내 페이지</strong>만 제공합니다.<br>
            건강검진 결과는 <strong>나의 건강기록</strong> 모바일 앱에서 확인하세요.
          </div>
          <ul class="hg-steps">
            <li class="hg-step"><div class="hg-num">1</div><div>스마트폰에서 <strong>「나의 건강기록」</strong> 앱 설치<br>
              <span style="font-size:11px;color:#64748b">App Store / Google Play에서 검색</span></div></li>
            <li class="hg-step"><div class="hg-num">2</div><div>공동인증서 또는 간편인증(카카오·네이버·PASS)으로 <strong>로그인</strong></div></li>
            <li class="hg-step"><div class="hg-num">3</div><div>하단 메뉴 → <strong>건강검진</strong> → 검진 연도 선택</div></li>
            <li class="hg-step"><div class="hg-num">4</div><div>결과 화면에서 <strong>공유 버튼 → PDF 저장</strong> → 아래 PDF 업로드 이용</div></li>
          </ul>
          <a class="hg-link" href="https://www.myhealthway.go.kr" target="_blank" rel="noopener">myhealthway.go.kr (앱 다운로드 안내) →</a>
        </div>
        <!-- PDF 업로드 -->
        <div style="margin-top:14px">
          <label style="font-size:12px;font-weight:600;color:#475569;display:block;margin-bottom:6px">
            📄 건강검진결과통보서 PDF 업로드
          </label>
          <div class="pdf-drop-zone" id="hr-pdf-drop"
            onclick="document.getElementById('hr-pdf-input').click()"
            ondragover="hrDragOver(event)" ondragleave="hrDragLeave(event)"
            ondrop="hrDropFile(event)">
            <div class="pdf-drop-icon">📄</div>
            <div class="pdf-drop-text">클릭하거나 PDF를 여기에 드래그</div>
            <div class="pdf-drop-sub">건강검진결과통보서 PDF · 최대 10MB</div>
          </div>
          <input type="file" id="hr-pdf-input" accept=".pdf" style="display:none"
            onchange="hrUploadPDF(this.files[0])">
          <div id="hr-pdf-status" style="font-size:11.5px;margin-top:6px"></div>
        </div>

        <div class="pdf-or-divider">또는 텍스트 직접 붙여넣기</div>

        <div>
          <label style="font-size:12px;font-weight:600;color:#475569;display:block;margin-bottom:6px">
            📋 건강검진결과통보서 붙여넣기 → 자동 입력
          </label>
          <textarea class="paste-area" id="hr-paste-area"
            placeholder="건강검진 결과 내용을 여기에 붙여넣으세요.
예) 신장 172cm / 체중 78kg / 허리둘레 88cm
    수축기혈압 130 / 이완기혈압 85
    총콜레스테롤 210 / 중성지방 160 / HDL 48 / LDL 135
    AST(GOT) 28 / ALT(GPT) 32 / GGT(감마GTP) 45
    흡연: 비흡연 / 음주: 음주"></textarea>
          <button class="parse-btn" id="hr-parse-btn" onclick="hrParseHealthData()">
            ✨ 자동 입력
          </button>
          <div id="hr-parse-status" style="font-size:11.5px;margin-top:6px"></div>
        </div>
      </div>
    </div>

    <!-- 입력 폼 -->
    <div class="health-form-card">
      <h3>✏️ 건강검진 수치 입력</h3>

      <div class="health-section-label">👤 기본 정보 <span style="font-weight:400;color:#94a3b8;font-size:11px">(필수)</span></div>
      <div class="form-grid">
        <div class="form-group">
          <label>나이</label>
          <input type="number" id="hr-age" placeholder="예: 48" min="20" max="80">
        </div>
        <div class="form-group">
          <label>성별</label>
          <select id="hr-gender">
            <option value="남">남성</option>
            <option value="여">여성</option>
          </select>
        </div>
      </div>

      <div class="health-section-label">⚖️ 신체계측 <span style="font-weight:400;color:#94a3b8;font-size:11px">(선택)</span></div>
      <div class="form-grid">
        <div class="form-group">
          <label>키 (cm)</label>
          <input type="number" id="hr-height" placeholder="예: 172" min="100" max="220" oninput="hrCalcBMI()">
        </div>
        <div class="form-group">
          <label>몸무게 (kg)</label>
          <input type="number" id="hr-weight-val" placeholder="예: 78" min="30" max="200" oninput="hrCalcBMI()">
        </div>
        <div class="form-group">
          <label>허리둘레 (cm)</label>
          <input type="number" id="hr-waist" placeholder="예: 88" min="50" max="160">
        </div>
        <div class="form-group">
          <label>BMI <span style="font-weight:400;color:#94a3b8">(자동)</span></label>
          <input type="text" id="hr-bmi-disp" placeholder="키·몸무게 입력 후 자동" readonly
            style="background:#f8fafc;color:#64748b;cursor:default">
        </div>
      </div>

      <div class="health-section-label">💓 혈압 <span style="font-weight:400;color:#94a3b8;font-size:11px">(선택)</span></div>
      <div class="form-grid">
        <div class="form-group">
          <label>수축기혈압 SBP (mmHg)</label>
          <input type="number" id="hr-sbp" placeholder="예: 130" min="70" max="250">
        </div>
        <div class="form-group">
          <label>이완기혈압 DBP (mmHg)</label>
          <input type="number" id="hr-dbp" placeholder="예: 85" min="40" max="150">
        </div>
      </div>

      <div class="health-section-label">🩸 혈중 지질 <span style="font-weight:400;color:#94a3b8;font-size:11px">(선택)</span></div>
      <div class="form-grid">
        <div class="form-group">
          <label>총콜레스테롤 (mg/dL)</label>
          <input type="number" id="hr-tc" placeholder="예: 200" min="50" max="500">
        </div>
        <div class="form-group">
          <label>중성지방 TG (mg/dL)</label>
          <input type="number" id="hr-tg" placeholder="예: 150" min="20" max="2000">
        </div>
        <div class="form-group">
          <label>HDL 콜레스테롤 (mg/dL)</label>
          <input type="number" id="hr-hdl" placeholder="예: 55" min="10" max="150">
        </div>
        <div class="form-group">
          <label>LDL 콜레스테롤 (mg/dL)</label>
          <input type="number" id="hr-ldl" placeholder="예: 130" min="20" max="400">
        </div>
      </div>

      <div class="health-section-label">🫁 간 수치 <span style="font-weight:400;color:#94a3b8;font-size:11px">(선택)</span></div>
      <div class="form-grid">
        <div class="form-group">
          <label>AST (U/L)</label>
          <input type="number" id="hr-ast" placeholder="예: 28" min="5" max="1000">
        </div>
        <div class="form-group">
          <label>ALT (U/L)</label>
          <input type="number" id="hr-alt" placeholder="예: 25" min="5" max="1000">
        </div>
        <div class="form-group">
          <label>GGT (U/L)</label>
          <input type="number" id="hr-ggt" placeholder="예: 30" min="5" max="1000">
        </div>
      </div>

      <div class="health-section-label">🚬 생활습관 <span style="font-weight:400;color:#94a3b8;font-size:11px">(선택)</span></div>
      <div class="form-grid">
        <div class="form-group">
          <label>흡연 여부</label>
          <select id="hr-smoke">
            <option value="">선택 안함</option>
            <option value="1">비흡연</option>
            <option value="2">과거 흡연</option>
            <option value="3">현재 흡연</option>
          </select>
        </div>
        <div class="form-group">
          <label>음주 여부</label>
          <select id="hr-drink">
            <option value="">선택 안함</option>
            <option value="0">비음주</option>
            <option value="1">음주</option>
          </select>
        </div>
      </div>

      <div class="health-section-label">💰 보험료 분위 (BFC) <span style="font-weight:400;color:#94a3b8;font-size:11px">(선택 — 이노베이션 존 BFC 데이터 연계)</span></div>
      <div class="form-grid">
        <div class="form-group" style="grid-column:1/-1">
          <label>소득/보험료 분위 <span style="font-weight:400;font-size:11px;color:#64748b">— 납부 가능 보험료 범위 자동 산정</span></label>
          <select id="hr-bfc-tier">
            <option value="">선택 안함</option>
            <option value="1">1분위 — 하위 10% (월 0~2만원)</option>
            <option value="2">2분위 — 10~20% (월 2~4만원)</option>
            <option value="3">3분위 — 20~30% (월 4~7만원)</option>
            <option value="4">4분위 — 30~40% (월 7~10만원)</option>
            <option value="5">5분위 — 40~50% (월 10~13만원)</option>
            <option value="6">6분위 — 50~60% (월 13~17만원)</option>
            <option value="7">7분위 — 60~70% (월 17~22만원)</option>
            <option value="8">8분위 — 70~80% (월 22~30만원)</option>
            <option value="9">9분위 — 80~90% (월 30~45만원)</option>
            <option value="10">10분위 — 상위 10% (월 45만원+)</option>
          </select>
        </div>
      </div>

      <button class="health-gen-btn" id="health-gen-btn" onclick="generateHealthPortfolio()">
        🏥 건강위험 분석 및 보험 추천
      </button>
    </div>

    <!-- 결과 영역 -->
    <div id="health-result-area" style="display:none">

      <!-- 위험도 게이지 -->
      <div class="risk-gauge-card">
        <div class="risk-gauge-title">📊 만성질환(당뇨·대사) 위험도</div>
        <div class="risk-bar-track">
          <div class="risk-bar-pointer" id="hr-risk-pointer" style="left:0%"></div>
        </div>
        <div class="risk-bar-labels">
          <span>저위험 (0%)</span><span>중간위험 (15%)</span><span>고위험 (30%+)</span>
        </div>
        <div>
          <span class="risk-score-num" id="hr-score-num"></span>
          <span class="risk-band-chip" id="hr-band-chip"></span>
        </div>
        <div class="hr-model-note" id="hr-model-note"></div>
        <div class="flag-chips" id="hr-flag-chips"></div>
      </div>

      <!-- 추천 보험 유형 -->
      <div class="risk-gauge-card">
        <div class="risk-gauge-title">🛡️ 맞춤 보험 유형 추천</div>
        <div class="ins-type-tags" id="hr-ins-type-tags"></div>
        <div class="hr-guidance" id="hr-guidance"></div>
      </div>

      <!-- 보험다모아 상품 -->
      <div class="risk-gauge-card">
        <div class="risk-gauge-title">📋 보험다모아 추천 상품</div>
        <div id="hr-products"></div>
      </div>

      <!-- 이노베이션 존: 암 위험 분석 (RGST/DEATH) -->
      <div class="risk-gauge-card" id="hr-cancer-card" style="display:none">
        <div class="risk-gauge-title">🔬 암 위험 분석
          <span class="inno-zone-badge">🏛️ 개인정보 이노베이션 존 · RGST/DEATH</span>
        </div>
        <div class="cancer-risk-summary">
          <div id="hr-cancer-ratio" style="font-size:22px;font-weight:800;color:#1e293b"></div>
          <span class="cancer-band-chip" id="hr-cancer-band"></span>
          <span id="hr-cancer-vs" style="font-size:12px;color:#64748b"></span>
        </div>
        <div id="hr-cancer-bars"></div>
        <div style="font-size:11px;color:#94a3b8;margin-top:8px" id="hr-cancer-source"></div>
      </div>

      <!-- 이노베이션 존: BFC 보험료 분위 -->
      <div class="risk-gauge-card" id="hr-bfc-card" style="display:none">
        <div class="risk-gauge-title">💰 납부 가능 보험료 범위
          <span class="inno-zone-badge">🏛️ 개인정보 이노베이션 존 · BFC</span>
        </div>
        <div id="hr-bfc-body"></div>
      </div>

      <!-- Health-Credit 가산점 자동 연산 -->
      <div class="hr-hc-bonus-card" id="hr-hc-bonus-card" style="display:none">
        <div class="hr-hc-bonus-title">
          <span style="font-size:16px">💳</span>
          <span>Health-Credit 신용 가산점 자동 연산</span>
          <span class="inno-zone-badge" style="margin-left:auto">이노베이션 존 · G1E/BFC</span>
        </div>
        <div id="hr-hc-bonus-body"></div>
      </div>

      <!-- AI 맞춤 추천 -->
      <div class="ai-rec-card">
        <div class="ai-rec-card-title">
          <span style="font-size:20px">🧠</span>
          <span>AI 맞춤 보험 추천 (GPT-4o)</span>
        </div>
        <button class="ai-rec-btn" id="hr-ai-btn" onclick="hrGetAiRec()">
          ✨ AI 맞춤 추천 받기
        </button>
        <div class="ai-rec-body" id="hr-ai-body" style="display:none"></div>
      </div>

      <!-- 면책 고지 -->
      <div class="health-disclaimer">
        ⚠️ 예측 결과는 <strong>예방·보장 강화 목적</strong>이며, 보험 가입 거절·불이익·차별의 근거로 사용하지 않습니다.<br>
        본 예측은 선별용 위험도이며 <strong>의학적 진단이 아닙니다.</strong> 정확한 진단은 의료기관에서 받으세요.
      </div>

    </div>

  </div>
</div>

<!-- Tab: 대회 데모 ─────────────────────────────────────────── -->
<div class="tab-panel" id="tab-demo">
  <div class="demo-panel">

    <div class="demo-header">
      <div class="demo-title">개인정보 이노베이션 존 × 보험·금융 혁신 데모</div>
      <div class="demo-subtitle">
        국립암센터 RGST·DEATH·G1E + 광주TP CDW/DICOM + BFC 보험료분위 + CB 신용DB<br>
        3대 데이터 결합 기반 <strong>16가지 혁신 시나리오</strong> 실시간 시연
      </div>
    </div>

    <!-- 보험 영역 -->
    <div class="demo-section-title">보험 영역 — 정밀 언더라이팅 &amp; 요율 합리화</div>
    <div class="demo-grid">

      <div class="demo-card" onclick="demoSend(1)">
        <div class="demo-card-num">시나리오 1</div>
        <div class="demo-card-title">암 완치자 인수 심사</div>
        <div class="demo-card-persona">박*준 · 45세 남성 · 위암 2기 완치 3년</div>
        <div class="demo-card-desc">RGST(암등록 DB) 재발률 → 조건부 표준체 전환 + 보험료 할인</div>
        <div class="demo-card-data">RGST(암등록 261만건) · DEATH(사망DB) · G1E(건강검진 DB)</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 일률 거절
          <span class="after-tag">After</span> 정밀 심사 → 조건부 승인
        </div>
      </div>

      <div class="demo-card" onclick="demoSend(2)">
        <div class="demo-card-num">시나리오 2</div>
        <div class="demo-card-title">AI 저위험군 보험료 할인</div>
        <div class="demo-card-persona">이*현 · 38세 여성 · 5년 연속 검진 정상</div>
        <div class="demo-card-desc">G1E(건강검진 DB) 연속 검진 + DICOM(의료영상 포맷) 정밀 분류 → 최대 30% 보험료 할인</div>
        <div class="demo-card-data">G1E(건강검진 1657만건) · DICOM(의료영상) · 바이탈(활력징후) DB</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 나이 기준 일률 보험료
          <span class="after-tag">After</span> 건강 점수 기반 30% 할인
        </div>
      </div>

      <div class="demo-card" onclick="demoSend(3)">
        <div class="demo-card-num">시나리오 3</div>
        <div class="demo-card-title">미세 영상 소견자 노-할증</div>
        <div class="demo-card-persona">김*영 · 52세 남성 · 폐 소결절 6mm</div>
        <div class="demo-card-desc">DICOM(의료영상) AI 판독 → 임상 무의미 소견 구분 → 부당 할증 없음</div>
        <div class="demo-card-data">DICOM(의료영상 포맷) · T400(소화기계 상병코드) · RGST(암등록 DB)</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 소견 이유로 보험료 30% 할증
          <span class="after-tag">After</span> AI 판독 → 노-할증 표준 체
        </div>
      </div>

      <div class="demo-card" onclick="demoSend(4)">
        <div class="demo-card-num">시나리오 4</div>
        <div class="demo-card-title">동적 보험료 캐시백</div>
        <div class="demo-card-persona">최*민 · 41세 여성 · 1년간 건강 점수 25% 개선</div>
        <div class="demo-card-desc">라이프로그(웨어러블 건강 활동 기록) 개선도 → 연간 보험료 캐시백 최대 15%</div>
        <div class="demo-card-data">라이프로그(건강 활동 기록) · 바이탈(활력징후) DB · G1E(건강검진 DB)</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 고정 보험료
          <span class="after-tag">After</span> 건강 개선 → 캐시백 지급
        </div>
      </div>

      <div class="demo-card" onclick="demoSend(5)">
        <div class="demo-card-num">시나리오 5</div>
        <div class="demo-card-title">맞춤형 유병자 요율</div>
        <div class="demo-card-persona">정*호 · 57세 남성 · 당뇨 · 치료 반응 우수</div>
        <div class="demo-card-desc">T200~T530(대사·내분비 질환 상병코드) + G1E(건강검진 DB) 치료 반응 → 개인 맞춤 보험료 (일률 할증 -30%)</div>
        <div class="demo-card-data">T200~T530(상병코드) · G1E(건강검진 DB) · BFC(보험료분위: 소득지표)</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 유병자 일률 30% 할증
          <span class="after-tag">After</span> 치료 반응 우수 → 맞춤 요율 -20%
        </div>
      </div>

      <div class="demo-card" onclick="demoSend(6)">
        <div class="demo-card-num">시나리오 6</div>
        <div class="demo-card-title">건강체 특별약관 최대 할인</div>
        <div class="demo-card-persona">강*원 · 43세 남성 · 5년 연속 건강체 · 비흡연 · BMI 21</div>
        <div class="demo-card-desc">G1E(건강검진 DB) 연속 검진 + 바이탈(활력징후) 전 항목 정상 → 건강체 1급 판정 → 보험료 최대 30% 할인</div>
        <div class="demo-card-data">G1E(건강검진 1657만건) · 바이탈(활력징후) DB · 라이프로그 · BFC(보험료분위)</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 표준체 기준 월 12만원
          <span class="after-tag">After</span> 건강체 1급 특약 → 월 8.4만원 (-30%)
        </div>
      </div>

      <div class="demo-card" onclick="demoSend(7)">
        <div class="demo-card-num">시나리오 7</div>
        <div class="demo-card-title">위 용종 절제 후 보험 가입 가능</div>
        <div class="demo-card-persona">홍*종 · 50세 남성 · 2년 전 위 선종 내시경 절제 · 추적 내시경 정상</div>
        <div class="demo-card-desc">병리 DB(양성 선종: 암세포 없음) + 추적 내시경 정상 → 재발 위험 1.5% → 5년 제한 없이 표준체 승인</div>
        <div class="demo-card-data">T400(소화기계 상병코드) · DICOM(의료영상) · 병리 DB · RGST(암등록 DB)</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 수술 이력 → 5년 보험 가입 불가
          <span class="after-tag">After</span> 의료 데이터 분석 → 즉시 표준체 승인
        </div>
      </div>

    </div>

    <!-- 금융 영역 -->
    <div class="demo-section-title">금융 영역 — 포용 금융 &amp; 대안 신용평가</div>
    <div class="demo-grid">

      <div class="demo-card" onclick="demoSend(8)">
        <div class="demo-card-num">시나리오 8</div>
        <div class="demo-card-title">씬파일러 Health-Credit 신용평가</div>
        <div class="demo-card-persona">이*진 · 29세 여성 · 금융 이력 부족 · 신용점수 680점</div>
        <div class="demo-card-desc">G1E(건강검진 DB) 성실도 + 바이탈(활력징후) 안정도 → 신용 +85점 → 1금융권 금리 1.8%p 인하</div>
        <div class="demo-card-data">G1E(건강검진 DB) · 바이탈(활력징후) DB · BFC(보험료분위) · CB(신용조회기관)</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 씬파일러 → 고금리 대출
          <span class="after-tag">After</span> Health-Credit → 1금융권 진입
        </div>
      </div>

      <div class="demo-card" onclick="demoSend(9)">
        <div class="demo-card-num">시나리오 9</div>
        <div class="demo-card-title">소상공인 건강 지속가능성 대출</div>
        <div class="demo-card-persona">오*석 · 48세 남성 · 8년 자영업 · 당뇨 치료 우수</div>
        <div class="demo-card-desc">CDW(임상 데이터 웨어하우스) + RGST(암등록 DB) 영속성 예측 → 대출 한도 3,000만원 증액 + 금리 0.8%p 우대</div>
        <div class="demo-card-data">CDW(임상 데이터 웨어하우스) · RGST(암등록 DB) · CB(신용조회기관) 매출 DB</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 담보·매출 기준만 → 한도 부족
          <span class="after-tag">After</span> 건강 지속가능성 → 한도 증액
        </div>
      </div>

      <div class="demo-card" onclick="demoSend(10)">
        <div class="demo-card-num">시나리오 10</div>
        <div class="demo-card-title">유병자·고령층 렌탈 금융 승인</div>
        <div class="demo-card-persona">윤*숙 · 68세 여성 · 위암 1기 완치 5년</div>
        <div class="demo-card-desc">환자 건강지수(HLI) + DEATH(사망 DB) 단기 위험 분석 → 병력 차별 없이 렌탈 승인</div>
        <div class="demo-card-data">환자 건강지수(HLI) DB · DEATH(사망 DB) · RGST(암등록 DB)</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 병력 이유 → 렌탈 거절
          <span class="after-tag">After</span> 단기 위험 낮음 → 정상 승인
        </div>
      </div>

      <div class="demo-card" onclick="demoSend(11)">
        <div class="demo-card-num">시나리오 11</div>
        <div class="demo-card-title">건강체 건강담보대출 승인</div>
        <div class="demo-card-persona">서*원 · 46세 여성 · 건강체 · DSR(총부채상환비율) 52% 초과 → 은행 대출 거절</div>
        <div class="demo-card-desc">G1E(건강검진 DB) 4년 연속 정상 + 바이탈(활력징후) 안정도 상 → HAS(건강자산점수) 87점(A+) → 건강담보대출 승인</div>
        <div class="demo-card-data">G1E(건강검진 DB) · 바이탈(활력징후) DB · BFC(보험료분위) · 담보대출 DB</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> DSR(총부채상환비율) 초과 → 전 금융기관 거절
          <span class="after-tag">After</span> 건강 자산 담보 → 5,000만원 / 연 3.2% 승인
        </div>
      </div>

      <div class="demo-card" onclick="demoSend(12)">
        <div class="demo-card-num">시나리오 12</div>
        <div class="demo-card-title">신(新) 건강담보대출 — 막힌 대출 해결</div>
        <div class="demo-card-persona">나*출 · 52세 남성 · DSR(총부채상환비율) 58%·LTV(담보인정비율) 82% 이중 초과 · 건강검진 3년 연속 정상</div>
        <div class="demo-card-desc">G1E(건강검진)+바이탈(활력징후)+라이프로그 3종 결합 HAS(건강자산점수) → 건강 자산 담보 신상품 승인</div>
        <div class="demo-card-data">G1E(건강검진 DB) · 바이탈(활력징후) DB · 라이프로그(건강활동 기록) · BFC(보험료분위)</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> DSR·LTV 이중 초과 → 대출 완전 불가
          <span class="after-tag">After</span> HAS(건강자산점수) → 5,000만원 / 연 3.2% 신상품
        </div>
      </div>

    </div>

    <!-- 신용 역선택 방지 영역 -->
    <div class="demo-section-title">신용 역선택 방지 — 신용+건강 교차 언더라이팅</div>
    <div class="demo-grid">

      <div class="demo-card" onclick="demoSend(13)">
        <div class="demo-card-num">시나리오 13 <span class="db-new-badge">NEW</span></div>
        <div class="demo-card-title">신용+건강 교차 역선택 탐지</div>
        <div class="demo-card-persona">강*민 · 42세 남성 · 신용점수 6개월 -120점 · 고액 보험 동시 신청</div>
        <div class="demo-card-desc">신용 급락 + 검진 기피 + 복수 보험사 동시 신청 → AASI(역선택방지지수) 산출 → 정밀 언더라이팅(인수심사)</div>
        <div class="demo-card-data">CB(신용조회기관) 신용 DB · G1E(건강검진 이력) · 보험사 청구 DB</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 신용·건강 별도 관리 → 역선택 미탐지
          <span class="after-tag">After</span> AASI(역선택방지지수) 교차 분석 → 고위험 즉시 탐지
        </div>
      </div>

      <div class="demo-card" onclick="demoSend(14)">
        <div class="demo-card-num">시나리오 14 <span class="db-new-badge">NEW</span></div>
        <div class="demo-card-title">씬파일러 역선택 방지 & 포용 심사</div>
        <div class="demo-card-persona">윤*아 · 28세 여성 · CB 이력 없음 · 건강검진 미수검 · 고액 첫 신청</div>
        <div class="demo-card-desc">씬파일러(신용·건강 이력 없는 사람) + 검진 기피 + 고액 보험 첫 신청 → G1E(건강검진) 수검 요구 + 포용 경로 제시</div>
        <div class="demo-card-data">G1E(건강검진 이력) · 바이탈(활력징후) DB · CB(신용조회기관) 신용 DB</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 씬파일러 일률 거절 or 무방비 승인
          <span class="after-tag">After</span> 역선택 방지 + 포용금융 경로 동시 제시
        </div>
      </div>

    </div>

    <!-- 위험 관리 영역 -->
    <div class="demo-section-title">위험 관리 영역 — 사전 케어 &amp; 부실률 차단</div>
    <div class="demo-grid">

      <div class="demo-card" onclick="demoSend(15)">
        <div class="demo-card-num">시나리오 15</div>
        <div class="demo-card-title">미시 징후 사전 케어 → 암 중증화 차단</div>
        <div class="demo-card-persona">박*호 · 52세 남성 · 위 미란 소견 · 2년 내 진행 위험 42%</div>
        <div class="demo-card-desc">DICOM(의료영상) + T400(소화기계 상병코드) AI 조기 감지 → 내시경 절제술 → 고액 보험금 8,000만원 선제 차단</div>
        <div class="demo-card-data">DICOM(의료영상 포맷) · T400(소화기계 상병코드) · 보험사 지급 DB</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 방치 → 암 3기 진행 → 보험금 지급
          <span class="after-tag">After</span> 사전 시술 → 완치 → 8,000만원 절감
        </div>
      </div>

      <div class="demo-card" onclick="demoSend(16)">
        <div class="demo-card-num">시나리오 16</div>
        <div class="demo-card-title">중증 질환 전환 예측 → 부실률 차단</div>
        <div class="demo-card-persona">한*철 · 55세 남성 · 대출 2억 · SOFA(장기부전 중증도 점수) 2.0 · 중증 위험 38%</div>
        <div class="demo-card-desc">CDW(임상 데이터) SOFA(장기부전 점수) + RGST(암등록 DB) → 상환 불능 위험 조기 식별 → 상환 보험 연계 → 부실 차단</div>
        <div class="demo-card-data">SOFA(장기부전 중증도 점수) DB · RGST(암등록 DB) · DEATH(사망 DB) · 금융사 대출 DB</div>
        <div class="demo-card-before-after">
          <span class="before-tag">Before</span> 건강 정보 없음 → 부실 리스크 미포착
          <span class="after-tag">After</span> SOFA(장기부전 점수) 예측 → 상환 보험 연계 → 부실 차단
        </div>
      </div>

    </div>

    <!-- 데모 채팅 결과 -->
    <div id="demo-chat-area" style="display:none">
      <div class="demo-result-title">시나리오 분석 결과</div>
      <div id="demo-chat"></div>
    </div>

  </div>
</div>

<!-- ── DIOBIO 웰니스 탭 ── -->
<div class="tab-panel" id="tab-diobio">
  <div class="diobio-panel">

    <!-- Landing -->
    <div id="db-landing" class="db-landing">
      <div class="db-logo">🌿</div>
      <div class="db-brand">DIOBIO</div>
      <div class="db-tagline">
        <em>영양제부터 시작하지 않습니다.</em><br>
        생활습관·음식·운동을 먼저 보고<br>
        필요한 경우 영양제와 의료를 연결합니다.
      </div>
      <button class="db-cta-main" onclick="dbStart()">3분 건강 밸런스 체크하기 →</button>
      <div class="db-landing-cards">
        <div class="db-landing-card">
          <div class="db-landing-card-ic">💡</div>
          <div class="db-landing-card-nm">AI 건강 분석</div>
          <div class="db-landing-card-ds">6가지 밸런스 유형<br>맞춤 솔루션 제시</div>
        </div>
        <div class="db-landing-card">
          <div class="db-landing-card-ic">💉</div>
          <div class="db-landing-card-nm">GLP-1 원격 상담 <span class="db-new-badge">NEW</span></div>
          <div class="db-landing-card-ds">비만·대사 관리<br>AI 원격 의료 연결</div>
        </div>
        <div class="db-landing-card">
          <div class="db-landing-card-ic">🔬</div>
          <div class="db-landing-card-nm">검사 키트</div>
          <div class="db-landing-card-ds">모발 미네랄·영양<br>리포트 제공</div>
        </div>
        <div class="db-landing-card">
          <div class="db-landing-card-ic">🛍️</div>
          <div class="db-landing-card-nm">DIOFARM 식품</div>
          <div class="db-landing-card-ds">올리브오일·단백질<br>발효식품 구독</div>
        </div>
      </div>
    </div>

    <!-- Survey -->
    <div id="db-survey" class="db-survey" style="display:none">
      <!-- Progress -->
      <div class="db-progress">
        <div class="db-step-meta">
          <span id="db-step-lbl">Step 1 / 6</span>
          <span id="db-step-pct">0%</span>
        </div>
        <div class="db-pbar"><div class="db-pbar-fill" id="db-pbar-fill" style="width:0%"></div></div>
      </div>

      <!-- Step 1: 대상 -->
      <div id="db-s1">
        <div class="db-step-title">누구를 위한 체크인가요?</div>
        <div class="db-step-sub">맞춤 솔루션을 위해 대상을 알려주세요</div>
        <div class="db-opts">
          <div class="db-opt" data-g="target" data-v="female" onclick="dbPick(this)"><span class="db-opt-ic">👩</span>여성</div>
          <div class="db-opt" data-g="target" data-v="male" onclick="dbPick(this)"><span class="db-opt-ic">👨</span>남성</div>
          <div class="db-opt" data-g="target" data-v="child" onclick="dbPick(this)"><span class="db-opt-ic">👦</span>자녀</div>
          <div class="db-opt" data-g="target" data-v="parents" onclick="dbPick(this)"><span class="db-opt-ic">👴</span>부모님</div>
          <div class="db-opt" data-g="target" data-v="family" onclick="dbPick(this)"><span class="db-opt-ic">👨‍👩‍👧</span>가족 전체</div>
          <div class="db-opt" data-g="target" data-v="unknown" onclick="dbPick(this)"><span class="db-opt-ic">🤔</span>잘 모르겠음</div>
        </div>
      </div>

      <!-- Step 2: 기본 정보 -->
      <div id="db-s2" style="display:none">
        <div class="db-step-title">기본 정보를 알려주세요</div>
        <div class="db-step-sub">연령대와 생활 패턴을 선택해 주세요</div>
        <div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:10px">연령대</div>
        <div class="db-opts col3" style="margin-bottom:20px">
          <div class="db-opt" data-g="age" data-v="10s" onclick="dbPick(this)"><span class="db-opt-ic">🎒</span>10대</div>
          <div class="db-opt" data-g="age" data-v="20s" onclick="dbPick(this)"><span class="db-opt-ic">🌱</span>20대</div>
          <div class="db-opt" data-g="age" data-v="30s" onclick="dbPick(this)"><span class="db-opt-ic">💼</span>30대</div>
          <div class="db-opt" data-g="age" data-v="40s" onclick="dbPick(this)"><span class="db-opt-ic">🏃</span>40대</div>
          <div class="db-opt" data-g="age" data-v="50s" onclick="dbPick(this)"><span class="db-opt-ic">🧘</span>50대</div>
          <div class="db-opt" data-g="age" data-v="60s" onclick="dbPick(this)"><span class="db-opt-ic">🌿</span>60대+</div>
        </div>
        <div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:10px">생활 패턴</div>
        <div class="db-opts">
          <div class="db-opt" data-g="pattern" data-v="office" onclick="dbPick(this)"><span class="db-opt-ic">🏢</span>직장인</div>
          <div class="db-opt" data-g="pattern" data-v="selfemployed" onclick="dbPick(this)"><span class="db-opt-ic">🏪</span>자영업</div>
          <div class="db-opt" data-g="pattern" data-v="parent" onclick="dbPick(this)"><span class="db-opt-ic">👶</span>학부모</div>
          <div class="db-opt" data-g="pattern" data-v="student" onclick="dbPick(this)"><span class="db-opt-ic">📚</span>학생</div>
          <div class="db-opt" data-g="pattern" data-v="abroad" onclick="dbPick(this)"><span class="db-opt-ic">✈️</span>해외 거주</div>
          <div class="db-opt" data-g="pattern" data-v="other" onclick="dbPick(this)"><span class="db-opt-ic">🙂</span>기타</div>
        </div>
      </div>

      <!-- Step 3: 건강 고민 (멀티 최대 3) -->
      <div id="db-s3" style="display:none">
        <div class="db-step-title">지금 가장 신경 쓰이는<br>건강 고민은 무엇인가요?</div>
        <div class="db-step-sub">최대 3가지까지 선택할 수 있어요</div>
        <div class="db-opts col1" id="db-concern-opts">
          <div class="db-opt" data-v="tired" onclick="dbMulti(this,3)"><span class="db-opt-ic">😴</span>자도 자도 피곤해요</div>
          <div class="db-opt" data-v="skin" onclick="dbMulti(this,3)"><span class="db-opt-ic">✨</span>피부가 푸석하고 칙칙해요</div>
          <div class="db-opt" data-v="gut" onclick="dbMulti(this,3)"><span class="db-opt-ic">🤰</span>속이 더부룩하고 장이 예민해요</div>
          <div class="db-opt" data-v="hair" onclick="dbMulti(this,3)"><span class="db-opt-ic">💇</span>머리카락이 가늘어지고 빠지는 것 같아요</div>
          <div class="db-opt" data-v="sleep" onclick="dbMulti(this,3)"><span class="db-opt-ic">🌙</span>잠을 자도 개운하지 않아요</div>
          <div class="db-opt" data-v="weight" onclick="dbMulti(this,3)"><span class="db-opt-ic">⚖️</span>살이 잘 안 빠지고 자주 붓는 것 같아요</div>
          <div class="db-opt" data-v="age40" onclick="dbMulti(this,3)"><span class="db-opt-ic">🔋</span>40대 이후 몸이 예전 같지 않아요</div>
          <div class="db-opt" data-v="men" onclick="dbMulti(this,3)"><span class="db-opt-ic">💪</span>남성 활력과 체력이 걱정돼요</div>
          <div class="db-opt" data-v="kidcare" onclick="dbMulti(this,3)"><span class="db-opt-ic">🧒</span>아이의 편식·피로·집중력이 걱정돼요</div>
          <div class="db-opt" data-v="burnout" onclick="dbMulti(this,3)"><span class="db-opt-ic">🔥</span>스트레스와 번아웃이 심해요</div>
          <div class="db-opt" data-v="unknown" onclick="dbMulti(this,3)"><span class="db-opt-ic">❓</span>어떤 영양제를 먹어야 할지 모르겠어요</div>
        </div>
      </div>

      <!-- Step 4: 생활습관 -->
      <div id="db-s4" style="display:none">
        <div class="db-step-title">생활습관을 체크해 드릴게요</div>
        <div class="db-step-sub">솔직하게 답할수록 정확한 유형이 나와요</div>
        <div class="db-q">
          <div class="db-q-lbl">🍳 아침 식사를 얼마나 자주 하나요?</div>
          <div class="db-q-row">
            <div class="db-q-o" data-q="breakfast" data-v="often" onclick="dbQ(this)">거의 매일</div>
            <div class="db-q-o" data-q="breakfast" data-v="sometimes" onclick="dbQ(this)">가끔</div>
            <div class="db-q-o" data-q="breakfast" data-v="rarely" onclick="dbQ(this)">거의 안 함</div>
          </div>
        </div>
        <div class="db-q">
          <div class="db-q-lbl">🥩 단백질 식품을 충분히 먹나요?</div>
          <div class="db-q-row">
            <div class="db-q-o" data-q="protein" data-v="often" onclick="dbQ(this)">충분히</div>
            <div class="db-q-o" data-q="protein" data-v="sometimes" onclick="dbQ(this)">가끔</div>
            <div class="db-q-o" data-q="protein" data-v="rarely" onclick="dbQ(this)">거의 안 먹음</div>
          </div>
        </div>
        <div class="db-q">
          <div class="db-q-lbl">🥦 채소·과일을 자주 먹나요?</div>
          <div class="db-q-row">
            <div class="db-q-o" data-q="veg" data-v="often" onclick="dbQ(this)">자주</div>
            <div class="db-q-o" data-q="veg" data-v="sometimes" onclick="dbQ(this)">가끔</div>
            <div class="db-q-o" data-q="veg" data-v="rarely" onclick="dbQ(this)">거의 안 먹음</div>
          </div>
        </div>
        <div class="db-q">
          <div class="db-q-lbl">🍔 외식·배달 음식은 얼마나 자주 먹나요?</div>
          <div class="db-q-row">
            <div class="db-q-o" data-q="dining" data-v="rarely" onclick="dbQ(this)">주 2회 이하</div>
            <div class="db-q-o" data-q="dining" data-v="sometimes" onclick="dbQ(this)">주 3~4회</div>
            <div class="db-q-o" data-q="dining" data-v="often" onclick="dbQ(this)">거의 매일</div>
          </div>
        </div>
        <div class="db-q">
          <div class="db-q-lbl">🍩 단 음식·간식을 자주 먹나요?</div>
          <div class="db-q-row">
            <div class="db-q-o" data-q="sugar" data-v="rarely" onclick="dbQ(this)">거의 안 먹음</div>
            <div class="db-q-o" data-q="sugar" data-v="sometimes" onclick="dbQ(this)">가끔</div>
            <div class="db-q-o" data-q="sugar" data-v="often" onclick="dbQ(this)">자주</div>
          </div>
        </div>
        <div class="db-q">
          <div class="db-q-lbl">😴 평균 수면 시간은 어느 정도인가요?</div>
          <div class="db-q-row">
            <div class="db-q-o" data-q="sleep" data-v="good" onclick="dbQ(this)">7시간 이상</div>
            <div class="db-q-o" data-q="sleep" data-v="less6" onclick="dbQ(this)">5~6시간</div>
            <div class="db-q-o" data-q="sleep" data-v="less5" onclick="dbQ(this)">5시간 미만</div>
          </div>
        </div>
        <div class="db-q">
          <div class="db-q-lbl">🏋️ 운동은 주 몇 회 하나요?</div>
          <div class="db-q-row">
            <div class="db-q-o" data-q="exercise" data-v="often" onclick="dbQ(this)">주 3회 이상</div>
            <div class="db-q-o" data-q="exercise" data-v="sometimes" onclick="dbQ(this)">주 1~2회</div>
            <div class="db-q-o" data-q="exercise" data-v="rarely" onclick="dbQ(this)">거의 안 함</div>
          </div>
        </div>
        <div class="db-q">
          <div class="db-q-lbl">🚶 하루 평균 걷는 시간은?</div>
          <div class="db-q-row">
            <div class="db-q-o" data-q="walk" data-v="good" onclick="dbQ(this)">30분 이상</div>
            <div class="db-q-o" data-q="walk" data-v="mid" onclick="dbQ(this)">10~30분</div>
            <div class="db-q-o" data-q="walk" data-v="rarely" onclick="dbQ(this)">10분 미만</div>
          </div>
        </div>
        <div class="db-q">
          <div class="db-q-lbl">😰 최근 스트레스 수준은?</div>
          <div class="db-q-row">
            <div class="db-q-o" data-q="stress" data-v="low" onclick="dbQ(this)">낮음</div>
            <div class="db-q-o" data-q="stress" data-v="mid" onclick="dbQ(this)">보통</div>
            <div class="db-q-o" data-q="stress" data-v="high" onclick="dbQ(this)">높음</div>
          </div>
        </div>
      </div>

      <!-- Step 5: 현재 영양제 -->
      <div id="db-s5" style="display:none">
        <div class="db-step-title">현재 복용 중인 영양제가 있나요?</div>
        <div class="db-step-sub">정확한 추천을 위해 알려주세요</div>
        <div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:10px">복용 여부</div>
        <div class="db-opts" style="margin-bottom:20px">
          <div class="db-opt" data-g="supp_yn" data-v="yes" onclick="dbPick(this);dbToggleSupp(true)"><span class="db-opt-ic">✅</span>먹고 있어요</div>
          <div class="db-opt" data-g="supp_yn" data-v="no" onclick="dbPick(this);dbToggleSupp(false)"><span class="db-opt-ic">❌</span>안 먹고 있어요</div>
        </div>
        <div id="db-supp-detail" style="display:none">
          <div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:10px">몇 가지 복용 중인가요?</div>
          <div class="db-opts col3" style="margin-bottom:20px">
            <div class="db-opt" data-g="supp_cnt" data-v="1-2" onclick="dbPick(this)"><span class="db-opt-ic">1️⃣</span>1~2가지</div>
            <div class="db-opt" data-g="supp_cnt" data-v="3-5" onclick="dbPick(this)"><span class="db-opt-ic">3️⃣</span>3~5가지</div>
            <div class="db-opt" data-g="supp_cnt" data-v="6+" onclick="dbPick(this)"><span class="db-opt-ic">➕</span>6가지 이상</div>
          </div>
          <div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:10px">불편했던 경험이 있나요?</div>
          <div class="db-opts">
            <div class="db-opt" data-g="supp_dis" data-v="no" onclick="dbPick(this)"><span class="db-opt-ic">👍</span>없어요</div>
            <div class="db-opt" data-g="supp_dis" data-v="yes" onclick="dbPick(this)"><span class="db-opt-ic">😟</span>있어요</div>
          </div>
        </div>
      </div>

      <!-- Step 6: 안전 확인 -->
      <div id="db-s6" style="display:none">
        <div class="db-step-title">안전 확인 질문</div>
        <div class="db-step-sub">해당 항목을 모두 체크해 주세요</div>
        <div class="db-safety-note">
          ⚠️ 아래 항목은 병원 상담이 먼저 필요할 수 있는지 확인하기 위한 질문입니다.
          해당되는 항목이 있다면 체크해 주세요.
        </div>
        <div id="db-safety-list">
          <label class="db-chk-item" onclick="dbChkToggle(this)">
            <input type="checkbox" value="medication"><span class="db-chk-text">현재 처방약을 복용 중이에요</span>
          </label>
          <label class="db-chk-item" onclick="dbChkToggle(this)">
            <input type="checkbox" value="pregnant"><span class="db-chk-text">임신 중이거나 수유 중이에요</span>
          </label>
          <label class="db-chk-item" onclick="dbChkToggle(this)">
            <input type="checkbox" value="allergy"><span class="db-chk-text">특정 성분 알레르기가 있어요</span>
          </label>
          <label class="db-chk-item" onclick="dbChkToggle(this)">
            <input type="checkbox" value="abnormal"><span class="db-chk-text">최근 건강검진에서 이상 소견을 받았어요</span>
          </label>
          <label class="db-chk-item" onclick="dbChkToggle(this)">
            <input type="checkbox" value="severe"><span class="db-chk-text">갑작스러운 심한 탈모·극심한 피로·지속 통증이 있어요</span>
          </label>
          <label class="db-chk-item" onclick="dbChkToggle(this)">
            <input type="checkbox" value="gut_severe"><span class="db-chk-text">혈변·심한 복통·지속 설사 또는 변비가 있어요</span>
          </label>
          <label class="db-chk-item" onclick="dbChkToggle(this)">
            <input type="checkbox" value="sleep_severe"><span class="db-chk-text">수면 문제가 일상생활에 큰 지장을 주고 있어요</span>
          </label>
        </div>
        <div style="margin-top:14px;padding:12px;background:white;border-radius:10px;font-size:11.5px;color:#6b7280;line-height:1.7">
          해당 없으면 체크하지 않고 "결과 보기"를 눌러주세요.
        </div>
      </div>

      <!-- Navigation -->
      <div class="db-nav">
        <button class="db-btn-p" id="db-btn-prev" onclick="dbPrev()" style="display:none">← 이전</button>
        <button class="db-btn-n" id="db-btn-next" onclick="dbNext()">다음 →</button>
      </div>
    </div>

    <!-- Result -->
    <div id="db-result" class="db-result" style="display:none">
      <div id="db-result-body"></div>
    </div>

  </div>
</div>

<!-- DIOBIO 모달: 검사 키트 신청 -->
<div class="db-overlay" id="db-modal-kit" onclick="dbOverlayClose(event,'db-modal-kit')">
  <div class="db-modal">
    <div class="db-modal-hd">
      <span class="db-modal-title">🔬 검사 키트 신청</span>
      <button class="db-modal-close" onclick="dbCloseModal('db-modal-kit')">✕ 닫기</button>
    </div>
    <div class="db-modal-body">
      <div class="db-form-group">
        <label class="db-form-label">검사 종류 선택</label>
        <select class="db-form-select" id="db-kit-type">
          <option value="">선택해 주세요</option>
          <option value="mineral">모발 미네랄 검사 (49,000원)</option>
          <option value="nutrition">개인 영양 리포트 (39,000원)</option>
          <option value="premium">프리미엄 종합 리포트 (89,000원)</option>
        </select>
      </div>
      <div class="db-form-group">
        <label class="db-form-label">이름</label>
        <input class="db-form-input" id="db-kit-name" type="text" placeholder="이름을 입력해 주세요">
      </div>
      <div class="db-form-group">
        <label class="db-form-label">연락처</label>
        <input class="db-form-input" id="db-kit-phone" type="tel" placeholder="010-0000-0000">
      </div>
      <div class="db-form-group">
        <label class="db-form-label">배송 주소</label>
        <input class="db-form-input" id="db-kit-addr" type="text" placeholder="주소를 입력해 주세요">
      </div>
      <button class="db-submit-btn" onclick="dbSubmitKit()">신청하기</button>
      <div style="font-size:11px;color:#9ca3af;margin-top:12px;line-height:1.6">
        검사 키트는 신청 후 2~3 영업일 내 발송됩니다.<br>결과 리포트는 카카오 또는 이메일로 안내드립니다.
      </div>
    </div>
  </div>
</div>

<!-- DIOBIO 모달: 추천 식품 -->
<div class="db-overlay" id="db-modal-food" onclick="dbOverlayClose(event,'db-modal-food')">
  <div class="db-modal">
    <div class="db-modal-hd">
      <span class="db-modal-title">🛍️ DIOFARM 추천 식품</span>
      <button class="db-modal-close" onclick="dbCloseModal('db-modal-food')">✕ 닫기</button>
    </div>
    <div class="db-modal-body">
      <div id="db-food-content"></div>
    </div>
  </div>
</div>

<div class="db-overlay" id="db-modal-travel" onclick="dbOverlayClose(event,'db-modal-travel')">
  <div class="db-modal">
    <div class="db-modal-hd">
      <span class="db-modal-title">✈️ 맞춤 웰니스 여행 추천</span>
      <button class="db-modal-close" onclick="dbCloseModal('db-modal-travel')">✕ 닫기</button>
    </div>
    <div class="db-modal-body">
      <div id="db-travel-content"></div>
    </div>
  </div>
</div>

<script>
const SESSION_ID = crypto.randomUUID();
let isLoading = false;

// 모든 링크를 새 탭으로 열기 (marked v4/v5 호환)
const renderer = new marked.Renderer();
renderer.link = function(token, legacyTitle, legacyText) {
  let href, title, text;
  if (token && typeof token === 'object' && 'href' in token) {
    // marked v5+: 첫 번째 인자가 토큰 객체
    href = token.href; title = token.title; text = token.text;
  } else {
    // marked v4: 위치 인자
    href = token; title = legacyTitle; text = legacyText;
  }
  const titleAttr = title ? ` title="${title}"` : '';
  return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`;
};
marked.setOptions({ breaks: true, gfm: true, renderer });

async function checkMode() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    updateBadge(d.effective_mode, d.forced_mode);
  } catch(e) {}
}

function updateBadge(effectiveMode, forcedMode) {
  const badge = document.getElementById('modeBadge');
  badge.classList.remove('live', 'mock');
  if (forcedMode === 'auto' || !forcedMode) {
    if (effectiveMode === 'live') {
      badge.textContent = '🟢 Live Mode (자동) ▾';
      badge.classList.add('live');
    } else {
      badge.textContent = '🔧 Mock Mode (자동) ▾';
      badge.classList.add('mock');
    }
  } else if (forcedMode === 'live') {
    badge.textContent = '🟢 Live Mode ▾';
    badge.classList.add('live');
  } else {
    badge.textContent = '🔧 Mock Mode ▾';
    badge.classList.add('mock');
  }
}

function toggleModeDropdown() {
  document.getElementById('modeDropdown').classList.toggle('open');
}

async function setMode(mode) {
  document.getElementById('modeDropdown').classList.remove('open');
  await fetch('/api/set-mode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode })
  });
  await checkMode();
}

document.addEventListener('click', (e) => {
  if (!document.getElementById('modeSelector').contains(e.target)) {
    document.getElementById('modeDropdown').classList.remove('open');
  }
});

const TOOL_LABELS = {
  search_insurance_products:       '🔍 보험 상품 검색 중...',
  compare_insurance_products:      '📊 상품 비교 중...',
  get_premium_estimate:            '💰 보험료 계산 중...',
  retrieve_insurance_knowledge:    '📚 지식 베이스 검색 중...',
  fetch_fss_realtime_products:     '🏛️ FSS 실시간 조회 중...',
  get_personalized_recommendation: '⚡ 맞춤 추천 생성 중...',
  search_insmarket_products:       '📊 보험다모아 공시 조회 중...',
  search_web:                      '🌐 웹 검색 중...',
  fetch_webpage:                   '📄 페이지 읽는 중...',
  get_credit_score:                '💳 신용점수 조회 중...',
  _news_search:                    '📰 관련 뉴스 검색 중...',
  assess_cancer_survivor:          '🔬 암 완치자 인수 심사 중... [시나리오 1]',
  assess_low_risk_discount:        '📉 AI 저위험군 할인 분석 중... [시나리오 2]',
  assess_pacs_no_extra:            '🩻 영상 소견 노-할증 분석 중... [시나리오 3]',
  assess_dynamic_discount:         '💚 동적 보험료 캐시백 계산 중... [시나리오 4]',
  assess_chronic_disease_rate:     '💊 맞춤형 유병자 요율 산출 중... [시나리오 5]',
  assess_healthy_body_discount:        '🌿 건강체 특별약관 할인 산출 중... [시나리오 6]',
  assess_polyp_removal_eligibility:    '🔭 위 내시경 용종 절제 후 가입 가능 여부 분석 중... [시나리오 7]',
  assess_health_credit:                '💳 Health-Credit 신용평가 중... [시나리오 8]',
  assess_sme_health_loan:              '🏪 소상공인 건강 대출 우대 분석 중... [시나리오 9]',
  assess_rental_approval:              '🛒 렌탈/할부 금융 승인 분석 중... [시나리오 10]',
  assess_healthy_body_loan:            '🏦 건강담보대출 심사 중... [시나리오 11]',
  assess_health_secured_loan:          '💰 건강자산담보대출 PLUS 심사 중... [시나리오 12]',
  assess_adverse_selection_score:      '🔎 신용+건강 교차 역선택 탐지 중... [시나리오 13]',
  assess_thin_filer_adverse_selection: '🛡️ 씬파일러 역선택 방지 심사 중... [시나리오 14]',
  assess_early_care:                   '🏥 사전 케어 중증화 차단 분석 중... [시나리오 15]',
  assess_default_prevention:           '🛡️ 부실률 차단 위험 예측 중... [시나리오 16]',
};

function scrollToBottom() {
  const chat = document.getElementById('chat');
  chat.scrollTop = chat.scrollHeight;
}

function addMessage(role, text) {
  const chat = document.getElementById('chat');
  const isUser = role === 'user';

  const div = document.createElement('div');
  div.className = `msg ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = isUser ? '👤' : '🛡️';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  if (isUser) {
    bubble.textContent = text;
  } else {
    bubble.innerHTML = addLinksToTables(marked.parse(preprocessMd(text)));
  }

  div.appendChild(avatar);
  div.appendChild(bubble);
  chat.appendChild(div);
  scrollToBottom();
}

function createStreamingBubble() {
  const chat = document.getElementById('chat');

  const msgDiv = document.createElement('div');
  msgDiv.className = 'msg bot';

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = '🛡️';

  const right = document.createElement('div');
  right.style.display = 'flex';
  right.style.flexDirection = 'column';
  right.style.maxWidth = '100%';

  const toolStatus = document.createElement('div');
  toolStatus.className = 'tool-status';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  // initial typing indicator
  bubble.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';

  right.appendChild(toolStatus);
  right.appendChild(bubble);
  msgDiv.appendChild(avatar);
  msgDiv.appendChild(right);
  chat.appendChild(msgDiv);
  scrollToBottom();

  return { msgDiv, bubble, toolStatus };
}

async function sendMessage() {
  if (isLoading) return;
  const input = document.getElementById('input');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  autoResize(input);
  addMessage('user', text);
  isLoading = true;
  document.getElementById('send').disabled = true;

  const { bubble, toolStatus } = createStreamingBubble();
  let fullText = '';
  let cursor = null;

  function startCursor() {
    if (!cursor) {
      cursor = document.createElement('span');
      cursor.className = 'stream-cursor';
      bubble.appendChild(cursor);
    }
  }
  function removeCursor() {
    if (cursor) { cursor.remove(); cursor = null; }
  }

  try {
    const r = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, session_id: SESSION_ID })
    });

    if (!r.ok) {
      bubble.innerHTML = '⚠️ 서버 오류가 발생했습니다.';
    } else {
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let event;
          try { event = JSON.parse(line.slice(6)); } catch { continue; }

          if (event.type === 'token') {
            fullText += event.text;
            bubble.innerHTML = marked.parse(preprocessMd(fullText));
            startCursor();
            scrollToBottom();

          } else if (event.type === 'tool_start') {
            toolStatus.textContent = TOOL_LABELS[event.tool] || '⚙️ 처리 중...';
            toolStatus.style.display = 'block';

          } else if (event.type === 'tool_done') {
            toolStatus.style.display = 'none';

          } else if (event.type === 'done') {
            fullText = event.full_text || fullText;
            bubble.innerHTML = addLinksToTables(marked.parse(preprocessMd(fullText)));
            toolStatus.style.display = 'none';
            removeCursor();
            scrollToBottom();

          } else if (event.type === 'error') {
            bubble.innerHTML = '⚠️ 오류: ' + event.message;
            toolStatus.style.display = 'none';
            removeCursor();
          }
        }
      }
      removeCursor();
    }
  } catch(e) {
    bubble.innerHTML = '⚠️ 서버 연결 오류가 발생했습니다.';
  }

  isLoading = false;
  document.getElementById('send').disabled = false;
  input.focus();
}

async function resetChat() {
  await fetch('/api/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: SESSION_ID })
  });
  document.getElementById('chat').innerHTML = '';
  addMessage('bot', '대화가 초기화되었습니다. 무엇을 도와드릴까요?');
}

function quickSend(text) {
  document.getElementById('input').value = text;
  sendMessage();
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

// ── Tab switching ──────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.currentTarget.classList.add('active');
}
function switchTabDirect(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  const panel = document.getElementById('tab-' + name);
  if (panel) panel.classList.add('active');
  const btn = document.querySelector(`.tab-btn[onclick*="'${name}'"]`);
  if (btn) btn.classList.add('active');
}

function openUrl(url) { window.open(url, '_blank'); }

// ── Credit score tier helper ───────────────────────────────
function scoreTier(v) {
  if (v >= 900) return { cls:'tier1', label:'최우량' };
  if (v >= 750) return { cls:'tier2', label:'우량' };
  if (v >= 600) return { cls:'tier3', label:'보통' };
  if (v >= 450) return { cls:'tier4', label:'주의' };
  return { cls:'tier5', label:'불량' };
}

function updateScoreBadge(type) {
  const input = document.getElementById('cf-' + type);
  const badge = document.getElementById('badge-' + type);
  const v = parseInt(input.value);
  if (isNaN(v) || v < 300 || v > 1000) { badge.textContent = ''; badge.className = 'score-badge'; }
  else {
    const t = scoreTier(v);
    badge.textContent = t.label;
    badge.className = 'score-badge ' + t.cls;
  }
  updateAvgNote();
}

function updateAvgNote() {
  const nice = parseInt(document.getElementById('cf-nice').value);
  const kcb  = parseInt(document.getElementById('cf-kcb').value);
  const note = document.getElementById('score-avg-note');
  const both = !isNaN(nice) && !isNaN(kcb);
  const oneNice = !isNaN(nice) && isNaN(kcb);
  const oneKcb  = isNaN(nice) && !isNaN(kcb);
  if (both) {
    const avg = Math.round((nice + kcb) / 2);
    const t = scoreTier(avg);
    note.innerHTML = `📊 NICE+KCB 평균 점수: <strong>${avg}점</strong> — <strong>${t.label}</strong> 등급으로 포트폴리오를 구성합니다.`;
  } else if (oneNice) {
    const t = scoreTier(nice);
    note.innerHTML = `📊 NICE 점수 ${nice}점 (${t.label}) 기준으로 포트폴리오를 구성합니다.`;
  } else if (oneKcb) {
    const t = scoreTier(kcb);
    note.innerHTML = `📊 KCB 점수 ${kcb}점 (${t.label}) 기준으로 포트폴리오를 구성합니다.`;
  } else {
    note.innerHTML = '';
  }
}

function toggleMedical(label) {
  const cb = label.querySelector('input[type=checkbox]');
  cb.checked = !cb.checked;
  label.classList.toggle('checked', cb.checked);
}

function getCheckedConditions() {
  return Array.from(document.querySelectorAll('#medical-grid input[type=checkbox]:checked'))
    .map(cb => cb.value);
}

// ── 마크다운 전처리: 숫자 범위 ~ 를 취소선 오해 방지 ───────────────
function preprocessMd(text) {
  // 숫자·한글 사이의 ~ 를 \~ 로 이스케이프하여 marked.js 취소선 오렌더링 방지
  // 예: "300만~500만" → "300만\~500만"
  return text.replace(/([\d가-힣원,]+)\s*~\s*([\d가-힣원,])/g, '$1\\~$2');
}

// ── 보험사 가입 링크 매핑 ─────────────────────────────────────
const INSURER_URLS = {
  // 생명보험사
  '삼성생명':       'https://www.samsunglife.com',
  '한화생명':       'https://www.hanwhalife.com',
  '교보생명':       'https://www.kyobo.com',
  '교보라이프플래닛': 'https://www.lifeplanet.co.kr',
  '신한라이프':     'https://www.shinhanlife.co.kr',
  'NH농협생명':     'https://www.nhlife.co.kr',
  '농협생명':       'https://www.nhlife.co.kr',
  '라이나생명':     'https://www.lina.co.kr',
  'AIA생명':        'https://www.aia.co.kr',
  'KB라이프':       'https://www.kblife.co.kr',
  'KB라이프생명':   'https://www.kblife.co.kr',
  '동양생명':       'https://www.myangel.co.kr',
  '흥국생명':       'https://www.heungkuklife.co.kr',
  '미래에셋생명':   'https://life.miraeasset.com',
  'ABL생명':        'https://www.abllife.co.kr',
  'DB생명':         'https://direct.idblife.com',
  '메트라이프':     'https://www.metlife.co.kr',
  '푸르덴셜생명':   'https://www.kblife.co.kr',
  '처브라이프':     'https://www.chubblife.co.kr',
  // 손해보험사
  '삼성화재':  'https://direct.samsungfire.com',
  '현대해상':      'https://direct.hi.co.kr',
  '현대해상화재':  'https://direct.hi.co.kr',
  'DB손해보험':    'https://www.idbins.com',
  'DB손보':        'https://www.idbins.com',
  'KB손보':        'https://www.kbinsure.co.kr',
  'KB손해보험':    'https://www.kbinsure.co.kr',
  '메리츠화재':    'https://direct.meritzfire.com',
  '메리츠손해보험': 'https://direct.meritzfire.com',
  '한화손보':      'https://www.hwgeneralins.com',
  '한화손해보험':  'https://www.hwgeneralins.com',
  '롯데손보':      'https://www.lotteins.co.kr',
  '롯데손해보험':  'https://www.lotteins.co.kr',
  '흥국화재':      'https://www.heungkukfire.co.kr',
  '하나손보':      'https://www.hanainsure.co.kr',
  '하나손해보험':  'https://www.hanainsure.co.kr',
  '신한EZ손해보험': 'https://www.shinhanez.co.kr',
  '신한EZ':        'https://www.shinhanez.co.kr',
  '농협손보':      'https://www.nhfire.co.kr',
  'NH손해보험':    'https://www.nhfire.co.kr',
};
const DAMOAH_URL = 'https://www.e-insmarket.or.kr';

function findInsurerUrl(text) {
  for (const [name, url] of Object.entries(INSURER_URLS)) {
    if (text.includes(name)) return { name, url };
  }
  return null;
}

function addLinksToTables(htmlStr) {
  const wrap = document.createElement('div');
  wrap.innerHTML = htmlStr;

  wrap.querySelectorAll('table').forEach(tbl => {
    const thead = tbl.querySelector('thead tr');
    const tbody = tbl.querySelector('tbody');
    if (!thead || !tbody) return;

    // "이 답변의 근거" 테이블(신뢰도 컬럼 존재) 제외
    const thTexts = Array.from(thead.querySelectorAll('th')).map(t => t.textContent.trim());
    if (thTexts.includes('신뢰도') || thTexts.includes('출처')) return;

    // 헤더에 "가입 안내" 열 추가
    const th = document.createElement('th');
    th.textContent = '가입 안내';
    thead.appendChild(th);

    tbody.querySelectorAll('tr').forEach(row => {
      const rowText = row.textContent;
      const insurer = findInsurerUrl(rowText);
      const td = document.createElement('td');

      const a = document.createElement('a');
      a.target = '_blank';
      a.rel = 'noopener noreferrer';

      if (insurer) {
        a.href = insurer.url;
        a.className = 'ins-link-btn';
        a.textContent = '가입하기 →';
      } else {
        a.href = DAMOAH_URL;
        a.className = 'ins-link-btn ins-link-damoah';
        a.textContent = '비교하기 →';
      }
      td.appendChild(a);
      row.appendChild(td);
    });
  });

  return wrap.innerHTML;
}

function renderCompositeCard(cs) {
  if (!cs) return '';
  const deltaStr = cs.total_delta >= 0 ? `+${cs.total_delta}` : `${cs.total_delta}`;
  const riskCls = {
    '일반': 'cs-risk-normal', '주의': 'cs-risk-caution',
    '중위험': 'cs-risk-mid', '고위험': 'cs-risk-high'
  }[cs.underwriting_risk] || 'cs-risk-normal';

  const adjRows = (cs.adjustments || []).map(a => {
    const cls = a.delta > 0 ? 'adj-delta-pos' : a.delta < 0 ? 'adj-delta-neg' : 'adj-delta-zer';
    const sign = a.delta > 0 ? '+' : '';
    return `<div class="adj-item">
      <span>${a.factor} <span style="opacity:0.7;font-size:10px">— ${a.reason}</span></span>
      <span class="${cls}">${sign}${a.delta}</span>
    </div>`;
  }).join('');

  const sbcRows = (cs.adjustments || []).map(a => {
    const cls = a.delta > 0 ? 'sbc-pos' : a.delta < 0 ? 'sbc-neg' : 'sbc-zer';
    const sign = a.delta > 0 ? '+' : '';
    return `<div class="sbc-row"><span>${a.factor}</span><span class="${cls}">${sign}${a.delta}점</span></div>`;
  }).join('');

  return `<div class="score-breakdown-card">
    <h4>📊 종합 보험 가입 적합도 분석</h4>
    <div class="sbc-row"><span>기본 신용점수 (NICE/KCB 평균)</span><span style="font-weight:700">${cs.base_score}점</span></div>
    ${sbcRows}
    <div class="sbc-row" style="font-weight:700;border-top:2px solid #e2e8f0;margin-top:6px;padding-top:6px">
      <span>종합 적합도 지수</span>
      <span style="color:#1d4ed8;font-size:15px">${cs.composite_score}점 (${cs.grade})</span>
    </div>
    <div style="margin-top:10px;font-size:11.5px;color:#475569">
      <strong>보험 심사 위험도:</strong>
      <span class="risk-badge ${riskCls === 'cs-risk-normal' ? 'risk-low' : riskCls === 'cs-risk-caution' ? 'risk-med' : 'risk-high'}">${cs.underwriting_risk}</span>
      ${cs.underwriting_risk !== '일반' ? `<span style="margin-left:6px;color:#64748b">— 간편심사·무심사형 상품 우선 검토</span>` : ''}
    </div>
    ${cs.preferred_products && cs.preferred_products.length ? `<div style="margin-top:8px;font-size:11.5px;color:#475569"><strong>적합 상품군:</strong> ${cs.preferred_products.slice(0,4).join(' · ')}</div>` : ''}
    ${cs.avoid_products && cs.avoid_products.length ? `<div style="margin-top:4px;font-size:11.5px;color:#475569"><strong>신중 검토 상품:</strong> <span style="color:#dc2626">${cs.avoid_products.slice(0,3).join(' · ')}</span></div>` : ''}
  </div>`;
}

function renderPolicyLoanCard(ld) {
  if (!ld) return '';
  const years = ['1','3','5','10'];
  const stripMd = s => (s || '').replace(/\*\*/g, '').replace(/\*/g, '').trim();
  // 대출 한도 포맷 (만원 단위)
  const fmt = n => {
    if (n >= 100000000) return `${(n/100000000).toFixed(1)}억원`;
    if (n >= 10000)     return `${Math.round(n/10000).toLocaleString()}만원`;
    return n > 0 ? `${n.toLocaleString()}원` : '—';
  };
  // 보험료 포맷 (원 단위 그대로 표시)
  const fmtPrem = n => {
    if (n >= 10000) return `${(n/10000).toFixed(n % 10000 === 0 ? 0 : 1)}만원`;
    return `${n.toLocaleString()}원`;
  };

  let eligRows = '';
  for (const p of (ld.eligible || [])) {
    const loanCells = years.map(y => `<td>${fmt(p.loans[y] || 0)}</td>`).join('');
    eligRows += `<tr>
      <td>${p.type}</td>
      <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis">${p.name}</td>
      <td>${fmtPrem(p.monthly_premium)}</td>
      ${loanCells}
    </tr>`;
  }

  const totalCells = years.map(y => `<td>${fmt(ld.totals && ld.totals[y] || 0)}</td>`).join('');
  const totalRow = ld.has_eligible ? `<tr class="loan-total-row">
    <td colspan="3">합계 (저축성 상품 기준)</td>${totalCells}
  </tr>` : '';

  const ineligBadges = (ld.ineligible || []).map(p =>
    `<span class="inelig-badge">${stripMd(p.type)} (${fmtPrem(p.monthly_premium)})</span>`
  ).join('');

  if (!ld.has_eligible && !(ld.ineligible || []).length) return '';

  return `<div class="policy-loan-card">
    <h4>💰 약관대출 예상 한도</h4>
    <p class="loan-subtitle">저축성 보험의 해지환급금을 담보로 보험사에서 대출받을 수 있는 예상 한도입니다.</p>
    ${ld.has_eligible ? `
    <div class="loan-table-wrap">
      <table class="loan-table">
        <thead><tr>
          <th>보험 종류</th><th>상품명</th><th>월 보험료</th>
          ${years.map(y => `<th>${y}년 후</th>`).join('')}
        </tr></thead>
        <tbody>${eligRows}${totalRow}</tbody>
      </table>
    </div>` : '<p style="color:#64748b;font-size:12px">추천된 상품 중 약관대출 가능한 저축성 보험이 없습니다.</p>'}
    ${ineligBadges ? `<div class="inelig-section">
      <strong>순수보장형 (약관대출 불가):</strong> ${ineligBadges}
    </div>` : ''}
    <p class="loan-disclaimer">※ 실제 대출 한도·이자율은 보험사·상품·납입 완료 여부에 따라 다릅니다. 일반적으로 해지환급금의 80~95% 이내. 대출 중 이자 미납 시 보험 계약 실효 가능.</p>
    ${ld.has_eligible ? `
    <details class="loan-basis">
      <summary>📐 산출 기준 보기</summary>
      <div class="loan-basis-body">
        <p class="loan-basis-formula">약관대출 한도 = <strong>월 보험료 × 12 × 납입기간(년) × 해지환급금률 × 약관대출비율</strong></p>
        <div class="loan-table-wrap">
          <table class="loan-table loan-basis-table">
            <thead><tr>
              <th>보험 종류</th><th>기준</th>
              <th>1년 후</th><th>3년 후</th><th>5년 후</th><th>10년 후</th>
              <th>약관대출 비율</th>
            </tr></thead>
            <tbody>
              <tr><td>종신보험</td><td style="font-size:10px;color:#64748b">비갱신형</td><td>30%</td><td>55%</td><td>70%</td><td>85%</td><td>85%</td></tr>
              <tr><td>연금보험</td><td style="font-size:10px;color:#64748b">공시이율형</td><td>75%</td><td>88%</td><td>92%</td><td>96%</td><td>90%</td></tr>
              <tr><td>변액보험</td><td style="font-size:10px;color:#64748b">수익률 변동</td><td>50%</td><td>70%</td><td>80%</td><td>88%</td><td>80%</td></tr>
              <tr><td>저축보험</td><td style="font-size:10px;color:#64748b">저축성</td><td>80%</td><td>90%</td><td>94%</td><td>97%</td><td>90%</td></tr>
              <tr><td>유니버셜</td><td style="font-size:10px;color:#64748b">유니버셜형</td><td>60%</td><td>75%</td><td>83%</td><td>90%</td><td>85%</td></tr>
            </tbody>
          </table>
        </div>
        <p style="color:#94a3b8;font-size:10px;margin:6px 0 0">해지환급금률은 업계 평균 추정치입니다. 실제 해지환급금은 공시이율·특약·저해약환급금형 여부에 따라 다릅니다.</p>
      </div>
    </details>` : ''}
  </div>`;
}

function toggleSection(name) {
  const body   = document.getElementById('body-' + name);
  const toggle = document.getElementById('toggle-' + name);
  const opening = !body.classList.contains('open');
  body.classList.toggle('open', opening);
  toggle.classList.toggle('open', opening);
}

function updateFinancialSummary() {
  const income  = parseFloat(document.getElementById('cf-income').value) || 0;
  const assets  = parseFloat(document.getElementById('cf-assets').value) || 0;
  const debt    = parseFloat(document.getElementById('cf-debt').value) || 0;
  const cprem   = parseFloat(document.getElementById('cf-current-premium').value) || 0;
  const summaryEl = document.getElementById('financial-summary');

  if (!income && !assets && !debt) {
    summaryEl.classList.remove('visible');
    return;
  }

  const monthlyIncome = income / 12;
  let rows = '';

  if (income)
    rows += `<div class="financial-summary-row"><span>월 환산 소득</span><span><strong>${Math.round(monthlyIncome).toLocaleString()}만원</strong>/월</span></div>`;

  if (debt && income) {
    const ratio = (debt / income * 100).toFixed(0);
    const [cls, lbl] = ratio < 100 ? ['risk-low','양호'] : ratio < 300 ? ['risk-med','보통'] : ['risk-high','과다'];
    rows += `<div class="financial-summary-row"><span>부채비율 (부채÷연소득)</span><span><strong>${ratio}%</strong> <span class="risk-badge ${cls}">${lbl}</span></span></div>`;
  }

  if (cprem && income) {
    const avail = Math.max(0, monthlyIncome * 0.15 - cprem);
    rows += `<div class="financial-summary-row"><span>추가 가입 여력 (소득 15% 기준)</span><span><strong>≈ ${avail.toFixed(0)}만원</strong>/월</span></div>`;
  }

  if (assets)
    rows += `<div class="financial-summary-row"><span>금융자산</span><span><strong>${assets.toLocaleString()}만원</strong></span></div>`;

  summaryEl.innerHTML = `<div style="font-weight:700;margin-bottom:6px;color:#0369a1">📊 재무 현황 분석</div>${rows}`;
  summaryEl.classList.add('visible');
}

// ── Portfolio generation ───────────────────────────────────
async function generatePortfolio() {
  const age    = parseInt(document.getElementById('cf-age').value);
  const gender = document.getElementById('cf-gender').value;
  const budget = parseInt(document.getElementById('cf-budget').value);
  const nice   = parseInt(document.getElementById('cf-nice').value);
  const kcb    = parseInt(document.getElementById('cf-kcb').value);
  const married  = document.getElementById('cf-married').value;
  const existing = document.getElementById('cf-existing').value.trim();
  const health   = document.getElementById('cf-health').value.trim();

  // 금융데이터
  const income     = parseFloat(document.getElementById('cf-income').value) || null;
  const assets     = parseFloat(document.getElementById('cf-assets').value) || null;
  const debt       = parseFloat(document.getElementById('cf-debt').value) || null;
  const curPremium = parseFloat(document.getElementById('cf-current-premium').value) || null;

  // 대안데이터
  const employment = document.getElementById('cf-employment').value;
  const housing    = document.getElementById('cf-housing').value;
  const telecom    = document.getElementById('cf-telecom').value;
  const utility    = document.getElementById('cf-utility').value;

  // 의료이력
  const medConditions     = getCheckedConditions();
  const hospitalization   = document.getElementById('cf-hospitalization').value;
  const currentMedications = document.getElementById('cf-medications').value.trim();

  if (!age || age < 20 || age > 70) { alert('나이를 20~70세 사이로 입력해주세요.'); return; }
  if (!budget || budget < 5)        { alert('월 예산을 입력해주세요 (최소 5만원).'); return; }

  const hasNice = !isNaN(nice) && nice >= 300 && nice <= 1000;
  const hasKcb  = !isNaN(kcb)  && kcb  >= 300 && kcb  <= 1000;
  if (!hasNice && !hasKcb) { alert('NICE 또는 KCB 신용점수 중 하나 이상을 입력해주세요.'); return; }

  const scores = [];
  if (hasNice) scores.push({ source: 'NICE', score: nice });
  if (hasKcb)  scores.push({ source: 'KCB',  score: kcb  });
  const avgScore = Math.round(scores.reduce((s,x) => s + x.score, 0) / scores.length);
  const tier = scoreTier(avgScore);

  // Show result area with loading
  const resultEl = document.getElementById('credit-result');
  const bodyEl   = document.getElementById('credit-result-body');
  const pillEl   = document.getElementById('result-score-pill');
  resultEl.style.display = 'block';
  resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  pillEl.textContent = `${avgScore}점 (${tier.label})`;
  bodyEl.innerHTML = '<div class="credit-loading"><div class="spin"></div>포트폴리오 생성 중... (30~60초 소요)</div>';

  const btn = document.getElementById('gen-btn');
  btn.disabled = true;
  btn.textContent = '⏳ 생성 중...';

  try {
    const resp = await fetch('/api/credit-portfolio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        age, gender, budget_man: budget, scores, avg_score: avgScore,
        married, existing_insurance: existing, health_notes: health,
        financial_data: { income, assets, debt, current_premium: curPremium },
        alt_data: { employment, housing, telecom, utility },
        medical_data: { conditions: medConditions, hospitalization, current_medications: currentMedications }
      })
    });
    const data = await resp.json();
    if (data.error) {
      bodyEl.innerHTML = `<p style="color:#dc2626">⚠️ ${data.error}</p>`;
    } else {
      // 종합 적합도 카드 렌더링
      const cardArea = document.getElementById('composite-score-card-area');
      if (data.composite_score_data) {
        cardArea.innerHTML = renderCompositeCard(data.composite_score_data);
        const cs = data.composite_score_data;
        pillEl.textContent = `종합 ${cs.composite_score}점 (${cs.grade})`;
      } else {
        cardArea.innerHTML = '';
      }
      // 약관대출 카드 렌더링
      const loanArea = document.getElementById('policy-loan-card-area');
      if (loanArea) {
        loanArea.innerHTML = renderPolicyLoanCard(data.policy_loan_data);
      }
      // 레이더 차트 + 보험료 납입이력 가점 + 신용점수 개선 시뮬레이터
      renderCreditRadar(avgScore, data.composite_score_data);
      renderPremiumHistCard(avgScore);
      renderScoreSimulator(avgScore);
      bodyEl.innerHTML = addLinksToTables(marked.parse(preprocessMd(data.result || '결과가 없습니다.')));
    }
  } catch(e) {
    bodyEl.innerHTML = '<p style="color:#dc2626">⚠️ 서버 연결 오류가 발생했습니다.</p>';
  } finally {
    btn.disabled = false;
    btn.textContent = '💳 신용점수 반영 포트폴리오 생성';
  }
}

let _radarChartInst = null;

function renderCreditRadar(avgScore, cs) {
  const card = document.getElementById('radar-chart-card');
  if (!card) return;
  card.style.display = 'block';

  const fin  = cs ? Math.min(100, Math.round((cs.composite_score || avgScore) / 10)) : Math.round(avgScore / 10);
  const creditPct = Math.min(100, Math.round(avgScore / 10));
  const healthPct = cs ? Math.min(100, Math.round((cs.has_score || 70))) : 70;
  const jobPct    = cs ? Math.min(100, Math.round((cs.employment_score || 65))) : 65;
  const homePct   = cs ? Math.min(100, Math.round((cs.housing_score   || 60))) : 60;
  const finPct    = Math.min(100, fin);

  const ctx = document.getElementById('credit-radar-canvas').getContext('2d');
  if (_radarChartInst) { _radarChartInst.destroy(); }
  _radarChartInst = new Chart(ctx, {
    type: 'radar',
    data: {
      labels: ['신용', '건강', '재무', '직업', '거주'],
      datasets: [{
        label: '다차원 평가',
        data: [creditPct, healthPct, finPct, jobPct, homePct],
        backgroundColor: 'rgba(59,130,246,0.18)',
        borderColor: '#3b82f6',
        borderWidth: 2,
        pointBackgroundColor: '#3b82f6',
        pointRadius: 4,
      }]
    },
    options: {
      responsive: false,
      scales: { r: { min: 0, max: 100, ticks: { display: false }, pointLabels: { font: { size: 11 } } } },
      plugins: { legend: { display: false } },
    }
  });
}

function renderPremiumHistCard(avgScore) {
  const card = document.getElementById('premium-hist-card');
  const body = document.getElementById('premium-hist-body');
  if (!card || !body) return;
  const rows = [
    { label: '보험료 6개월 정상납부',  pts: '+8점' },
    { label: '보험료 12개월 정상납부', pts: '+15점' },
    { label: '보험료 24개월 정상납부', pts: '+22점' },
    { label: '통신·공과금 병행 납부',  pts: '추가 +12점' },
  ];
  body.innerHTML = rows.map(r =>
    `<div class="premium-hist-row"><span>${r.label}</span><span class="premium-hist-pts">${r.pts}</span></div>`
  ).join('');
  card.style.display = 'block';
}

function renderScoreSimulator(avgScore) {
  const area = document.getElementById('score-sim-area');
  if (!area) return;

  const tiers = [
    { threshold: 600, grade: '보통(4~6등급)', benefits: ['실손·암·치아보험 표준 조건 가입'] },
    { threshold: 750, grade: '우량(2~3등급)', benefits: ['종신보험 가입', '보험료 우대 할인', 'Health-Credit 금리 -1.3%p'] },
    { threshold: 900, grade: '최우량(1등급)',  benefits: ['VIP 보험 조건', '변액유니버셜', 'Health-Credit 금리 -1.8%p'] },
  ];
  const factors = [
    { action: '보험료 12개월 정상납부', pts: 15 },
    { action: '통신비·공과금 12개월 납부', pts: 12 },
    { action: '대출 12개월 정상상환', pts: 20 },
    { action: '카드 연체 이력 소멸(2년)', pts: 25 },
    { action: '건강검진 2년 연속 수검', pts: 10 },
    { action: '소액 대출 상환 완료', pts: 18 },
  ];

  const pending = tiers.filter(t => t.threshold > avgScore);
  if (!pending.length) {
    area.innerHTML = `<div class="score-sim-card"><div class="score-sim-title">✅ 신용점수 개선 시뮬레이터</div><p style="font-size:12px;color:#16a34a">현재 점수(${avgScore}점)가 최우량 등급 이상입니다. 모든 혜택이 열려 있습니다!</p></div>`;
    return;
  }

  let html = `<div class="score-sim-card"><div class="score-sim-title">📈 신용점수 개선 시뮬레이터 (현재 ${avgScore}점 → 목표 달성 경로)</div>`;
  for (const tier of pending) {
    const gap = tier.threshold - avgScore;
    let acc = 0; const needed = [];
    for (const f of factors) { if (acc >= gap) break; needed.push(f); acc += f.pts; }
    const ok = acc >= gap;
    html += `<div class="score-sim-scenario">
      <div class="score-sim-target">${tier.grade} 달성 목표: ${tier.threshold}점 (+${gap}점 필요)</div>
      <div class="score-sim-gap">아래 조건 달성 시 +${acc}점 획득 가능 ${ok ? '(달성 가능!)' : ''}</div>
      <ul class="score-sim-steps">${needed.map(f => `<li>${f.action} <span style="color:#16a34a;font-weight:700">+${f.pts}점</span></li>`).join('')}</ul>
      <div class="score-sim-benefits">${tier.benefits.map(b => `<span class="${ok ? 'score-sim-achieved' : 'score-sim-benefit'}">${b}</span>`).join('')}</div>
    </div>`;
  }
  html += '</div>';
  area.innerHTML = html;
}

// ── Health Risk 전역 상태 ──────────────────────────────────
let _hrLastResult = null;

// ── Health Risk: BMI 자동계산 ──────────────────────────────
function hrCalcBMI() {
  const h = parseFloat(document.getElementById('hr-height').value);
  const w = parseFloat(document.getElementById('hr-weight-val').value);
  const el = document.getElementById('hr-bmi-disp');
  if (h > 0 && w > 0) {
    const bmi = (w / ((h / 100) ** 2)).toFixed(1);
    const lbl = bmi < 18.5 ? '저체중' : bmi < 23 ? '정상' : bmi < 25 ? '과체중' : '비만';
    el.value = `${bmi} (${lbl})`;
    el.style.color = bmi >= 25 ? '#dc2626' : bmi >= 23 ? '#d97706' : '#16a34a';
  } else {
    el.value = '';
    el.style.color = '#64748b';
  }
}

// ── Health Risk: 포트폴리오 생성 ───────────────────────────
async function generateHealthPortfolio() {
  const age = parseInt(document.getElementById('hr-age').value);
  const gender = document.getElementById('hr-gender').value;
  if (!age || age < 20 || age > 80) {
    alert('나이를 20~80세 사이로 입력해주세요.');
    return;
  }

  const num = id => {
    const v = document.getElementById(id).value;
    return v !== '' ? parseFloat(v) : null;
  };
  const sel = id => {
    const v = document.getElementById(id).value;
    return v !== '' ? parseInt(v) : null;
  };

  const payload = {
    age, gender,
    height: num('hr-height'),
    weight: num('hr-weight-val'),
    waist:  num('hr-waist'),
    sbp:    num('hr-sbp'),
    dbp:    num('hr-dbp'),
    total_cholesterol: num('hr-tc'),
    triglyceride:      num('hr-tg'),
    hdl:    num('hr-hdl'),
    ldl:    num('hr-ldl'),
    ast:    num('hr-ast'),
    alt:    num('hr-alt'),
    ggt:    num('hr-ggt'),
    smoke:  sel('hr-smoke'),
    drink:  sel('hr-drink'),
    bfc_tier: sel('hr-bfc-tier'),
  };

  const resultArea = document.getElementById('health-result-area');
  const btn = document.getElementById('health-gen-btn');
  resultArea.style.display = 'none';
  btn.disabled = true;
  btn.textContent = '⏳ 분석 중...';

  try {
    const resp = await fetch('/api/health-risk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (data.error) {
      alert('오류: ' + data.error);
      return;
    }
    hrRenderResult(data);
    resultArea.style.display = 'block';
    resultArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    alert('서버 연결 오류가 발생했습니다.');
  } finally {
    btn.disabled = false;
    btn.textContent = '🏥 건강위험 분석 및 보험 추천';
  }
}

function hrRenderResult(data) {
  _hrLastResult = data;
  const ra  = data.risk_assessment || {};
  const ins = data.input_summary   || {};
  const rTypes   = data.recommended_insurance_types || [];
  const products = data.insmarket_products || {};

  // 위험도 게이지 (risk_score 0~1 → 0~100%)
  const score = ra.risk_score || 0;
  const pct   = Math.min(99, Math.round(score * 100));
  document.getElementById('hr-risk-pointer').style.left = pct + '%';
  document.getElementById('hr-score-num').textContent   = (score * 100).toFixed(1) + '%';

  const band   = ra.risk_band || '';
  const chipEl = document.getElementById('hr-band-chip');
  chipEl.textContent = band;
  chipEl.className   = 'risk-band-chip ' + (
    band === '고위험'   ? 'risk-band-high' :
    band === '중간위험' ? 'risk-band-mid'  : 'risk-band-low'
  );
  document.getElementById('hr-model-note').textContent = ra.model || '';

  // 임상 플래그
  const flags = ins.flags || [];
  document.getElementById('hr-flag-chips').innerHTML = flags.map(f =>
    f === '특이소견 없음'
      ? `<span class="flag-chip flag-chip-ok">✓ ${f}</span>`
      : `<span class="flag-chip">⚠ ${f}</span>`
  ).join('');

  // 추천 보험 유형
  document.getElementById('hr-ins-type-tags').innerHTML =
    rTypes.map(t => `<span class="ins-type-tag">${t}</span>`).join('');
  document.getElementById('hr-guidance').textContent = data.guidance || '';

  // 보험다모아 상품
  const prodEl = document.getElementById('hr-products');
  const types  = Object.keys(products);
  if (!types.length) {
    prodEl.innerHTML = '<p style="color:#94a3b8;font-size:13px;padding:4px 0">상품 조회 결과가 없습니다.</p>';
    return;
  }

  let html = '';
  for (const [type, td] of Object.entries(products)) {
    if (td && td.error) {
      html += `<div class="product-type-sec">
        <div class="product-type-hdr">${type}
          <span style="font-weight:400;color:#94a3b8;font-size:11px">데이터 없음</span>
        </div>
      </div>`;
      continue;
    }
    const results = (td && td.results) || [];
    // 실제 보험료 있는 상품만 표시 (없으면 섹션 전체 숨김)
    if (!results.length) continue;

    const total = results.length;
    html += `<div class="product-type-sec">
      <div class="product-type-hdr" onclick="hrToggleProducts(this)">
        <span>${type} <span style="font-weight:400;color:#64748b;font-size:11px">— ${total}개 조회됨</span></span>
        <span class="hr-prod-arrow">▼</span>
      </div>
      <div class="product-cards-body">`;

    for (const p of results.slice(0, 3)) {
      const co  = p.company      || '-';
      const nm  = p.product_name || p.notes || '-';
      const pr  = p.premium;
      const ag  = (p.file_context && p.file_context.age_group) || p.age_range || '';
      const ge  = (p.file_context && p.file_context.gender) || '';
      const covStr = (p.coverages || []).slice(0, 2).join(' · ');
      const url  = INSURER_URLS[co] || DAMOAH_URL;
      const lCls = INSURER_URLS[co] ? 'ins-link-btn' : 'ins-link-btn ins-link-damoah';
      const lTxt = INSURER_URLS[co] ? '가입하기 →' : '비교하기 →';
      html += `<div class="hr-product-card">
        <div class="hr-prod-name">${nm}</div>
        <div class="hr-prod-co">${co}${ag ? ' · ' + ag : ''}${ge ? ' · ' + ge : ''}</div>
        <div class="hr-prod-row"><span>월 보험료</span><span class="hr-prod-premium">${pr}</span></div>
        ${covStr ? `<div style="font-size:11.5px;color:#64748b;margin-top:5px">${covStr}</div>` : ''}
        <div style="margin-top:8px">
          <a href="${url}" target="_blank" rel="noopener noreferrer" class="${lCls}">${lTxt}</a>
        </div>
      </div>`;
    }
    html += '</div></div>';
  }
  prodEl.innerHTML = html || '<p style="color:#94a3b8;font-size:13px">추천 상품이 없습니다.</p>';

  // ── 이노베이션 존: 암 위험 렌더링 (RGST/DEATH) ───────────────────
  const cr = data.cancer_risk;
  const cancerCard = document.getElementById('hr-cancer-card');
  if (cr && !cr.error) {
    cancerCard.style.display = 'block';
    document.getElementById('hr-cancer-ratio').textContent =
      '인구 평균 대비 ' + (cr.risk_ratio >= 1 ? '+' : '') +
      Math.round((cr.risk_ratio - 1) * 100) + '%';
    const bandEl = document.getElementById('hr-cancer-band');
    bandEl.textContent = cr.band;
    bandEl.className = 'cancer-band-chip ' + (
      cr.band === '고위험' ? 'cancer-band-high' :
      cr.band === '중위험' ? 'cancer-band-mid'  : 'cancer-band-low'
    );
    document.getElementById('hr-cancer-vs').textContent =
      `${cr.age_group} ${cr.gender}성 연간 암 발생률: 인구 10만명당 ${cr.pop_total_per_100k.toFixed(0)}명 → 개인 추정 ${cr.ind_total_per_100k.toFixed(0)}명`;

    const maxRate = Math.max(...(cr.top3_cancers || []).map(c => c.rate_per_100k), 1);
    const barsHtml = (cr.top3_cancers || []).map(c => {
      const pct   = Math.min(100, Math.round(c.rate_per_100k / maxRate * 100));
      const base  = Math.min(100, Math.round(c.base_per_100k  / maxRate * 100));
      const mult  = c.risk_multiplier > 1 ? `<span style="color:#dc2626;font-weight:700">×${c.risk_multiplier}</span>` : '';
      const surv  = c['5yr_survival_pct'] != null ? `5년 생존율 ${c['5yr_survival_pct']}%` : '';
      const color = pct >= 70 ? '#ef4444' : pct >= 40 ? '#f59e0b' : '#34d399';
      return `<div class="cancer-bar-wrap">
        <div class="cancer-bar-label">
          <span>${c.type} ${mult}</span>
          <span style="color:#64748b">${c.rate_per_100k.toFixed(0)} / 10만명</span>
        </div>
        <div class="cancer-bar-track">
          <div class="cancer-bar-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        ${surv ? `<div class="cancer-surv">DEATH 연계 ${surv}</div>` : ''}
      </div>`;
    }).join('');
    document.getElementById('hr-cancer-bars').innerHTML = barsHtml;
    document.getElementById('hr-cancer-source').textContent = '데이터 출처: ' + (cr.data_source || '');
  } else {
    cancerCard.style.display = 'none';
  }

  // ── 이노베이션 존: BFC 보험료 분위 렌더링 ──────────────────────────
  const bfc = data.bfc_info;
  const bfcCard = document.getElementById('hr-bfc-card');
  if (bfc) {
    bfcCard.style.display = 'block';
    const tierPct = Math.round(bfc.tier / 10 * 100);
    document.getElementById('hr-bfc-body').innerHTML = `
      <div style="font-size:13px;font-weight:700;color:#1e293b;margin-bottom:4px">
        ${bfc.label} <span style="font-weight:400;font-size:12px;color:#64748b">(${bfc.desc})</span>
      </div>
      <div class="bfc-tier-bar" style="width:${tierPct}%;background:${bfc.color}"></div>
      <div class="bfc-tier-row">
        <span>1분위</span><span>3분위</span><span>5분위</span><span>7분위</span><span>10분위</span>
      </div>
      <div style="margin-top:10px;padding:10px;background:#f0fdf4;border-radius:8px;font-size:12.5px;color:#065f46">
        💡 <strong>추천 보험료 범위:</strong>
        월 ${bfc.budget_min_10k}~${bfc.budget_max_10k}만원
        <div style="font-size:11.5px;color:#047857;margin-top:4px">${bfc.guidance}</div>
      </div>
      <div style="font-size:11px;color:#94a3b8;margin-top:6px">데이터 출처: 개인정보 이노베이션 존 — NHIS BFC(자격및보험료 3,706만건)</div>`;
  } else {
    bfcCard.style.display = 'none';
  }

  // Health-Credit 신용 가산점 자동 연산
  renderHealthCreditBonus(data);
}

function renderHealthCreditBonus(data) {
  const card = document.getElementById('hr-hc-bonus-card');
  const body = document.getElementById('hr-hc-bonus-body');
  if (!card || !body) return;

  const ra  = data.risk_assessment || {};
  const ins = data.input_summary   || {};
  const bfc = data.bfc_info;

  const riskBand   = ra.risk_band || '저위험';
  const flags      = ins.flags || [];
  const hasNormal  = flags.includes('특이소견 없음') || flags.length === 0;
  const bfcTier    = bfc ? bfc.tier : null;

  // 가산점 계산
  let checkupPts = 0, vitalPts = 0, bfcPts = 0;
  const checkupNote = (data.checkup_consecutive != null)
    ? `연속 ${data.checkup_consecutive}회 수검` : '수검 이력 미확인';

  // 검진 성실도: 위험 낮을수록 가산 (저위험=+20, 중간=+10, 고=+0)
  if (riskBand === '저위험')      checkupPts = 20;
  else if (riskBand === '중간위험') checkupPts = 10;

  // 바이탈 안정도: 이상 소견 없으면 가산
  if (hasNormal) vitalPts = 15;

  // BFC 소득분위 가산
  if (bfcTier) {
    if (bfcTier >= 7)      bfcPts = 10;
    else if (bfcTier >= 4) bfcPts = 5;
  }

  const total = checkupPts + vitalPts + bfcPts;
  const creditEffect = total >= 40 ? '신용점수 +25~35점 추정' :
                       total >= 25 ? '신용점수 +15~25점 추정' :
                       total >= 10 ? '신용점수 +5~15점 추정' : '가산점 기준 미충족';

  body.innerHTML = `
    <div class="hr-hc-bonus-row"><span>건강검진 성실도 (G1E)</span><span style="font-weight:700;color:#1d4ed8">+${checkupPts}점</span></div>
    <div class="hr-hc-bonus-row"><span>바이탈 안정도 (cdw_psmn_vtls)</span><span style="font-weight:700;color:#1d4ed8">+${vitalPts}점</span></div>
    <div class="hr-hc-bonus-row"><span>BFC 소득분위 (${bfcTier ? bfcTier + '분위' : '미입력'})</span><span style="font-weight:700;color:#1d4ed8">+${bfcPts}점</span></div>
    <div class="hr-hc-bonus-total"><span>Health-Credit HAS 합산</span><span>${total}점 / 100점</span></div>
    <div class="hr-hc-bonus-note">신용 효과 추정: ${creditEffect} — 보험료 대출 우대·금리 인하 가능</div>
  `;
  card.style.display = 'block';
}

function hrToggleProducts(hdr) {
  const body  = hdr.nextElementSibling;
  const arrow = hdr.querySelector('.hr-prod-arrow');
  const open  = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (arrow) arrow.textContent = open ? '▶' : '▼';
}

// ── Health Risk: 가이드 탭 전환 ───────────────────────────
function hrGuideTab(el, paneId) {
  document.querySelectorAll('.hg-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.hg-pane').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
  document.getElementById(paneId).classList.add('active');
}

// ── Health Risk: PDF 업로드 ────────────────────────────────
function hrDragOver(e) {
  e.preventDefault();
  document.getElementById('hr-pdf-drop').classList.add('dragover');
}
function hrDragLeave(e) {
  document.getElementById('hr-pdf-drop').classList.remove('dragover');
}
function hrDropFile(e) {
  e.preventDefault();
  document.getElementById('hr-pdf-drop').classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file && file.name.toLowerCase().endsWith('.pdf')) {
    hrUploadPDF(file);
  } else {
    alert('PDF 파일만 업로드 가능합니다.');
  }
}

async function hrUploadPDF(file) {
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) { alert('파일이 10MB를 초과합니다.'); return; }

  const status = document.getElementById('hr-pdf-status');
  const drop   = document.getElementById('hr-pdf-drop');

  status.textContent = '⏳ PDF 분석 중...';
  status.style.color = '#64748b';
  drop.style.pointerEvents = 'none';
  drop.style.opacity = '0.6';
  drop.querySelector('.pdf-drop-text').textContent = file.name;
  drop.querySelector('.pdf-drop-sub').textContent  = '텍스트 추출 중...';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const resp = await fetch('/api/upload-health-pdf', { method: 'POST', body: formData });
    const d    = await resp.json();

    if (d.error) {
      status.textContent = '⚠️ ' + d.error;
      status.style.color = '#dc2626';
      drop.querySelector('.pdf-drop-sub').textContent = '오류 — 다시 시도하세요';
      return;
    }

    // 폼 자동 채우기
    const fill = (id, val) => {
      if (val == null) return;
      const el = document.getElementById(id);
      if (el) { el.value = val; el.dispatchEvent(new Event('input')); }
    };
    const fillSel = (id, val) => {
      if (val == null) return;
      const el = document.getElementById(id);
      if (el) el.value = String(val);
    };
    fill('hr-age',        d.age);
    if (d.gender) fillSel('hr-gender', d.gender);
    fill('hr-height',     d.height);
    fill('hr-weight-val', d.weight);
    fill('hr-waist',      d.waist);
    fill('hr-sbp',        d.sbp);    fill('hr-dbp', d.dbp);
    fill('hr-tc',         d.total_cholesterol);
    fill('hr-tg',         d.triglyceride);
    fill('hr-hdl',        d.hdl);    fill('hr-ldl', d.ldl);
    fill('hr-ast',        d.ast);    fill('hr-alt', d.alt); fill('hr-ggt', d.ggt);
    if (d.smoke != null) fillSel('hr-smoke', d.smoke);
    if (d.drink != null) fillSel('hr-drink', d.drink);
    hrCalcBMI();

    const cnt = Object.entries(d).filter(([k, v]) => !k.startsWith('_') && v != null).length;
    drop.querySelector('.pdf-drop-icon').textContent = '✅';
    drop.querySelector('.pdf-drop-text').textContent = file.name;
    drop.querySelector('.pdf-drop-sub').textContent  = `${cnt}개 항목 추출 완료`;
    drop.style.borderColor = '#22c55e';
    drop.style.background  = '#f0fdf4';
    status.textContent = `✅ ${cnt}개 항목이 자동 입력됐습니다. 확인 후 분석해 주세요.`;
    status.style.color = '#16a34a';

    // 입력 폼으로 스크롤
    document.getElementById('hr-age').scrollIntoView({ behavior: 'smooth', block: 'center' });
  } catch (e) {
    status.textContent = '⚠️ 업로드 오류가 발생했습니다.';
    status.style.color = '#dc2626';
  } finally {
    drop.style.pointerEvents = '';
    drop.style.opacity = '';
  }
}

// ── Health Risk: 건강검진 결과 텍스트 자동 파싱 ───────────
async function hrParseHealthData() {
  const text = document.getElementById('hr-paste-area').value.trim();
  if (!text) { alert('건강검진 결과를 붙여넣어 주세요.'); return; }

  const btn    = document.getElementById('hr-parse-btn');
  const status = document.getElementById('hr-parse-status');
  btn.disabled = true;
  btn.textContent = '⏳ 파싱 중...';
  status.textContent = '';

  try {
    const resp = await fetch('/api/parse-health-data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const d = await resp.json();
    if (d.error) {
      status.textContent = '⚠️ ' + d.error;
      status.style.color = '#dc2626';
      return;
    }

    const fill = (id, val) => {
      if (val == null) return;
      const el = document.getElementById(id);
      if (el) { el.value = val; el.dispatchEvent(new Event('input')); }
    };
    const fillSel = (id, val) => {
      if (val == null) return;
      const el = document.getElementById(id);
      if (el) el.value = String(val);
    };

    fill('hr-age',        d.age);
    if (d.gender) fillSel('hr-gender', d.gender);
    fill('hr-height',     d.height);
    fill('hr-weight-val', d.weight);
    fill('hr-waist',      d.waist);
    fill('hr-sbp',        d.sbp);
    fill('hr-dbp',        d.dbp);
    fill('hr-tc',         d.total_cholesterol);
    fill('hr-tg',         d.triglyceride);
    fill('hr-hdl',        d.hdl);
    fill('hr-ldl',        d.ldl);
    fill('hr-ast',        d.ast);
    fill('hr-alt',        d.alt);
    fill('hr-ggt',        d.ggt);
    if (d.smoke != null) fillSel('hr-smoke', d.smoke);
    if (d.drink != null) fillSel('hr-drink', d.drink);
    hrCalcBMI();

    const filledCount = Object.values(d).filter(v => v != null).length;
    status.textContent = `✅ ${filledCount}개 항목이 자동 입력됐습니다. 확인 후 분석해 주세요.`;
    status.style.color = '#16a34a';
  } catch (e) {
    status.textContent = '⚠️ 서버 연결 오류가 발생했습니다.';
    status.style.color = '#dc2626';
  } finally {
    btn.disabled = false;
    btn.textContent = '✨ 자동 입력';
  }
}

// ── Health Risk: AI 맞춤 추천 ──────────────────────────────
async function hrGetAiRec() {
  if (!_hrLastResult) {
    alert('먼저 건강위험 분석을 실행해주세요.');
    return;
  }

  const btn  = document.getElementById('hr-ai-btn');
  const body = document.getElementById('hr-ai-body');
  btn.disabled = true;
  btn.textContent = '⏳ AI 추천 생성 중... (30~60초)';
  body.style.display = 'none';

  try {
    const resp = await fetch('/api/health-risk-ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ risk_data: _hrLastResult }),
    });
    const d = await resp.json();
    if (d.error) {
      body.innerHTML = `<p style="color:#dc2626">⚠️ ${d.error}</p>`;
    } else {
      body.innerHTML = addLinksToTables(marked.parse(preprocessMd(d.result || '')));
    }
    body.style.display = 'block';
  } catch (e) {
    body.innerHTML = '<p style="color:#dc2626">⚠️ 서버 연결 오류가 발생했습니다.</p>';
    body.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = '🔮 AI 맞춤 추천 다시 받기';
  }
}

// ── Demo Tab: 시나리오 버튼 클릭 → 직접 실행 ─────────────
const DEMO_QUERIES = {
  1: `[대회 시나리오 1 — 암 완치자 인수 심사]

박*준(45세 남성)은 위암 2기로 3년 전 완치(수술+항암 치료)했으며 최근 건강검진 결과가 정상입니다.

다음 두 단계로 분석해 주세요.

① assess_cancer_survivor 도구로 이노베이션 존 RGST 데이터 기반 정밀 인수 심사를 실행하고 조건부 승인 여부와 보험료 할인율을 산출해 주세요.

② 심사 결과를 바탕으로 박*준 씨에게 실제로 가입 가능한 보험 상품을 search_insmarket_products로 조회하여 추천해 주세요. 암보험(질병보험)과 실손의료보험 각각 상위 3개 상품을 보험사명·상품명·월 보험료 기준으로 비교표로 제시해 주세요. 완치자 가입 가능 여부도 표시해 주세요.`,

  2: `[대회 시나리오 2 — AI 저위험군 보험료 할인]

이*현(38세 여성)은 5년 연속 건강검진 정상, BMI·혈압·혈당 정상, 비흡연, DICOM 영상 정상입니다.

다음 두 단계로 분석해 주세요.

① assess_low_risk_discount 도구로 AI 저위험군 할인율을 산출해 주세요.

② 이*현 씨에게 적합한 보험 상품을 search_insmarket_products로 조회하여 추천해 주세요. 실손의료보험·암보험·치아보험 각 상위 2~3개 상품을 보험사명·상품명·표준 월 보험료·할인 적용 후 예상 보험료 기준으로 비교표로 제시해 주세요.`,

  3: `[대회 시나리오 3 — 미세 영상 소견자 노-할증]

김*영(52세 남성)은 폐CT에서 6mm 소결절 소견이 발견됐으나 2년째 경과 관찰 중 변화 없음.

다음 두 단계로 분석해 주세요.

① assess_pacs_no_extra 도구로 광주TP DICOM AI 판독 결과 기반 노-할증 인수 여부를 판단해 주세요.

② 김*영 씨가 가입할 수 있는 보험 상품을 search_insmarket_products로 조회하여 추천해 주세요. 50대 남성 기준 실손의료보험·암보험 상위 3개 상품을 보험사명·상품명·월 보험료로 비교표를 제시하고, 소결절 소견자 가입 시 주의사항도 안내해 주세요.`,

  4: `[대회 시나리오 4 — 동적 보험료 캐시백]

최*민(41세 여성)은 라이프로그 기반 건강 점수가 1년간 25% 개선됐습니다. 현재 월 보험료 8만원.

다음 두 단계로 분석해 주세요.

① assess_dynamic_discount 도구로 동적 캐시백 금액을 산출해 주세요. (점수 개선 25%, 월보험료 80000원, 1년)

② 최*민 씨에게 적합한 보험 포트폴리오를 search_insmarket_products로 조회하여 추천해 주세요. 40대 여성 기준 실손의료보험·암보험·치아보험 상위 상품을 보험사명·상품명·월 보험료로 비교표를 제시하고, 캐시백 프로그램 연동 시 실질 비용도 함께 계산해 주세요.`,

  5: `[대회 시나리오 5 — 맞춤형 유병자 요율]

정*호(57세 남성)는 당뇨 진단을 받았지만 HbA1c 6.8%로 치료 반응이 우수합니다.

다음 두 단계로 분석해 주세요.

① assess_chronic_disease_rate 도구로 T200~T530 상병 + G1E 치료 반응 기반 맞춤형 유병자 요율을 산출해 주세요. (당뇨, 치료반응 우수, HbA1c 6.8)

② 정*호 씨가 가입 가능한 유병자 보험 상품을 search_insmarket_products로 조회하여 추천해 주세요. 50대 남성 기준 유병자 실손보험·당뇨합병증 특화 상품·간병보험 상위 3개 상품을 보험사명·상품명·월 보험료로 비교표를 제시해 주세요.`,

  6: `[대회 시나리오 6 — 씬파일러 Health-Credit 대안 신용평가]

이*진(29세 여성)은 금융 거래 이력이 부족한 씬파일러로 신용점수가 680점입니다. 4년 연속 건강검진 정상, 바이탈 안정도 상, BFC 분위 6. 전세자금 2억 대출 희망.

다음 두 단계로 분석해 주세요.

① assess_health_credit 도구로 G1E + 바이탈 안정도 + BFC 기반 Health-Credit 가산점과 금리 인하 혜택을 산출해 주세요. (연속검진 4년, 바이탈 안정도 상, 현재신용점수 680, 전세자금 2억)

② 이*진 씨에게 적합한 보험 상품도 search_insmarket_products로 조회하여 추천해 주세요. 30대 여성 기준 실손의료보험·암보험 상위 상품을 보험사명·상품명·월 보험료로 비교표를 제시하고, 건강 관리 지속 시 추가 혜택도 안내해 주세요.`,

  7: `[대회 시나리오 7 — 소상공인 건강 지속가능성 대출 우대]

오*석(48세 남성)은 8년째 소상공인 운영, 월 매출 800만원, 당뇨 치료 반응 우수. 3,000만원 사업자 대출 희망.

다음 두 단계로 분석해 주세요.

① assess_sme_health_loan 도구로 CDW 임상 수치 기반 건강 지속가능성 점수와 대출 한도 증액·금리 우대를 산출해 주세요.

② 오*석 씨에게 적합한 보험 상품도 search_insmarket_products로 조회하여 추천해 주세요. 40대 남성 기준 실손의료보험·당뇨 유병자 보험·간병보험 상위 상품을 보험사명·상품명·월 보험료로 비교표를 제시해 주세요. 대출 상환 보장 보험도 추천에 포함해 주세요.`,

  8: `[대회 시나리오 8 — 유병자·고령층 렌탈/할부 금융 승인]

윤*숙(68세 여성)은 위암 1기 완치 5년 후 현재 이상 없음. 냉장고 500만원 36개월 렌탈 신청.

다음 두 단계로 분석해 주세요.

① assess_rental_approval 도구로 cdw_ptn_hli + DEATH DB 기반 단기 건강 급변 위험을 분석하고 렌탈 승인 여부를 판단해 주세요. (위암 1기 완치, 단기 위험 낮음)

② 윤*숙 씨에게 적합한 보험 상품도 search_insmarket_products로 조회하여 추천해 주세요. 60대 여성 기준 실손의료보험·간병·치매보험 상위 상품을 보험사명·상품명·월 보험료로 비교표를 제시하고, 암 완치자 가입 가능 여부도 함께 안내해 주세요.`,

  9: `[대회 시나리오 9 — 미시 징후 사전 케어 암 중증화 차단]

박*호(52세 남성)는 내시경에서 위 미란 소견 발견, 2년 내 암 진행 위험 42%, 보험금 8,000만원 기준.

다음 두 단계로 분석해 주세요.

① assess_early_care 도구로 광주TP DICOM + T400 DB 기반 조기 개입 시 중증화 차단 효과와 보험사 절감 효과를 분석해 주세요. (위 미란 소견, 위험 42%, 조기 개입 적용)

② 박*호 씨에게 지금 당장 가입해야 할 보험 상품을 search_insmarket_products로 조회하여 추천해 주세요. 50대 남성 기준 암보험(질병보험)·실손의료보험·간병보험 상위 상품을 보험사명·상품명·월 보험료로 비교표를 제시하고, 조기 가입의 중요성도 강조해 주세요.`,

  10: `[대회 시나리오 10 — 중증 질환 전환 예측 대출 부실률 차단]

한*철(55세 남성)은 대출 잔액 2억원, CDW SOFA 점수 2.0, 2년 내 중증 질환 전환 위험 38%, 대출 상환 보험 미가입.

다음 두 단계로 분석해 주세요.

① assess_default_prevention 도구로 CDW SOFA + RGST 연계 부실 예상 손실과 상환 보험 연계 권고를 분석해 주세요.

② 한*철 씨에게 반드시 필요한 보험 상품을 search_insmarket_products로 조회하여 추천해 주세요. 50대 남성 기준 암보험·간병보험·실손의료보험 상위 상품을 보험사명·상품명·월 보험료로 비교표를 제시하고, 대출 상환 보장 보험 가입이 왜 필수인지도 설명해 주세요.`,

  11: `[대회 시나리오 11 — 건강체 특별약관 보험료 최대 할인]

강*원(43세 남성)은 5년 연속 건강검진 정상, 비흡연, BMI 21(정상), 혈압 정상, 공복혈당 정상입니다. 현재 표준체 기준 월 보험료 12만원.

다음 두 단계로 분석해 주세요.

① assess_healthy_body_discount 도구로 G1E 연속 건강검진 + 바이탈 전 항목 정상 기반 건강체 등급과 보험료 할인율을 산출해 주세요. (연속검진 5년, BMI 정상, 혈압 정상, 혈당 정상, 비흡연, 월보험료 12만원)

② 강*원 씨에게 건강체 특별약관 적용 가능한 보험 상품을 search_insmarket_products로 조회하여 추천해 주세요. 40대 남성 기준 종신보험·실손의료보험·암보험 상위 3개 상품을 보험사명·상품명·표준 월 보험료·건강체 적용 후 예상 보험료로 비교표를 제시해 주세요.`,

  12: `[대회 시나리오 12 — 건강체 건강담보대출 승인]

서*원(46세 여성)은 건강검진 4년 연속 정상, 바이탈 안정도 상, BFC 분위 6등급입니다. DSR 52%로 은행 모든 대출이 거절된 상황이며 생활자금 5,000만원이 필요합니다.

다음 두 단계로 분석해 주세요.

① assess_healthy_body_loan 도구로 G1E + 바이탈 기반 건강 자산 점수(HAS)를 산출하고 건강담보대출 승인 여부·한도·금리를 산출해 주세요. (연속검진 4년, 바이탈 상, BFC 6등급, DSR 52%, 대출 5000만원, 생활자금)

② 서*원 씨에게 적합한 보험 상품도 search_insmarket_products로 조회하여 추천해 주세요. 40대 여성 기준 실손의료보험·암보험·치아보험 상위 상품을 보험사명·상품명·월 보험료로 비교표를 제시하고, 건강 담보 대출 연계 보험 유지의 중요성도 안내해 주세요.`,

  13: `[대회 시나리오 13 — 위 내시경 용종 절제술 후 보험 가입 가능]

홍*종(50세 남성)은 2년 전 위내시경에서 관상선종(저등급) 8mm 발견 후 EMR(내시경 점막 절제술)로 절제했습니다. 병리 결과 양성(암세포 없음), 1년 추적 내시경 정상. 현재 수술 이력으로 전 보험사 가입 거절 중.

다음 두 단계로 분석해 주세요.

① assess_polyp_removal_eligibility 도구로 병리 DB + T400(상병) + DICOM 추적 내시경 기반 재발 위험을 분석하고 보험 가입 가능 여부를 판정해 주세요. (관상선종 저등급, 절제 후 2년, 병리 양성, 추적 내시경 정상, 용종 8mm)

② 홍*종 씨가 지금 가입 가능한 보험 상품을 search_insmarket_products로 조회하여 추천해 주세요. 50대 남성 기준 실손의료보험·암보험·간병보험 상위 3개 상품을 보험사명·상품명·월 보험료로 비교표를 제시하고, 내시경 용종 절제 이력자 가입 시 주의사항도 함께 안내해 주세요.`,

  14: `[대회 시나리오 14 — 신(新) 건강담보대출 — 막힌 대출 해결]

나*출(52세 남성)은 DSR 58%·LTV 82% 동시 초과로 전 금융기관 대출이 완전 봉쇄 상태입니다. 건강검진 3년 연속 정상, 바이탈 안정도 상, 라이프로그 건강 관리 점수 78점, BFC 분위 5등급. 생활자금 5,000만원 필요.

다음 두 단계로 분석해 주세요.

① assess_health_secured_loan 도구로 G1E + 바이탈 + 라이프로그 3종 결합 건강 자산 점수(HAS)를 산출하고 신(新) 건강담보대출 PLUS 승인 여부·한도·금리를 산출해 주세요. (연속검진 3년, 바이탈 상, 라이프로그 78점, BFC 5등급, DSR 58%, LTV 82%, 대출 5000만원)

② 나*출 씨에게 적합한 보험 상품도 search_insmarket_products로 조회하여 추천해 주세요. 50대 남성 기준 실손의료보험·암보험·간병보험 상위 상품을 보험사명·상품명·월 보험료로 비교표를 제시하고, 건강 자산 담보 대출과 보험 연계의 중요성도 함께 설명해 주세요.`,

  15: `[대회 시나리오 15 — 신용+건강 교차 역선택 탐지 언더라이팅]

강*민(42세 남성)은 최근 6개월간 신용점수가 780점 → 650점으로 급락(-130점)했으며, 3곳의 보험사에 동시에 사망보험금 1억원 규모 종신보험을 신청했습니다. 마지막 건강검진은 30개월 전이며, 기존 소액 보험에서 갑작스럽게 고액 보험으로 전환을 시도하고 있습니다.

다음 두 단계로 분석해 주세요.

① assess_adverse_selection_score 도구로 신용+건강 교차 AASI(역선택방지지수) 분석을 실행하고 역선택 위험 등급과 필요 조치를 산출해 주세요. (신용점수 650점, 6개월 -130점 급락, 보험금 10000만원, 검진 30개월 미수검, 복수 보험사 동시 신청, 고액 전환 true)

② 역선택 분석 결과를 바탕으로 보험사 입장에서의 심사 권고사항과, 동시에 강*민 씨가 정상적인 방법으로 가입 가능한 보험 상품(실손의료보험 등)을 search_insmarket_products로 조회하여 안내해 주세요.`,

  16: `[대회 시나리오 16 — 씬파일러 역선택 방지 & 포용 심사]

윤*아(28세 여성)는 사회초년생으로 CB 금융 이력이 전무하고, 건강검진을 한 번도 받은 적이 없습니다. 갑자기 사망보험금 8,000만원 규모의 종신보험 가입을 신청했으며, 바이탈 데이터도 없습니다.

다음 두 단계로 분석해 주세요.

① assess_thin_filer_adverse_selection 도구로 씬파일러 역선택 위험 분석을 실행하고 가입 가능 여부, 포용 금융 경로, 건강 데이터 제출 요청 방안을 산출해 주세요. (CB 이력 없음, 건강검진 0회, 보험금 8000만원, 갑작스러운 첫 신청, 바이탈 없음)

② 씬파일러이지만 역선택 위험이 없는 경우의 포용 보험 가입 경로를 안내하고, 윤*아 씨가 지금 당장 가입 가능한 보험 상품을 search_insmarket_products로 조회하여 20~30대 여성 기준 실손의료보험·암보험 상위 상품을 비교표로 제시해 주세요.`,
};
// DEMO_QUERIES는 현재 미사용 — 데모 시나리오는 /api/demo/run으로 직접 실행

// 데모 시나리오별 보험 상담 자연어 쿼리 — 의료·금융 용어 한글 병기
const DEMO_CHAT_QUERIES = {
  1:  `박*준(45세 남성)은 위암 2기로 3년 전 완치(수술+항암 치료)했으며 최근 건강검진 결과는 정상입니다. RGST(국립암센터 암등록 데이터베이스) 기반으로 정밀 인수 심사를 해주시고, 조건부 승인 여부와 보험료를 분석해주세요. 가입 가능한 암보험과 실손의료보험도 각 상위 3개씩 추천해주세요.`,
  2:  `이*현(38세 여성)은 5년 연속 건강검진 정상, BMI(체질량지수)·혈압·혈당 정상, 비흡연, DICOM(의료영상 디지털 포맷) 영상 정상인 저위험군입니다. AI 저위험군 보험료 할인율을 산출해주시고, 실손의료보험·암보험·치아보험 추천 상품을 할인 적용 후 보험료 기준으로 비교표로 제시해주세요.`,
  3:  `김*영(52세 남성)은 폐CT에서 6mm 소결절(작은 폐 내 음영) 소견이 있으나 2년 경과 관찰 중 변화가 없습니다. DICOM(의료영상 디지털 포맷) AI 판독 기반으로 노-할증 인수 여부를 판단해주시고, 50대 남성 기준 실손의료보험·암보험 상위 3개 상품을 비교표와 주의사항과 함께 추천해주세요.`,
  4:  `최*민(41세 여성)은 라이프로그(웨어러블·앱 기반 건강 활동 기록) 건강 점수가 1년간 25% 개선됐으며 현재 월 보험료는 8만원입니다. 동적 캐시백 금액을 산출해주시고, 40대 여성 기준 실손·암·치아보험 추천 상품을 캐시백 연동 실질 비용과 함께 비교표로 제시해주세요.`,
  5:  `정*호(57세 남성)는 당뇨 진단을 받았지만 HbA1c(당화혈색소: 최근 2~3개월 평균 혈당 수치) 6.8%로 치료 반응이 우수합니다. G1E(국가일반건강검진 데이터) 기반 맞춤형 유병자 요율을 산출해주시고, 50대 남성 유병자 실손보험·당뇨합병증 특화 상품·간병보험 상위 3개를 비교표로 추천해주세요.`,
  6:  `강*원(43세 남성)은 5년 연속 건강검진 정상, 비흡연, BMI(체질량지수) 21 정상, 혈압·혈당 정상이며 현재 표준체 기준 월 보험료 12만원입니다. 건강체 특별약관 등급과 보험료 할인율을 산출해주시고(연속검진 5년, 월보험료 12만원), 40대 남성 기준 건강체 특별약관 적용 가능한 종신·실손·암보험 추천 상품을 할인 전후 보험료 비교표로 제시해주세요.`,
  7:  `홍*종(50세 남성)은 2년 전 위내시경에서 관상선종(저등급, 암 전 단계 가능 용종) 8mm를 EMR(내시경 점막 절제술: 내시경으로 점막 병변을 절제하는 시술)로 제거했으며, 병리 결과 양성(암세포 없음), 1년 추적 내시경 정상입니다. 현재 수술 이력으로 전 보험사에서 가입이 거절된 상황입니다. 재발 위험 분석 후 보험 가입 가능 여부를 판정해주시고, 가입 가능한 실손·암·간병보험 상위 3개를 주의사항과 함께 추천해주세요.`,
  8:  `이*진(29세 여성)은 금융 거래 이력이 부족한 씬파일러(신용 이력 없는 사람)로 신용점수 680점이며, 4년 연속 건강검진 정상, 바이탈(혈압·맥박·체온 등 활력 징후) 안정도 상, BFC(건강보험료 분위: 소득 수준 지표) 6분위입니다. 전세자금 2억 대출을 희망합니다. G1E(건강검진 DB)·바이탈·BFC 기반 Health-Credit(건강 자산 기반 신용 평가) 가산점과 금리 인하 혜택을 분석해주시고(연속검진 4년, 바이탈 상, 신용 680, 전세 2억), 30대 여성 기준 실손·암보험도 추천해주세요.`,
  9:  `오*석(48세 남성)은 8년째 소상공인을 운영 중이며 월 매출 800만원, 당뇨 치료 반응 우수입니다. 3,000만원 사업자 대출을 희망합니다. CDW(임상 데이터 웨어하우스: 병원 진료·검사 기록 통합 DB) 임상 수치 기반 건강 지속가능성 점수와 대출 한도 증액·금리 우대를 분석해주시고, 40대 남성 기준 실손·당뇨 유병자·간병보험 추천 상품을 대출 상환 보장 보험 포함하여 비교표로 제시해주세요.`,
  10: `윤*숙(68세 여성)은 위암 1기 완치 5년 후 현재 이상이 없으며, 냉장고 500만원 36개월 렌탈을 신청했습니다. 건강 급변 위험 분석 후 렌탈 승인 여부를 판단해주시고(위암 1기 완치, 단기 위험 낮음), 60대 여성 기준 실손·간병·치매보험 추천 상품을 암 완치자 가입 가능 여부와 함께 비교표로 제시해주세요.`,
  11: `서*원(46세 여성)은 건강검진 4년 연속 정상, 바이탈(활력 징후) 안정도 상, BFC(건강보험료 분위) 6등급이며 DSR(총부채원리금상환비율: 연소득 대비 전체 대출 상환액 비율) 52%로 은행 대출이 모두 거절됐습니다. 생활자금 5,000만원이 필요합니다. HAS(건강자산점수: 건강 데이터 기반 신용 보완 점수)를 산출하고 건강담보대출 승인·한도·금리를 분석해주시고(연속검진 4년, 바이탈 상, DSR 52%, 생활자금 5000만원), 40대 여성 기준 실손·암·치아보험도 추천해주세요.`,
  12: `나*출(52세 남성)은 DSR(총부채원리금상환비율) 58%·LTV(주택담보인정비율: 주택가격 대비 대출 한도 비율) 82% 동시 초과로 전 금융기관 대출이 봉쇄됐습니다. 건강검진 3년 연속 정상, 바이탈(활력 징후) 안정도 상, 라이프로그 78점, BFC(보험료 분위) 5등급이며 생활자금 5,000만원이 필요합니다. G1E(건강검진 DB)·바이탈·라이프로그 결합 HAS(건강자산점수)를 산출하고 신(新) 건강담보대출 PLUS 승인·한도·금리를 분석해주시고, 50대 남성 실손·암·간병보험도 추천해주세요.`,
  13: `강*민(42세 남성)은 최근 6개월간 신용점수가 780점에서 650점으로 급락(-130점)했으며, 3개 보험사에 동시에 사망보험금 1억원 종신보험을 신청했습니다. 마지막 검진은 30개월 전이고 소액에서 고액으로 갑작스럽게 전환 신청 중입니다. AASI(역선택방지지수: 보험 악용 가능성을 수치화한 지표) 기반 역선택 위험을 분석해주시고(신용 650점, 6개월 -130점, 보험금 1억, 검진 30개월 미수검, 복수사 동시 신청), 정상적으로 가입 가능한 보험 상품도 안내해주세요.`,
  14: `윤*아(28세 여성)는 사회초년생으로 CB(신용조회기관, Credit Bureau) 금융 이력이 전무하고, 건강검진을 한 번도 받은 적이 없습니다. 갑자기 사망보험금 8,000만원 종신보험을 신청했으며 바이탈(활력 징후) 데이터도 없습니다. 씬파일러(신용·건강 이력 없는 사람) 역선택 위험을 분석하고 가입 가능 여부·포용 금융 경로·건강 데이터 제출 방안을 산출해주시고, 20~30대 여성 기준 포용 보험 가입 경로와 추천 상품도 안내해주세요.`,
  15: `박*호(52세 남성)는 내시경에서 위 미란(위 점막 표면이 얕게 패인 염증 소견) 소견이 발견됐으며 2년 내 암 진행 위험 42%, 보험금 8,000만원 기준입니다. DICOM(의료영상 디지털 포맷)·T400(소화기계 상병 분류 코드) 기반 조기 개입 시 중증화 차단 효과와 보험사 절감 효과를 분석해주시고, 50대 남성 기준 암·실손·간병보험 지금 당장 가입해야 할 상품을 조기 가입 중요성과 함께 추천해주세요.`,
  16: `한*철(55세 남성)은 대출 잔액 2억원, SOFA(장기부전 중증도 점수: 수치 높을수록 중증) 2.0, 2년 내 중증 질환 전환 위험 38%이며 대출 상환 보험이 미가입 상태입니다. CDW(임상 데이터 웨어하우스)·RGST(암등록 DB) 연계로 부실 예상 손실과 상환 보험 연계 권고를 분석해주시고, 50대 남성 기준 암·간병·실손보험 필수 가입 상품을 대출 상환 보장 보험 필요성과 함께 추천해주세요.`,
};

async function demoSend(num) {
  const chatQuery = DEMO_CHAT_QUERIES[num];
  if (!chatQuery) return;
  if (isLoading) return;

  // 보험 상담 탭으로 전환
  switchTabDirect('chat');
  window.scrollTo({ top: 0, behavior: 'smooth' });

  addMessage('user', chatQuery);
  isLoading = true;
  document.getElementById('send').disabled = true;

  const { bubble, toolStatus } = createStreamingBubble();
  let fullText = '';
  let cursor = null;
  function startCursor() { if (!cursor) { cursor = document.createElement('span'); cursor.className = 'stream-cursor'; bubble.appendChild(cursor); } }
  function removeCursor() { if (cursor) { cursor.remove(); cursor = null; } }

  try {
    const r = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: chatQuery, session_id: SESSION_ID }),
    });
    if (!r.ok) {
      bubble.innerHTML = '서버 오류가 발생했습니다.';
    } else {
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let event;
          try { event = JSON.parse(line.slice(6)); } catch { continue; }
          if (event.type === 'token') {
            fullText += event.text;
            bubble.innerHTML = marked.parse(preprocessMd(fullText));
            startCursor();
            scrollToBottom();
          } else if (event.type === 'tool_start') {
            toolStatus.textContent = TOOL_LABELS[event.tool] || '분석 중...';
            toolStatus.style.display = 'block';
          } else if (event.type === 'tool_done') {
            toolStatus.style.display = 'none';
          } else if (event.type === 'done') {
            fullText = event.full_text || fullText;
            bubble.innerHTML = addLinksToTables(marked.parse(preprocessMd(fullText)));
            toolStatus.style.display = 'none';
            removeCursor();
            scrollToBottom();
          } else if (event.type === 'error') {
            bubble.innerHTML = '오류: ' + event.message;
            toolStatus.style.display = 'none';
            removeCursor();
          }
        }
      }
      removeCursor();
    }
  } catch (e) {
    bubble.innerHTML = '서버 연결 오류가 발생했습니다.';
  }
  isLoading = false;
  document.getElementById('send').disabled = false;
}

function renderDemoResult(r, num) {
  if (!r) return '<p style="color:#dc2626">결과 없음</p>';

  const badge = (txt, color) =>
    `<span style="display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700;background:${color[0]};color:${color[1]}">${txt}</span>`;

  // Before / After
  const beforeAfter = (r.before || r.after) ? `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0">
      ${r.before ? `<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:10px;font-size:12px"><span style="font-weight:700;color:#dc2626">Before</span><div style="margin-top:4px;color:#334155">${r.before}</div></div>` : ''}
      ${r.after  ? `<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:10px;font-size:12px"><span style="font-weight:700;color:#16a34a">After</span><div style="margin-top:4px;color:#334155">${r.after}</div></div>` : ''}
    </div>` : '';

  // 핵심 분석 데이터 (시나리오별 주요 필드 자동 추출)
  const analysisKeys = [
    'underwriting','risk_assessment','cashback','rate_analysis','pacs_analysis',
    'credit_score_data','loan_details','approval_result','care_result','default_risk',
    'discount_result','loan_result','eligibility_result','secured_loan_result',
    'aasi_analysis','thin_filer_analysis','health_credit_data','sme_result',
    'rental_result','has_result',
  ];
  let analysisHtml = '';
  for (const key of analysisKeys) {
    if (!r[key]) continue;
    const obj = r[key];
    const rows = Object.entries(obj)
      .filter(([k, v]) => v !== null && v !== undefined && typeof v !== 'object')
      .map(([k, v]) => {
        const label = k.replace(/_/g, ' ');
        const isGood = typeof v === 'boolean' ? v : String(v).includes('승인') || String(v).includes('정상') || String(v).includes('가능');
        const isBad  = String(v).includes('거절') || String(v).includes('불가') || String(v).includes('고위험');
        const valColor = isBad ? '#dc2626' : (isGood ? '#16a34a' : '#1e293b');
        return `<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #f1f5f9;font-size:12px"><span style="color:#64748b">${label}</span><span style="font-weight:700;color:${valColor}">${v}</span></div>`;
      }).join('');
    if (rows) {
      analysisHtml = `<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;margin:8px 0">${rows}</div>`;
      break;
    }
  }

  // 이노베이션 존 데이터
  const inno = r.innovation_zone_data;
  const innoHtml = inno ? `
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px;margin:8px 0;font-size:11.5px">
      <span style="font-weight:700;color:#1e40af">이노베이션 존 데이터</span>
      <div style="margin-top:4px;color:#1d4ed8">${(inno.tables||[]).join(' · ')}</div>
      ${inno.evidence ? `<div style="margin-top:4px;color:#3b82f6">${inno.evidence}</div>` : ''}
    </div>` : '';

  // Impact
  const impact = r.impact;
  const impactHtml = impact ? `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:8px 0">
      ${Object.entries(impact).map(([k,v]) => `
        <div style="background:#f8fafc;border-radius:8px;padding:8px;font-size:11.5px">
          <div style="font-weight:700;color:#475569;margin-bottom:3px">${k}</div>
          <div style="color:#334155">${v}</div>
        </div>`).join('')}
    </div>` : '';

  // 포용 경로 (S16)
  const pathHtml = r.inclusion_path ? `
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:10px;margin:8px 0;font-size:12px">
      <div style="font-weight:700;color:#166534;margin-bottom:6px">포용 금융 경로</div>
      ${r.inclusion_path.map(p => `<div style="color:#15803d;padding:2px 0">→ ${p}</div>`).join('')}
    </div>` : '';

  return `
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:18px;margin-top:12px">
      <div style="font-size:13px;font-weight:800;color:#1e293b;margin-bottom:4px">${r.scenario || ('시나리오 ' + num)}</div>
      <div style="font-size:12px;color:#64748b;margin-bottom:12px">${r.persona_summary || ''}</div>
      ${beforeAfter}
      ${analysisHtml}
      ${innoHtml}
      ${pathHtml}
      ${impactHtml}
    </div>`;
}

// 초기화
// ══════════════════════════════════════════════════════════
// DIOBIO 웰니스 체크 — 설문 & 결과 로직
// ══════════════════════════════════════════════════════════
const DB = {
  step: 1,
  answers: { target: null, age: null, pattern: null, concerns: [], lifestyle: {}, supp: {}, safety: [] }
};

const DB_RESULTS = {
  energy: {
    icon: '⚡', type: 'Energy Low Balance Type', name: '에너지 회복이 필요한 유형',
    desc: '피로, 활력 저하, 회복력 감소가 함께 나타나는 유형입니다. 만성 피로의 원인은 영양 불균형, 수면 부족, 생활습관 복합 요인인 경우가 많습니다.',
    food: '달걀·닭가슴살·콩류(단백질), 견과류, 올리브오일, 현미·잡곡, 녹색 채소',
    exercise: '주 2~3회 30분 걷기부터 시작 · 가벼운 스트레칭 · 과도한 운동은 오히려 피로 악화',
    supp: '비타민 B군 · 철분(여성) · 마그네슘 · 코큐텐(CoQ10) · 비타민D',
    hospital: '갑상선 기능 저하, 빈혈 의심 시 내분비내과 상담 권장',
    travel: '자연 속 산림 치유형 리트릿 · 온천 휴양 · 조용한 힐링 숙소'
  },
  skin_gut: {
    icon: '🌸', type: 'Skin-Gut Balance Type', name: '피부·장건강 관리가 필요한 유형',
    desc: '피부 트러블과 소화·장 건강이 함께 고민인 유형입니다. 피부와 장은 긴밀히 연결된 "장-피부 축"으로, 장내 환경 개선이 피부에도 긍정적인 영향을 줍니다.',
    food: '김치·요거트(발효식품), 등 푸른 생선(오메가3), 다채로운 채소, 충분한 수분 섭취',
    exercise: '가벼운 유산소(속보·자전거) · 요가·필라테스 · 규칙적 배변 리듬 형성',
    supp: '프로바이오틱스 · 오메가3 · 비타민C · 아연 · 콜라겐(선택)',
    hospital: '만성 소화불량, 피부 트러블 지속 시 소화기내과·피부과 상담 권장',
    travel: '해양 치유형(해변·바다 공기) · 해독 온천 · 건강 식단 중심 리트릿'
  },
  hair: {
    icon: '💫', type: 'Hair Nutrition Balance Type', name: '모발·영양 상태 점검이 필요한 유형',
    desc: '모발 건강은 체내 영양 상태의 직접적인 신호입니다. 단백질·철분·아연·비오틴 부족이 원인인 경우가 많으며, 조기 관리가 중요합니다.',
    food: '달걀·닭가슴살·두부(단백질), 검은콩·검은깨, 견과류, 해조류(요오드), 굴(아연)',
    exercise: '두피 혈류 개선 마사지(매일 3~5분) · 스트레칭 · 과도한 다이어트 금지',
    supp: '바이오틴(비타민B7) · 아연 · 철분 · 비타민D · 모발 전용 멀티미네랄',
    hospital: '갑작스러운 심한 탈모·원형탈모 시 피부과(탈모 클리닉) 조기 상담 권장',
    travel: '해독·디톡스 리트릿 · 산림 공기 휴양 · 스트레스 해소 중심 여행'
  },
  sleep_stress: {
    icon: '🌙', type: 'Sleep-Stress Balance Type', name: '수면·스트레스 루틴 관리가 필요한 유형',
    desc: '수면의 질 저하와 만성 스트레스가 복합적으로 나타나는 유형입니다. 코르티솔 과부하와 멜라토닌 리듬 교란이 주요 원인이며, 루틴 개선이 핵심입니다.',
    food: '바나나·체리(트립토판·멜라토닌), 두부·연어, 캐모마일차·라벤더차, 마그네슘 풍부 식품',
    exercise: '저녁 30분 가벼운 산책 · 수면 전 요가·명상(5~10분) · 취침 2시간 전 격렬 운동 금지',
    supp: '마그네슘 · L-테아닌 · GABA · 비타민B군 · 아슈와간다(적응원 허브)',
    hospital: '수면 문제가 3개월 이상 지속되면 신경과·정신건강의학과 상담 권장',
    travel: '숲 명상 리트릿 · 한적한 산속 힐링 · 디지털 디톡스 숙소'
  },
  metabolic: {
    icon: '🔥', type: 'Metabolic Balance Type', name: '대사·체중 밸런스 개선이 필요한 유형',
    desc: '체중 조절 어려움, 부종, 식습관 불균형이 함께 나타나는 유형입니다. 대사 건강은 식단·운동·수면이 세트로 작동하며, 한 가지만으로는 효과가 제한적입니다.',
    food: '저당·고섬유 식단, 충분한 단백질, 저칼로리 채소, 발효식품, 설탕·가공식품 줄이기',
    exercise: '근력 운동 + 유산소 병행(주 3~4회) · 공복 후 식전 간단 걷기 · 일상 활동량 늘리기',
    supp: '식이섬유(차전자피) · 크롬 · 비타민D · 오메가3 · 마그네슘',
    hospital: '대사증후군 의심, 갑상선 이상, 다낭성 난소증후군 시 내분비내과 상담',
    travel: '디톡스 리트릿 · 단식·해독 프로그램 · 활동 중심 에코 리트릿'
  },
  total: {
    icon: '🌈', type: 'Total Balance Type', name: '복합적 건강 밸런스 관리가 필요한 유형',
    desc: '여러 건강 고민이 복합적으로 나타나는 유형입니다. 특정 영양제 하나보다는 전반적인 생활습관 점검과 기초 건강관리부터 시작하는 것이 가장 효과적입니다.',
    food: '균형 잡힌 식단 전반 개선 · 가공식품·배달 음식 줄이기 · 규칙적 식사 리듬',
    exercise: '일상 활동량 증가(하루 30분 걷기)부터 시작 · 과도한 목표 설정 금지',
    supp: '종합 멀티비타민·미네랄부터 시작 · 프로바이오틱스 · 오메가3 · 비타민D',
    hospital: '3년 이상 종합건강검진을 받지 않았다면 종합검진 우선 권장',
    travel: '회복 중심 웰니스 패키지 · 자연 치유 리트릿 · 번아웃 회복 프로그램'
  }
};

function dbStart() {
  document.getElementById('db-landing').style.display = 'none';
  document.getElementById('db-survey').style.display = 'block';
  dbGoTo(1);
}

function dbGoTo(n) {
  for (let i = 1; i <= 6; i++) {
    const el = document.getElementById('db-s' + i);
    if (el) el.style.display = (i === n ? 'block' : 'none');
  }
  DB.step = n;
  const pct = Math.round((n - 1) / 6 * 100);
  document.getElementById('db-pbar-fill').style.width = pct + '%';
  document.getElementById('db-step-lbl').textContent = 'Step ' + n + ' / 6';
  document.getElementById('db-step-pct').textContent = pct + '%';
  document.getElementById('db-btn-prev').style.display = n > 1 ? 'block' : 'none';
  document.getElementById('db-btn-next').textContent = n === 6 ? '✅ 결과 보기' : '다음 →';
  document.querySelector('.diobio-panel').scrollTop = 0;
}

function dbPick(el) {
  const g = el.dataset.g;
  document.querySelectorAll('.db-opt[data-g="' + g + '"]').forEach(e => e.classList.remove('sel'));
  el.classList.add('sel');
  DB.answers[g] = el.dataset.v;
}

function dbMulti(el, max) {
  if (el.classList.contains('sel')) {
    el.classList.remove('sel');
    DB.answers.concerns = DB.answers.concerns.filter(v => v !== el.dataset.v);
  } else {
    if (DB.answers.concerns.length >= max) {
      el.style.animation = 'none';
      el.offsetHeight;
      el.style.animation = '';
      return;
    }
    el.classList.add('sel');
    DB.answers.concerns.push(el.dataset.v);
  }
}

function dbQ(el) {
  const q = el.dataset.q;
  document.querySelectorAll('.db-q-o[data-q="' + q + '"]').forEach(e => e.classList.remove('sel'));
  el.classList.add('sel');
  DB.answers.lifestyle[q] = el.dataset.v;
}

function dbToggleSupp(show) {
  document.getElementById('db-supp-detail').style.display = show ? 'block' : 'none';
}

function dbChkToggle(lbl) {
  const cb = lbl.querySelector('input[type=checkbox]');
  const checked = cb.checked;
  lbl.classList.toggle('on', checked);
  const v = cb.value;
  if (checked) { if (!DB.answers.safety.includes(v)) DB.answers.safety.push(v); }
  else { DB.answers.safety = DB.answers.safety.filter(x => x !== v); }
}

function dbNext() {
  const s = DB.step;
  if (s === 1 && !DB.answers.target) { alert('대상을 선택해 주세요.'); return; }
  if (s === 2 && (!DB.answers.age || !DB.answers.pattern)) { alert('연령대와 생활 패턴을 모두 선택해 주세요.'); return; }
  if (s === 3 && DB.answers.concerns.length === 0) { alert('건강 고민을 최소 1가지 선택해 주세요.'); return; }
  if (s === 6) { dbShowResult(); return; }
  dbGoTo(s + 1);
}

function dbPrev() { if (DB.step > 1) dbGoTo(DB.step - 1); }

function dbCalcType() {
  const sc = { energy: 0, skin_gut: 0, hair: 0, sleep_stress: 0, metabolic: 0 };
  const map = { tired:'energy', skin:'skin_gut', gut:'skin_gut', hair:'hair', sleep:'sleep_stress',
                weight:'metabolic', age40:'energy', men:'energy', kidcare:'energy',
                burnout:'sleep_stress', unknown: null };
  DB.answers.concerns.forEach(c => {
    const t = map[c];
    if (t) sc[t] += 3; else Object.keys(sc).forEach(k => sc[k] += 1);
  });
  const ls = DB.answers.lifestyle;
  if (ls.breakfast === 'rarely')    { sc.metabolic += 1; sc.energy += 1; }
  if (ls.protein === 'rarely')      { sc.hair += 1; sc.energy += 1; }
  if (ls.veg === 'rarely')          { sc.skin_gut += 1; sc.metabolic += 1; }
  if (ls.dining === 'often')        { sc.metabolic += 1; sc.skin_gut += 1; }
  if (ls.sugar === 'often')         { sc.metabolic += 1; sc.skin_gut += 1; }
  if (ls.sleep === 'less5' || ls.sleep === 'less6') { sc.sleep_stress += 2; sc.energy += 1; }
  if (ls.exercise === 'rarely')     { sc.metabolic += 1; sc.energy += 1; }
  if (ls.walk === 'rarely')         { sc.metabolic += 1; }
  if (ls.stress === 'high')         { sc.sleep_stress += 2; sc.energy += 1; }
  if (['40s','50s','60s'].includes(DB.answers.age)) sc.energy += 1;
  if (DB.answers.age === '60s')     sc.metabolic += 1;

  const entries = Object.entries(sc).sort((a,b) => b[1]-a[1]);
  const top = entries[0][1];
  const topN = entries.filter(e => e[1] === top).length;
  const activeN = Object.values(sc).filter(v => v >= 3).length;
  if (topN >= 3 || activeN >= 3 || DB.answers.concerns.length >= 3) return 'total';
  return entries[0][0];
}

function dbShowResult() {
  document.getElementById('db-survey').style.display = 'none';
  const r = document.getElementById('db-result');
  r.style.display = 'block';
  r.scrollTop = 0;
  document.querySelector('.diobio-panel').scrollTop = 0;

  const type = dbCalcType();
  DB.currentType = type;
  const d = DB_RESULTS[type];
  const medFlag = DB.answers.safety.length >= 2;

  const medHtml = medFlag ? `<div class="db-med-alert">⚠️ <strong>병원 상담을 먼저 권장드려요</strong><br>안전 확인 질문에서 의료 전문가 상담이 필요한 항목이 확인됐습니다. 영양제나 식품 솔루션보다 먼저 담당 의사와 상의해 주세요.</div>` : '';

  const glp1Html = type === 'metabolic' ? `
    <div class="db-glp1-banner">
      <div class="db-glp1-title">💉 GLP-1 기반 AI 원격 의료 상담</div>
      <div class="db-glp1-body">
        대사·비만 유형으로 확인됐습니다. GLP-1 비만 치료제(세마글루타이드·리라글루타이드)는
        식욕 억제·혈당 조절에 효과가 입증된 최신 옵션입니다.<br>
        DIOBIO는 AI 기반 원격 의료 플랫폼과 연계하여 전문의 상담 없이도 비대면으로
        처방 검토 및 모니터링을 받을 수 있도록 연결해 드립니다.
      </div>
      <button class="db-glp1-cta" onclick="dbOpenKakao()">AI 원격 상담 신청하기 →</button>
    </div>` : '';

  document.getElementById('db-result-body').innerHTML = `
    <div class="db-res-hero">
      <div class="db-res-icon">${d.icon}</div>
      <div class="db-res-type">${d.type}</div>
      <div class="db-res-name">당신은 <br>${d.name}입니다</div>
      <div class="db-res-desc">${d.desc}</div>
    </div>
    ${medHtml}
    ${glp1Html}
    <div class="db-sol-hd">맞춤 솔루션</div>
    <div class="db-sol-grid">
      <div class="db-sol-card"><div class="db-sol-card-h">🥗 식품 솔루션</div><div class="db-sol-card-b">${d.food}</div></div>
      <div class="db-sol-card"><div class="db-sol-card-h">🏃 운동 솔루션</div><div class="db-sol-card-b">${d.exercise}</div></div>
      <div class="db-sol-card"><div class="db-sol-card-h">💊 영양제 솔루션</div><div class="db-sol-card-b">${d.supp}</div></div>
      <div class="db-sol-card"><div class="db-sol-card-h">🏥 병원 상담</div><div class="db-sol-card-b">${d.hospital}</div></div>
    </div>
    <div class="db-sol-card" style="margin-bottom:20px"><div class="db-sol-card-h">✈️ 웰니스 여행</div><div class="db-sol-card-b">${d.travel}</div></div>
    <div class="db-ctas">
      <button class="db-btn-kakao" onclick="dbOpenKakao()">💬 카카오 상담하기</button>
      <button class="db-btn-green" onclick="dbOpenDiobioSite()">🌿 DIOBIO 구독 신청하기</button>
      <div class="db-btn-row">
        <button class="db-btn-out" onclick="dbOpenModal('db-modal-kit')">🔬 검사 키트 신청</button>
        <button class="db-btn-out" onclick="dbOpenFood(DB.currentType)">🛍️ 추천 식품 보기</button>
      </div>
      <button class="db-btn-out" onclick="dbOpenTravel(DB.currentType)">✈️ 웰니스 여행 보기</button>
    </div>
    <div class="db-privacy" style="margin-top:20px">
      DIOBIO Balance Check 결과 안내와 상담을 위해 이름, 연락처, 설문 답변을 수집합니다.
      본 서비스는 질병의 진단이나 치료를 목적으로 하지 않으며, 건강한 생활습관과 영양 균형
      관리를 위한 참고 정보를 제공합니다. 특정 증상이나 질환이 의심되는 경우 전문 의료기관
      상담이 권장됩니다.
    </div>
    <button class="db-restart" onclick="dbRestart()">🔄 처음부터 다시 하기</button>
  `;
}

// ── DIOBIO Modal helpers ──────────────────────────────────────
function dbOpenModal(id) { document.getElementById(id).classList.add('open'); }
function dbCloseModal(id) { document.getElementById(id).classList.remove('open'); }
function dbOverlayClose(e, id) { if (e.target === e.currentTarget) dbCloseModal(id); }

function dbOpenKakao() {
  window.open('http://pf.kakao.com/_xcPnxnX/chat', '_blank');
}
function dbOpenKakaoChannel() {
  window.open('http://pf.kakao.com/_xcPnxnX', '_blank');
}
function dbOpenDiobioSite() {
  window.open('/diobio', '_blank');
}

function dbSubmitKit() {
  const type  = document.getElementById('db-kit-type').value;
  const name  = document.getElementById('db-kit-name').value.trim();
  const phone = document.getElementById('db-kit-phone').value.trim();
  const addr  = document.getElementById('db-kit-addr').value.trim();
  if (!type || !name || !phone) { alert('검사 종류, 이름, 연락처를 입력해 주세요.'); return; }
  const label = { mineral:'모발 미네랄 검사', nutrition:'개인 영양 리포트', premium:'프리미엄 종합 리포트' }[type];
  alert('신청이 완료됐습니다!\\n\\n' + name + '님의 [' + label + '] 키트를\\n' + (addr || '입력한 주소') + '로 2~3 영업일 내 발송해 드립니다.\\n카카오 또는 문자로 발송 안내드립니다.');
  dbCloseModal('db-modal-kit');
}

const DB_FOODS = {
  energy: [
    { icon:'🫒', name:'엑스트라버진 올리브오일', desc:'에너지 대사에 필수인 건강 지방, 항산화 폴리페놀 풍부', tags:['에너지 대사','항산화','심혈관'], url:'https://search.shopping.naver.com/search/all?query=엑스트라버진+올리브오일' },
    { icon:'🥜', name:'오메가3 견과류 믹스', desc:'호두·아몬드·캐슈넛 혼합, 활력 회복에 도움되는 불포화지방', tags:['피로 회복','뇌 건강','항염'], url:'https://search.shopping.naver.com/search/all?query=오메가3+견과류+믹스' },
    { icon:'🥚', name:'방목란 단백질 팩(12구)', desc:'완전 단백질·비타민B12·철분 함유, 에너지 생성 지원', tags:['단백질','철분','B12'], url:'https://search.shopping.naver.com/search/all?query=방목란+12구' },
    { icon:'🌾', name:'멀티그레인 오트밀', desc:'복합탄수화물로 혈당 안정, 지속적인 에너지 공급', tags:['저GI','식이섬유','포만감'], url:'https://search.shopping.naver.com/search/all?query=멀티그레인+오트밀' },
  ],
  skin_gut: [
    { icon:'🥗', name:'유기농 발효 건강식품 세트', desc:'김치·된장·청국장 발효 농축 분말, 장내 유익균 증식 도움', tags:['프로바이오틱스','장건강','면역'], url:'https://search.shopping.naver.com/search/all?query=유기농+발효+건강식품' },
    { icon:'🫒', name:'엑스트라버진 올리브오일', desc:'폴리페놀 함유, 피부 항산화 및 장 점막 보호', tags:['피부','항산화','항염'], url:'https://search.shopping.naver.com/search/all?query=엑스트라버진+올리브오일' },
    { icon:'🐟', name:'DIOFARM 오메가3 오일', desc:'정제 어유 오메가3, EPA+DHA 풍부, 피부 장벽 강화', tags:['피부 장벽','오메가3','항염'], url:'https://search.shopping.naver.com/search/all?query=오메가3+오일+EPA+DHA' },
    { icon:'🍵', name:'콤부차 발효 음료 키트', desc:'홍차버섯 발효 DIY 키트, 장내 환경 개선', tags:['발효','프로바이오틱스','디톡스'], url:'https://search.shopping.naver.com/search/all?query=콤부차+발효+키트' },
  ],
  hair: [
    { icon:'🖤', name:'검은콩·검은깨 파우더', desc:'안토시아닌·이소플라본 풍부, 모발 색소·강도 유지에 도움', tags:['모발 강화','안토시아닌','단백질'], url:'https://search.shopping.naver.com/search/all?query=검은콩+검은깨+파우더' },
    { icon:'🥜', name:'아마씨·호두 믹스', desc:'오메가3·아연·비타민E 복합, 두피 혈류 개선', tags:['두피 건강','아연','오메가3'], url:'https://search.shopping.naver.com/search/all?query=아마씨+호두+믹스' },
    { icon:'🌊', name:'해조류 믹스(미역·다시마·톳)', desc:'요오드·칼슘·철분 풍부, 갑상선 기능 및 모발 성장 지원', tags:['요오드','칼슘','모발 성장'], url:'https://search.shopping.naver.com/search/all?query=해조류+미역+다시마+톳+건강식품' },
    { icon:'🦪', name:'굴 농축 분말', desc:'아연 최고 함유 식품, 케라틴 합성 지원', tags:['아연','케라틴','단백질'], url:'https://search.shopping.naver.com/search/all?query=굴+농축+분말+아연' },
  ],
  sleep_stress: [
    { icon:'🍌', name:'건바나나 & 체리 믹스', desc:'트립토판·멜라토닌 전구체 함유, 자연스러운 수면 유도', tags:['수면','멜라토닌','트립토판'], url:'https://search.shopping.naver.com/search/all?query=건바나나+체리+수면+건강식품' },
    { icon:'🌸', name:'캐모마일·라벤더 허브티 세트', desc:'GABA 활성화 도움, 취침 전 긴장 완화', tags:['릴렉스','GABA','카페인프리'], url:'https://search.shopping.naver.com/search/all?query=캐모마일+라벤더+허브티' },
    { icon:'🍫', name:'다크초콜릿(85%+)', desc:'마그네슘 풍부, 세로토닌 전구체 함유, 항산화', tags:['마그네슘','세로토닌','항산화'], url:'https://search.shopping.naver.com/search/all?query=다크초콜릿+85프로+건강' },
    { icon:'🫘', name:'두부·템페 단백질 세트', desc:'완전 단백질 + 이소플라본, 스트레스 호르몬 완화 도움', tags:['단백질','이소플라본','호르몬'], url:'https://search.shopping.naver.com/search/all?query=템페+두부+단백질+건강식품' },
  ],
  metabolic: [
    { icon:'🫒', name:'엑스트라버진 올리브오일', desc:'인슐린 감수성 개선, GLP-1 분비 촉진에 도움되는 건강 지방', tags:['대사','인슐린','GLP-1'], url:'https://search.shopping.naver.com/search/all?query=엑스트라버진+올리브오일+대사' },
    { icon:'🌾', name:'차전자피(실리움허스크)', desc:'수용성 식이섬유, 혈당 스파이크 억제, 포만감 증가', tags:['혈당 조절','식이섬유','다이어트'], url:'https://search.shopping.naver.com/search/all?query=차전자피+실리움허스크' },
    { icon:'🥦', name:'브로콜리·컬리플라워 분말', desc:'설포라판 함유, 대사 효소 활성화, 디톡스 지원', tags:['설포라판','디톡스','항산화'], url:'https://search.shopping.naver.com/search/all?query=브로콜리+컬리플라워+분말+설포라판' },
    { icon:'🫙', name:'애플사이다 비니거', desc:'혈당 조절, 인슐린 감수성, 지방 분해 효소 활성화', tags:['혈당','인슐린','지방 대사'], url:'https://search.shopping.naver.com/search/all?query=애플사이다+비니거+건강' },
  ],
  total: [
    { icon:'🎁', name:'DIOBIO 웰니스 스타터 패키지', desc:'올리브오일+견과류+발효식품+허브티 4종 구성, 균형 잡힌 시작', tags:['균형','입문','패키지'], url:'https://search.shopping.naver.com/search/all?query=웰니스+건강식품+스타터+패키지' },
    { icon:'🥜', name:'오메가3 견과류 믹스', desc:'뇌 건강·심혈관·항염 복합 효과, 매일 한 줌 시작', tags:['뇌 건강','항염','일상'], url:'https://search.shopping.naver.com/search/all?query=오메가3+견과류+믹스' },
    { icon:'🌾', name:'통곡물 오트밀 프리미엄', desc:'하루를 시작하는 기초 영양, 식이섬유+단백질+복합탄수화물', tags:['기초 영양','아침','식이섬유'], url:'https://search.shopping.naver.com/search/all?query=통곡물+오트밀+프리미엄' },
    { icon:'🫙', name:'유기농 발효 건강식품 세트', desc:'전반적인 장내 환경 개선, 면역·소화·피부 복합 지원', tags:['면역','소화','피부'], url:'https://search.shopping.naver.com/search/all?query=유기농+발효+건강식품' },
  ],
};

function dbOpenFood(type) {
  const foods = DB_FOODS[type] || DB_FOODS.total;
  const cards = foods.map(f => `
    <div class="db-food-card">
      <div style="font-size:30px;text-align:center;margin-bottom:8px">${f.icon}</div>
      <div class="db-food-card-name">${f.name}</div>
      <div class="db-food-card-desc">${f.desc}</div>
      <div class="db-food-tags">${f.tags.map(t => '<span class="db-food-tag">' + t + '</span>').join('')}</div>
      ${f.url ? `<a href="${f.url}" target="_blank" rel="noopener noreferrer" class="db-food-link">상품 보기 →</a>` : ''}
    </div>`).join('');
  document.getElementById('db-food-content').innerHTML = '<div class="db-food-grid">' + cards + '</div>';
  dbOpenModal('db-modal-food');
}

const DB_TRAVELS = {
  energy: [
    { icon: '🌲', name: '강원도 평창 산림치유원', desc: '피톤치드 가득한 치유의 숲 속에서 피로를 풀고 생체 리듬을 회복하는 1박2일 산림 리트릿 프로그램.', tags: ['산림치유', '피로회복', '1박2일'], url: 'https://search.naver.com/search.naver?query=평창+산림치유원+웰니스' },
    { icon: '♨️', name: '충남 아산 온천 리조트', desc: '천연 온천수로 근육 피로를 풀고 혈액 순환을 개선하는 온천 힐링 패키지. 아로마 마사지 포함.', tags: ['온천', '마사지', '힐링'], url: 'https://search.naver.com/search.naver?query=아산+스파비스+온천+힐링' },
    { icon: '🎋', name: '전남 담양 대나무숲 리트릿', desc: '청정 대나무숲 속 산책과 명상으로 지친 심신을 회복하는 당일·1박 프로그램.', tags: ['명상', '산책', '피톤치드'], url: 'https://search.naver.com/search.naver?query=담양+대나무숲+힐링+여행' },
    { icon: '🏯', name: '경북 경주 한방 스파', desc: '전통 한방 처방 기반 스파와 족욕으로 에너지를 보충하는 웰니스 패키지. 보약 보양식 포함.', tags: ['한방', '족욕', '보양식'], url: 'https://search.naver.com/search.naver?query=경주+한방스파+웰니스' },
  ],
  skin_gut: [
    { icon: '🌊', name: '전남 완도 해양치유파크', desc: '청정 해조류·해수 기반 해양치유 프로그램. 피부 재생과 장 건강에 도움을 주는 전문 트리트먼트 제공.', tags: ['해양치유', '피부', '장건강'], url: 'https://search.naver.com/search.naver?query=완도+해양치유파크' },
    { icon: '🏝️', name: '제주 해안 힐링 리트릿', desc: '제주 청정 바다 공기와 해조류 기반 식단, 해수 스파를 결합한 피부·장 케어 2박3일 패키지.', tags: ['제주', '해수스파', '건강식단'], url: 'https://search.naver.com/search.naver?query=제주+웰니스+해양+리트릿' },
    { icon: '♨️', name: '강원 고성 해수 온천', desc: '동해 해수를 활용한 해수 온천과 미네랄 입욕으로 피부 트러블을 완화하는 힐링 여행.', tags: ['해수온천', '미네랄', '피부케어'], url: 'https://search.naver.com/search.naver?query=고성+해수온천+힐링' },
    { icon: '🌿', name: '경남 남해 발효 건강 리트릿', desc: '남해 청정 자연 속에서 발효 식품 체험과 장 건강 개선 식단 프로그램을 즐기는 힐링 여행.', tags: ['발효식품', '장건강', '자연'], url: 'https://search.naver.com/search.naver?query=남해+건강+웰니스+리트릿' },
  ],
  hair: [
    { icon: '🌄', name: '전북 무주 덕유산 청정 리트릿', desc: '오염 없는 청정 산공기와 항산화 식단으로 두피 혈류를 개선하고 모발 영양을 보충하는 프로그램.', tags: ['청정공기', '두피케어', '항산화'], url: 'https://search.naver.com/search.naver?query=무주+덕유산+힐링+웰니스' },
    { icon: '🌿', name: '경남 하동 녹차 디톡스', desc: '하동 야생 녹차의 항산화 성분을 활용한 두피 디톡스 트리트먼트와 건강식 체험 패키지.', tags: ['녹차디톡스', '두피', '항산화'], url: 'https://search.naver.com/search.naver?query=하동+녹차+웰니스+힐링' },
    { icon: '🧘', name: '강원 양양 서피비치 스트레스 해소', desc: '파도 소리를 들으며 요가·명상으로 스트레스를 해소하고 탈모 유발 코르티솔 수치를 낮추는 여행.', tags: ['요가', '명상', '스트레스해소'], url: 'https://search.naver.com/search.naver?query=양양+서피비치+요가+웰니스' },
    { icon: '🏡', name: '충북 단양 자연 힐링 스테이', desc: '단양 청정 자연과 건강 식단으로 내부부터 영양을 채우는 모발·영양 집중 관리 리트릿.', tags: ['자연힐링', '영양식단', '청정'], url: 'https://search.naver.com/search.naver?query=단양+자연+힐링+웰니스' },
  ],
  sleep_stress: [
    { icon: '🌲', name: '강원 인제 자작나무숲 명상', desc: '하얀 자작나무숲 속 산림 명상과 디지털 디톡스로 수면 호르몬 멜라토닌 리듬을 회복하는 리트릿.', tags: ['명상', '디지털디톡스', '수면'], url: 'https://search.naver.com/search.naver?query=인제+자작나무숲+명상+힐링' },
    { icon: '⛩️', name: '충북 영동 천태산 템플스테이', desc: '사찰 생활로 마음을 비우고 숙면·명상·다도로 스트레스를 근본적으로 해소하는 1박2일 프로그램.', tags: ['템플스테이', '명상', '다도'], url: 'https://search.naver.com/search.naver?query=영동+천태산+템플스테이' },
    { icon: '🏔️', name: '경기 가평 산속 명상 리트릿', desc: '서울 근교 가평의 한적한 산속에서 마음챙김 명상, 호흡 훈련, 수면 코칭을 받는 주말 리트릿.', tags: ['명상', '수면코칭', '주말힐링'], url: 'https://search.naver.com/search.naver?query=가평+명상+리트릿+힐링' },
    { icon: '🌙', name: '전북 진안 마이산 힐링', desc: '마이산의 영기 어린 자연 속에서 스트레스 해소 프로그램과 한방 수면 개선 식단을 즐기는 여행.', tags: ['자연치유', '한방', '스트레스'], url: 'https://search.naver.com/search.naver?query=진안+마이산+힐링+웰니스' },
  ],
  metabolic: [
    { icon: '🌿', name: '경남 남해 지중해식 리트릿', desc: '지중해식 저당·고섬유 건강식과 활동적 야외 프로그램을 결합한 대사 개선 2박3일 패키지.', tags: ['지중해식단', '대사개선', '활동형'], url: 'https://search.naver.com/search.naver?query=남해+건강식+다이어트+리트릿' },
    { icon: '🍵', name: '전남 보성 녹차밭 웰니스', desc: '보성 녹차의 카테킨 성분이 지방 대사를 돕는 디톡스 프로그램. 걷기·체조 포함 건강 패키지.', tags: ['디톡스', '대사촉진', '걷기'], url: 'https://search.naver.com/search.naver?query=보성+녹차밭+웰니스+힐링' },
    { icon: '🚴', name: '강원 평창 바이오 헬스 투어', desc: '청정 고원 지대에서 자전거·트레킹·올림픽 스포츠 체험으로 대사량을 높이는 액티브 웰니스 여행.', tags: ['트레킹', '자전거', '액티브'], url: 'https://search.naver.com/search.naver?query=평창+웰니스+액티브+여행' },
    { icon: '🌱', name: '제주 팜스테이 건강 프로그램', desc: '제주 유기농 농장에서 직접 수확한 저칼로리 건강식을 먹고 야외 활동으로 에너지를 소모하는 힐링 체험.', tags: ['팜스테이', '유기농', '건강식'], url: 'https://search.naver.com/search.naver?query=제주+팜스테이+건강+웰니스' },
  ],
  total: [
    { icon: '🌈', name: '강원 원주 종합 웰니스 패키지', desc: '에너지·수면·대사·피부를 종합 관리하는 프리미엄 웰니스 리조트 2박3일 패키지. 전문 상담 포함.', tags: ['종합웰니스', '프리미엄', '2박3일'], url: 'https://search.naver.com/search.naver?query=원주+웰니스+리조트+힐링' },
    { icon: '🏞️', name: '충남 태안 국립공원 자연 치유', desc: '국립공원의 청정 자연 속에서 산책·해변 명상·건강식으로 몸과 마음 전반을 회복하는 힐링 여행.', tags: ['자연치유', '국립공원', '명상'], url: 'https://search.naver.com/search.naver?query=태안+웰니스+국립공원+힐링' },
    { icon: '🏛️', name: '전북 전주 한옥 힐링 스테이', desc: '전통 한옥에서 한방 보양식·다도·명상을 즐기는 웰니스 스테이. 번아웃 회복에 최적화된 루틴 제공.', tags: ['한옥', '한방', '번아웃회복'], url: 'https://search.naver.com/search.naver?query=전주+한옥+웰니스+힐링스테이' },
    { icon: '🌄', name: '경북 안동 자연 회복 리트릿', desc: '안동 청정 자연과 유네스코 세계유산 속에서 디지털 디톡스와 전통 건강관리법을 체험하는 리트릿.', tags: ['디지털디톡스', '전통', '자연'], url: 'https://search.naver.com/search.naver?query=안동+웰니스+자연+힐링' },
  ],
};

function dbOpenTravel(type) {
  const travels = DB_TRAVELS[type] || DB_TRAVELS.total;
  const cards = travels.map(t => `
    <div class="db-travel-card">
      <div style="font-size:30px;text-align:center;margin-bottom:8px">${t.icon}</div>
      <div class="db-travel-card-name">${t.name}</div>
      <div class="db-travel-card-desc">${t.desc}</div>
      <div class="db-travel-tags">${t.tags.map(g => '<span class="db-travel-tag">' + g + '</span>').join('')}</div>
      <a href="${t.url}" target="_blank" rel="noopener noreferrer" class="db-travel-link">여행 알아보기 →</a>
    </div>`).join('');
  document.getElementById('db-travel-content').innerHTML = '<div class="db-travel-grid">' + cards + '</div>';
  dbOpenModal('db-modal-travel');
}
// ─────────────────────────────────────────────────────────────

function dbRestart() {
  DB.step = 1;
  DB.answers = { target:null, age:null, pattern:null, concerns:[], lifestyle:{}, supp:{}, safety:[] };
  document.querySelectorAll('.db-opt.sel').forEach(e => e.classList.remove('sel'));
  document.querySelectorAll('.db-q-o.sel').forEach(e => e.classList.remove('sel'));
  document.querySelectorAll('.db-chk-item.on').forEach(e => { e.classList.remove('on'); e.querySelector('input').checked = false; });
  document.getElementById('db-supp-detail').style.display = 'none';
  document.getElementById('db-result').style.display = 'none';
  document.getElementById('db-landing').style.display = 'flex';
  document.querySelector('.diobio-panel').scrollTop = 0;
}

checkMode();
addMessage('bot',
  '안녕하세요! **보험 상담 AI 어시스턴트**입니다. 🛡️\n\n' +
  '**종신보험, 실손의료보험, 암보험, 치아보험, 간병·치매보험, 연금보험** 상담을 도와드립니다.\n\n' +
  '보험다모아 공시 데이터 + 실시간 웹 검색을 통해 최신 정보로 답변드립니다.\n\n' +
  '나이, 성별, 예산을 알려주시면 더 정확한 추천이 가능합니다!\n\n' +
  '> 예시: *"50대 남성, 간병보험 보험사별로 비교해줘"*'
);
</script>
</body>
</html>"""


# ── Routes ────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template_string(HTML)


def _check_api_live():
    """실제 API 호출로 키 유효 여부 확인 (결과를 60초 캐싱)"""
    now = __import__('time').time()
    cached = _check_api_live._cache
    if cached['ts'] and now - cached['ts'] < 60:
        return cached['result']

    api_key = os.getenv('OPENAI_API_KEY', '')
    if not api_key:
        result = False
    else:
        try:
            import openai as _oai
            _oai.OpenAI(api_key=api_key).chat.completions.create(
                model='gpt-4o-mini',
                max_tokens=1,
                messages=[{'role': 'user', 'content': 'hi'}],
            )
            result = True
        except Exception:
            result = False

    _check_api_live._cache = {'ts': now, 'result': result}
    return result

_check_api_live._cache = {'ts': None, 'result': False}

# 사용자가 수동으로 선택한 모드: 'auto', 'live', 'mock'
forced_mode = 'auto'


@app.route('/api/set-mode', methods=['POST'])
def set_mode():
    global forced_mode
    mode = request.json.get('mode', 'auto')
    if mode not in ('auto', 'live', 'mock'):
        return jsonify({'error': '유효하지 않은 모드'}), 400
    forced_mode = mode
    # 캐시 무효화해서 다음 요청에서 재확인
    _check_api_live._cache = {'ts': None, 'result': False}
    live = _check_api_live()
    effective = _get_effective_mode(live)
    return jsonify({'forced_mode': forced_mode, 'effective_mode': effective})


def _get_effective_mode(api_live: bool) -> str:
    if forced_mode == 'live':
        return 'live'
    if forced_mode == 'mock':
        return 'mock'
    return 'live' if api_live else 'mock'


@app.route('/api/status')
def status():
    live = _check_api_live()
    effective = _get_effective_mode(live)
    return jsonify({'mode': effective, 'effective_mode': effective, 'forced_mode': forced_mode})


@app.route('/api/credit-portfolio', methods=['POST'])
def credit_portfolio():
    """신용점수 입력 기반 보험 포트폴리오 생성"""
    data = request.json or {}
    age           = data.get('age')
    gender        = data.get('gender', '남')
    budget_man    = data.get('budget_man')        # 만원 단위
    scores        = data.get('scores', [])        # [{'source':'NICE','score':820}, ...]
    avg_score     = data.get('avg_score')
    married       = data.get('married', '')
    existing      = data.get('existing_insurance', '')
    health        = data.get('health_notes', '')
    financial_data = data.get('financial_data', {}) or {}
    alt_data      = data.get('alt_data', {}) or {}
    medical_data  = data.get('medical_data', {}) or {}

    if not age or not budget_man or not scores:
        return jsonify({'error': '나이, 예산, 신용점수를 모두 입력해주세요.'}), 400

    # 종합 적합도 점수 산출 (항상 계산)
    from data.credit_model import (
        calculate_composite_score, get_financial_profile_summary, get_credit_summary_for_prompt
    )
    cs = calculate_composite_score(avg_score, financial_data, alt_data, medical_data)

    api_live = _check_api_live()
    effective = _get_effective_mode(api_live)

    if effective == 'live':
        try:
            from agents.orchestrator import InsuranceChatbot
            bot = InsuranceChatbot()

            score_parts = [f"{s['source']} {s['score']}점" for s in scores]
            score_str = ' / '.join(score_parts)
            married_str = f", {married}" if married else ""
            existing_str = f"\n- 현재 가입 보험: {existing}" if existing else ""
            health_str = f"\n- 건강 특이사항: {health}" if health else ""

            # 의료이력 요약
            conditions = medical_data.get("conditions", [])
            hosp = medical_data.get("hospitalization", "")
            meds = medical_data.get("current_medications", "")
            med_lines = []
            if conditions:
                med_lines.append(f"- 최근 5년 치료 이력: {', '.join(conditions)}")
            if hosp:
                med_lines.append(f"- 최근 5년 입원: {hosp}")
            if meds:
                med_lines.append(f"- 현재 복용 약물: {meds}")
            med_section = ("\n" + "\n".join(med_lines)) if med_lines else ""

            # 금융·대안데이터 분석
            fin_profile = get_financial_profile_summary(financial_data, alt_data)
            fin_section = f"\n\n{fin_profile}" if fin_profile.strip() else ""

            # 종합 점수 분석 블록
            adj_str = "\n".join(
                f"  • {a['factor']}: {'+' if a['delta']>=0 else ''}{a['delta']}점 ({a['reason']})"
                for a in cs['adjustments']
            )
            cs_section = (
                f"\n\n## 종합 보험 가입 적합도 분석 결과\n"
                f"- 기본 신용점수: {cs['base_score']}점\n"
                f"- 조정 항목:\n{adj_str}\n"
                f"- **종합 적합도 지수: {cs['composite_score']}점 ({cs['grade']})**\n"
                f"- 보험 심사 위험도: {cs['underwriting_risk']}\n"
                f"- 권장 상품군: {', '.join(cs['preferred_products'][:4])}\n"
                f"- 신중 검토: {', '.join(cs['avoid_products'][:3]) if cs['avoid_products'] else '없음'}"
            )

            msg = (
                f"{age}세 {gender}성{married_str}, 월 예산 {budget_man}만원으로 "
                f"보험 포트폴리오 추천해줘.\n"
                f"신용점수: {score_str} (평균 {avg_score}점)"
                f"{existing_str}{health_str}{med_section}"
                f"{fin_section}{cs_section}\n\n"
                f"위 종합 적합도 분석을 바탕으로 각 상품 추천 이유를 구체적으로 설명하고, "
                f"보험 심사 위험도({cs['underwriting_risk']})와 신용등급({cs['grade']})이 "
                f"추천에 어떻게 반영됐는지 반드시 포함해줘."
            )
            result = bot.chat(msg)
            result = result.replace('(?)', '').replace('(?) ', '')
            from data.credit_model import parse_recommended_products, calculate_policy_loans
            loan_data = calculate_policy_loans(parse_recommended_products(result))
            return jsonify({'result': result, 'avg_score': avg_score, 'composite_score_data': cs, 'policy_loan_data': loan_data})
        except Exception as e:
            return jsonify({'error': f'포트폴리오 생성 실패: {str(e)}'}), 500
    else:
        # Mock fallback
        tier_info = get_credit_summary_for_prompt(avg_score)
        fin_profile = get_financial_profile_summary(financial_data, alt_data)
        fin_section = f"\n{fin_profile}" if fin_profile.strip() else ""

        conditions = medical_data.get("conditions", [])
        med_rows = []
        if conditions: med_rows.append(f"치료 이력: {', '.join(conditions)}")
        if medical_data.get("hospitalization"): med_rows.append(f"입원: {medical_data['hospitalization']}")
        if medical_data.get("current_medications"): med_rows.append(f"복용 약물: {medical_data['current_medications']}")
        alt_rows = []
        if alt_data.get("employment"): alt_rows.append(f"직업: {alt_data['employment']}")
        if alt_data.get("housing"):    alt_rows.append(f"거주: {alt_data['housing']}")
        all_extra = med_rows + alt_rows
        extra_section = ("\n- " + "\n- ".join(all_extra)) if all_extra else ""

        mock_result = f"""## 💳 신용점수 반영 보험 포트폴리오 (Mock 모드)

> ⚠️ **Mock 모드**: OpenAI API 키가 없어 샘플 결과를 표시합니다.

### 입력 정보
- 나이: {age}세 {gender}성 / 월 예산: {budget_man}만원
- 신용점수: {', '.join(f"{s['source']} {s['score']}점" for s in scores)} → 평균 **{avg_score}점**
- **종합 적합도 지수: {cs['composite_score']}점 ({cs['grade']})** (조정: {'+' if cs['total_delta']>=0 else ''}{cs['total_delta']}점){extra_section}

{tier_info}{fin_section}
### 📋 추천 포트폴리오 (샘플)

| 순위 | 보험 종류 | 추천 이유 | 예상 월보험료 |
|------|-----------|-----------|--------------|
| 1순위 | 실손의료보험 (5세대) | 기본 의료비 보장 필수 | 2~4만원 |
| 2순위 | 암보험 | 3대 질병 집중 보장 | 3~5만원 |
| 3순위 | 종신보험 | 사망/노후 자산 형성 | 5~8만원 |

> 실제 포트폴리오는 Live 모드에서 OpenAI API 키 설정 후 이용하세요.
"""
        from data.credit_model import parse_recommended_products, calculate_policy_loans
        mock_loan = calculate_policy_loans(parse_recommended_products(mock_result))
        return jsonify({'result': mock_result, 'avg_score': avg_score, 'composite_score_data': cs, 'policy_loan_data': mock_loan})


@app.route('/api/health-risk', methods=['POST'])
def api_health_risk():
    """건강검진 기반 위험예측 + 맞춤 보험 추천"""
    d = request.get_json(force=True) or {}

    def num(k):
        v = d.get(k)
        return float(v) if v not in (None, '', 'null') else None

    try:
        from tools.health_risk_tool import assess_health_risk
        smoke = d.get('smoke')
        drink = d.get('drink')
        bfc_raw = d.get('bfc_tier')
        out = assess_health_risk(
            age=int(d['age']), gender=d.get('gender', '남'),
            height=num('height'), weight=num('weight'), waist=num('waist'),
            sbp=num('sbp'), dbp=num('dbp'),
            total_cholesterol=num('total_cholesterol'), triglyceride=num('triglyceride'),
            hdl=num('hdl'), ldl=num('ldl'),
            ast=num('ast'), alt=num('alt'), ggt=num('ggt'),
            smoke=int(smoke) if smoke not in (None, '', 'null') else None,
            drink=int(drink) if drink not in (None, '', 'null') else None,
            bfc_tier=int(bfc_raw) if bfc_raw not in (None, '', 'null') else None,
            include_products=True,
        )
        return app.response_class(out, mimetype='application/json')
    except KeyError:
        return jsonify({'error': '나이를 입력해주세요.'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _parse_health_regex(text: str) -> dict:
    """건강검진 결과 텍스트에서 수치를 정규식으로 추출"""
    import datetime
    result = {}

    def find_num(patterns):
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1).replace(',', ''))
                except Exception:
                    pass
        return None

    # ── 나이 추출 (우선순위 순) ─────────────────────────────
    age_val = None
    # 1) "만 48세" / "만48세"
    m = re.search(r'만\s*(\d{2,3})\s*세', text)
    if m:
        age_val = int(m.group(1))
    # 2) "연령: 48" / "나이: 48" / "연령(세): 48"
    if age_val is None:
        m = re.search(r'(?:연령|나이)\s*(?:\(세\))?\s*[:\s]\s*(\d{2,3})', text)
        if m:
            age_val = int(m.group(1))
    # 3) 생년월일에서 역산 "생년월일: 1976-05-15" / "1976년 05월"
    if age_val is None:
        m = re.search(r'생년월일[:\s]*(\d{4})', text)
        if not m:
            m = re.search(r'(\d{4})\s*년\s*(?:\d{1,2}\s*월)', text)
        if m:
            birth_year = int(m.group(1))
            if 1930 <= birth_year <= 2015:
                age_val = datetime.datetime.now().year - birth_year
    # 4) 검진서 상단에 단독으로 나오는 두 자리 나이 "48세"
    #    단, 혈액검사 수치와 혼동 방지를 위해 문장 처음이나 줄 시작만
    if age_val is None:
        m = re.search(r'(?:^|\s|,)(\d{2})\s*세(?!\s*대)', text, re.MULTILINE)
        if m:
            age_val = int(m.group(1))
    if age_val is not None and 15 <= age_val <= 90:
        result['age'] = age_val

    # ── 성별 추출 ────────────────────────────────────────────
    if re.search(r'성별[:\s]*(남|M)\b|^남성$', text, re.IGNORECASE | re.MULTILINE):
        result['gender'] = '남'
    elif re.search(r'성별[:\s]*(여|F)\b|^여성$', text, re.IGNORECASE | re.MULTILINE):
        result['gender'] = '여'

    v = find_num([r'신장[:\s/]*(\d+\.?\d*)\s*cm', r'키[:\s]*(\d+\.?\d*)\s*cm'])
    if v: result['height'] = v

    v = find_num([r'체중[:\s/]*(\d+\.?\d*)\s*kg', r'몸무게[:\s]*(\d+\.?\d*)\s*kg'])
    if v: result['weight'] = v

    v = find_num([r'허리둘레[:\s/]*(\d+\.?\d*)', r'복부둘레[:\s]*(\d+\.?\d*)'])
    if v: result['waist'] = v

    m = re.search(r'수축기[혈압]?[:\s/]*(\d+)', text, re.IGNORECASE)
    if m: result['sbp'] = float(m.group(1))
    m = re.search(r'이완기[혈압]?[:\s/]*(\d+)', text, re.IGNORECASE)
    if m: result['dbp'] = float(m.group(1))
    if 'sbp' not in result:
        m = re.search(r'혈압[:\s]*(\d{2,3})\s*/\s*(\d{2,3})', text)
        if m:
            result['sbp'] = float(m.group(1))
            result['dbp'] = float(m.group(2))

    v = find_num([r'총콜레스테롤[:\s/]*(\d+)', r'\bTC[:\s]*(\d+)'])
    if v: result['total_cholesterol'] = v

    v = find_num([r'중성지방[:\s/]*(\d+)', r'\bTG[:\s]*(\d+)', r'트리글리세라이드[:\s]*(\d+)'])
    if v: result['triglyceride'] = v

    v = find_num([r'HDL[콜레스테롤]?[:\s/]*(\d+)', r'고밀도지단백[:\s]*(\d+)'])
    if v: result['hdl'] = v

    v = find_num([r'LDL[콜레스테롤]?[:\s/]*(\d+)', r'저밀도지단백[:\s]*(\d+)'])
    if v: result['ldl'] = v

    v = find_num([r'AST[^:\d\n]*[:\s/]*(\d+)', r'GOT[:\s/]*(\d+)'])
    if v: result['ast'] = v

    v = find_num([r'ALT[^:\d\n]*[:\s/]*(\d+)', r'GPT[:\s/]*(\d+)'])
    if v: result['alt'] = v

    v = find_num([r'\bGGT[:\s/]*(\d+)', r'감마.{0,3}GTP[:\s/]*(\d+)', r'γ.{0,3}GTP[:\s/]*(\d+)'])
    if v: result['ggt'] = v

    if re.search(r'현재\s*흡연|흡연[:\s]*(현재|예)', text, re.IGNORECASE):
        result['smoke'] = 3
    elif re.search(r'과거\s*흡연|금연', text, re.IGNORECASE):
        result['smoke'] = 2
    elif re.search(r'비흡연|흡연[:\s]*(비|아니|no)', text, re.IGNORECASE):
        result['smoke'] = 1

    if re.search(r'음주[:\s]*(예|함|있음|yes)', text, re.IGNORECASE):
        result['drink'] = 1
    elif re.search(r'음주[:\s]*(아니|안|없음|no|비)', text, re.IGNORECASE):
        result['drink'] = 0

    return result


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """PDF 바이트에서 텍스트 추출. pdfplumber → pypdf → PyPDF2 순 시도."""
    import io, subprocess, sys
    text = ""
    try:
        import pdfplumber
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'pdfplumber'], check=False)
        try:
            import pdfplumber
        except ImportError:
            pdfplumber = None
    try:
        if pdfplumber is not None:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
            text = "\n".join(pages)
            if text.strip():
                return text
    except Exception:
        pass
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        if text.strip():
            return text
    except Exception:
        pass
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception as e:
        raise RuntimeError(f"PDF 텍스트 추출 실패: {e}\n(해결: pip install pdfplumber pypdf)")
    return text


@app.route('/api/upload-health-pdf', methods=['POST'])
def api_upload_health_pdf():
    """건강검진 결과 PDF 업로드 → 텍스트 추출 → 수치 파싱"""
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다.'}), 400
    f = request.files['file']
    if not f.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'PDF 파일만 지원합니다.'}), 400

    pdf_bytes = f.read()
    if len(pdf_bytes) > 10 * 1024 * 1024:
        return jsonify({'error': '파일이 10MB를 초과합니다.'}), 400

    try:
        raw_text = _extract_pdf_text(pdf_bytes)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    if not raw_text.strip():
        return jsonify({'error': 'PDF에서 텍스트를 추출할 수 없습니다. 스캔된 이미지 PDF는 지원하지 않습니다.'}), 422

    result = _parse_health_regex(raw_text)

    # LLM 보완 (API 사용 가능한 경우)
    api_live = _check_api_live()
    if api_live:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY', ''))
            import datetime as _dt
            current_year = _dt.datetime.now().year
            already = {k: v for k, v in result.items() if v is not None and not k.startswith('_')}
            already_hint = ', '.join(f'{k}={v}' for k, v in already.items()) if already else '(없음)'
            prompt = f"""다음은 국민건강보험공단 건강검진 결과 PDF에서 추출한 텍스트입니다.
오늘은 {current_year}년입니다. 아래 JSON 형식으로 수치를 추출해주세요. 없는 항목은 null로 설정하세요.

【중요】
- age(나이): 반드시 {current_year}년 기준 만 나이(정수)로 반환. 생년월일이 있으면 {current_year} - 출생연도 로 계산.
  예) 1976년생 → {current_year - 1976}세. 절대 혈액검사 수치를 나이로 착각하지 말 것.
- 이미 정규식으로 추출된 항목: {already_hint} — 이 항목들은 null로 반환해도 됨(덮어쓰지 않음).

{{
  "age": 만 나이(정수, {current_year}년 기준) or null,
  "gender": "남" or "여" or null,
  "height": 키(cm 숫자) or null,
  "weight": 몸무게(kg 숫자) or null,
  "waist": 허리둘레(cm 숫자) or null,
  "sbp": 수축기혈압(mmHg 숫자) or null,
  "dbp": 이완기혈압(mmHg 숫자) or null,
  "total_cholesterol": 총콜레스테롤(mg/dL 숫자) or null,
  "triglyceride": 중성지방(mg/dL 숫자) or null,
  "hdl": HDL콜레스테롤(mg/dL 숫자) or null,
  "ldl": LDL콜레스테롤(mg/dL 숫자) or null,
  "ast": AST/GOT(U/L 숫자) or null,
  "alt": ALT/GPT(U/L 숫자) or null,
  "ggt": 감마GTP(U/L 숫자) or null,
  "smoke": 1(비흡연) or 2(과거흡연) or 3(현재흡연) or null,
  "drink": 0(비음주) or 1(음주) or null
}}

텍스트:
{raw_text[:3000]}"""
            resp = client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[{'role': 'user', 'content': prompt}],
                response_format={'type': 'json_object'},
                temperature=0,
                max_tokens=512,
            )
            llm_data = json.loads(resp.choices[0].message.content)
            for k, v in llm_data.items():
                if v is not None and result.get(k) is None:
                    result[k] = v
        except Exception:
            pass

    result['_source'] = 'pdf'
    return jsonify(result)


@app.route('/api/parse-health-data', methods=['POST'])
def api_parse_health_data():
    """건강검진 결과 텍스트 → 구조화된 수치 추출 (정규식 + LLM 보완)"""
    d = request.get_json(force=True) or {}
    text = d.get('text', '').strip()
    if not text:
        return jsonify({'error': '텍스트를 입력해주세요.'}), 400

    result = _parse_health_regex(text)

    api_live = _check_api_live()
    effective = _get_effective_mode(api_live)
    if effective == 'live':
        try:
            import openai as _oai
            client = _oai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            resp = client.chat.completions.create(
                model='gpt-4o-mini',
                max_tokens=400,
                response_format={'type': 'json_object'},
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            '건강검진 결과 텍스트에서 수치를 추출해서 JSON으로만 반환해. '
                            'key: age(나이 정수), gender("남"또는"여"), '
                            'height(cm), weight(kg), waist(cm), sbp, dbp, '
                            'total_cholesterol, triglyceride, hdl, ldl, ast, alt, ggt, '
                            'smoke(1=비흡연/2=과거/3=현재흡연), drink(0=비음주/1=음주). '
                            '없는 값은 null. 단위 없이 숫자만.'
                        ),
                    },
                    {'role': 'user', 'content': text[:2000]},
                ],
            )
            llm_result = json.loads(resp.choices[0].message.content)
            for k, v in llm_result.items():
                if v is not None and k not in result:
                    result[k] = v
        except Exception:
            pass

    return jsonify(result)


@app.route('/api/health-risk-ai', methods=['POST'])
def api_health_risk_ai():
    """건강위험 분석 결과 기반 GPT-4o AI 맞춤 보험 추천"""
    d = request.get_json(force=True) or {}
    risk_data = d.get('risk_data', {})
    if not risk_data:
        return jsonify({'error': '위험 분석 결과가 없습니다.'}), 400

    ra    = risk_data.get('risk_assessment', {})
    ins   = risk_data.get('input_summary', {})
    recs  = risk_data.get('recommended_insurance_types', [])
    prods = risk_data.get('insmarket_products', {})
    bfc   = risk_data.get('bfc_info') or {}
    cancer = risk_data.get('cancer_risk') or {}

    age    = ins.get('age', '불명')
    gender = ins.get('gender', '남')
    bmi    = ins.get('bmi', '')
    flags  = ins.get('flags', [])
    score  = ra.get('risk_score', 0)
    band   = ra.get('risk_band', '')

    # BFC 분위 예산 정보
    bfc_section = ''
    if bfc:
        bfc_label = bfc.get('label', '')
        bfc_min   = bfc.get('budget_min_10k', 0)
        bfc_max   = bfc.get('budget_max_10k', 0)
        bfc_section = (
            f"\n## BFC 보험료 분위 (이노베이션 존 · NHIS 3,706만 건)\n"
            f"- 분위: {bfc_label}\n"
            f"- 납부 가능 보험료 범위: 월 {bfc_min}~{bfc_max}만원\n"
            f"⚠️ 추천 포트폴리오 합산 월보험료가 반드시 {bfc_max}만원 이내가 되도록 구성할 것.\n"
        )

    # 암 위험 상위 3개
    cancer_section = ''
    cancer_items = cancer.get('cancer_risks', []) if isinstance(cancer, dict) else []
    if cancer_items:
        top3 = cancer_items[:3]
        lines = [f"- {c['cancer']}: {c['risk_level']} (5년 생존율 {c.get('survival_5yr', '?')}%)" for c in top3]
        death_flag = any((c.get('survival_5yr') or 100) < 50 for c in top3)
        cancer_section = (
            f"\n## 암 위험 분석 (이노베이션 존 RGST/DEATH 연계)\n"
            + '\n'.join(lines) +
            ('\n⚠️ 5년 생존율 50% 미만 고위험 암종 감지 → 종신보험·간병보험을 포트폴리오에 반드시 포함할 것.' if death_flag else '')
        )

    prod_lines = []
    prod_table_rows = []
    for t, td in prods.items():
        if isinstance(td, dict) and td.get('results'):
            for r in td['results'][:2]:
                co = (r.get('company') or '').strip()
                nm = (r.get('product_name') or '').strip()
                pr = (r.get('premium') or '문의').strip()
                if nm:
                    prod_table_rows.append(f"| {t} | {co} | {nm} | {pr} |")
                    prod_lines.append(f"- {t}: {co} {nm} ({pr})")
    prod_section = '\n'.join(prod_lines) if prod_lines else '(보험다모아 조회 결과 없음)'

    budget_note = (
        f"월 {bfc.get('budget_max_10k', '?')}만원 이하 범위 내 포트폴리오 구성 필수."
        if bfc else "예산 제한 없음."
    )

    prompt = (
        f"{age}세 {gender}성, 건강검진 위험 분석 결과를 바탕으로 맞춤 보험 포트폴리오를 추천해줘.\n\n"
        f"## 위험도 분석 결과\n"
        f"- 당뇨·대사 위험도: {score*100:.1f}% ({band})\n"
        f"- BMI: {bmi if bmi else '미입력'}\n"
        f"- 임상 플래그: {', '.join(flags) if flags else '없음'}\n"
        f"- 추천 보험 유형: {', '.join(recs)}\n"
        f"{bfc_section}"
        f"{cancer_section}\n\n"
        f"## 보험다모아 조회 상품 (보험사명 포함)\n{prod_section}\n\n"
        f"다음 4가지를 포함해서 마크다운으로 추천해줘:\n"
        f"1. **위험도 해석** — 이 위험도가 보험 가입에 어떤 의미인지\n"
        f"2. **우선순위별 보험 포트폴리오** — 반드시 아래 형식의 마크다운 **표**로 정리. "
        f"{budget_note} "
        f"**보험사 컬럼에 반드시 실제 보험사명**을 기재할 것 (위 조회 상품 활용, 없으면 삼성생명·한화생명·교보생명 등 주요사 직접 기재):\n"
        f"   | 순위 | 보험 종류 | 보험사 | 추천 이유 | 예상 월보험료 |\n"
        f"3. **심사 전략** — 현재 건강 상태에서 가입 시 유의사항 (간편심사/일반심사 등)\n"
        f"4. **예방 포인트** — 위험 요인 개선으로 보험료 절감·재심사 가능성"
    )

    api_live = _check_api_live()
    effective = _get_effective_mode(api_live)

    if effective == 'live':
        try:
            from agents.orchestrator import InsuranceChatbot
            bot = InsuranceChatbot()
            result = bot.chat(prompt)
            return jsonify({'result': result})
        except Exception as e:
            return jsonify({'error': f'AI 추천 생성 실패: {str(e)}'}), 500
    else:
        flag_str = ', '.join(flags) if flags and flags != ['특이소견 없음'] else '특별한 이상 소견 없음'
        # 실제 조회 상품이 있으면 활용, 없으면 샘플
        if prod_table_rows:
            portfolio_table = (
                "| 순위 | 보험 종류 | 보험사 | 추천 상품 | 예상 월보험료 |\n"
                "|------|-----------|--------|-----------|---------------|\n" +
                '\n'.join(
                    f"| {i+1}순위 | {row.split('|')[1].strip()} | {row.split('|')[2].strip()} "
                    f"| {row.split('|')[3].strip()} | {row.split('|')[4].strip()} |"
                    for i, row in enumerate(prod_table_rows[:4])
                )
            )
        else:
            portfolio_table = (
                "| 순위 | 보험 종류 | 보험사 | 추천 이유 | 예상 월보험료 |\n"
                "|------|-----------|--------|-----------|---------------|\n"
                "| 1순위 | 실손의료보험 (5세대) | 삼성화재 | 기본 의료비 보장 필수 | 2~4만원 |\n"
                "| 2순위 | 질병보험 | 한화생명 | 당뇨·대사 위험 대비 진단금 | 3~5만원 |\n"
                "| 3순위 | 암보험 | 교보생명 | 대사증후군 → 암 위험 상관관계 | 2~4만원 |"
            )
        mock = f"""## 📊 AI 맞춤 보험 추천 (Mock 모드)

> ⚠️ Mock 모드: OpenAI API 키 설정 후 Live 모드에서 정확한 추천을 받을 수 있습니다.

### 1. 위험도 해석
**{band}** ({score*100:.1f}%)으로 분석됐습니다. 임상 소견: {flag_str}

### 2. 우선순위별 보험 포트폴리오

{portfolio_table}

### 3. 심사 전략
- **일반심사** 가능 여부를 먼저 확인하세요.
- 고혈압·당뇨 치료 이력 있으면 **간편심사형** 상품 비교 필요.

### 4. 예방 포인트
- 규칙적 유산소 운동 (주 3~5회, 30분+)
- 금연 및 절주 → 2년 후 보험료 재산정 기회
- 1~2년 주기 정기 건강검진 권장
"""
        return jsonify({'result': mock})


@app.route('/api/demo/run', methods=['POST'])
def demo_run():
    """데모 시나리오 도구를 직접 실행하여 결과 반환 (GPT-4o 없이)."""
    from tools.cancer_survivor_tool import (
        assess_cancer_survivor, assess_low_risk_discount, assess_pacs_no_extra,
        assess_dynamic_discount, assess_chronic_disease_rate,
        assess_healthy_body_discount, assess_polyp_removal_eligibility,
    )
    from tools.health_credit_tool import (
        assess_health_credit, assess_sme_health_loan, assess_rental_approval,
        assess_early_care, assess_default_prevention,
        assess_healthy_body_loan, assess_health_secured_loan,
        assess_adverse_selection_score, assess_thin_filer_adverse_selection,
    )

    scenario = request.json.get('scenario')

    # 시나리오별 페르소나 파라미터 — 그룹 순서: 보험(1-7) 금융(8-12) 역선택(13-14) 위험관리(15-16)
    DEMO_CALLS = {
        # 보험 영역 (1~7)
        1:  lambda: assess_cancer_survivor(
                age=45, gender="남", cancer_type="위암", cancer_stage="2기",
                years_since_cure=3, treatment_method="수술+항암", recent_checkup_normal=True),
        2:  lambda: assess_low_risk_discount(
                age=38, gender="여", consecutive_checkups=5,
                bmi_normal=True, bp_normal=True, blood_sugar_normal=True,
                non_smoker=True, pacs_finding="이상없음"),
        3:  lambda: assess_pacs_no_extra(
                age=52, gender="남", finding_type="폐 미세결절",
                finding_size_mm=6, follow_up_years=2),
        4:  lambda: assess_dynamic_discount(
                age=41, gender="여", score_improvement_pct=25,
                monthly_premium=80000, management_years=1),
        5:  lambda: assess_chronic_disease_rate(
                age=57, gender="남", disease="당뇨",
                treatment_response="우수", hba1c_or_key_metric=6.5),
        6:  lambda: assess_healthy_body_discount(
                age=43, gender="남", consecutive_checkups=5,
                bmi_normal=True, bp_normal=True, blood_sugar_normal=True,
                non_smoker=True, base_premium_10k=12),
        7:  lambda: assess_polyp_removal_eligibility(
                age=50, gender="남", polyp_type="관상선종(저등급)",
                years_since_removal=2.0, pathology_benign=True,
                followup_endoscopy_normal=True, polyp_size_mm=8),
        # 금융 영역 (8~12)
        8:  lambda: assess_health_credit(
                age=32, gender="남", consecutive_checkups=4,
                vital_stability="상", bfc_tier=5,
                current_credit_score=680, loan_purpose="전세자금", loan_amount_10k=20000),
        9:  lambda: assess_sme_health_loan(
                age=48, gender="남", business_years=8,
                chronic_disease="없음", treatment_response="우수",
                monthly_revenue_10k=800, loan_amount_10k=3000),
        10: lambda: assess_rental_approval(
                age=62, gender="남", disease_history="위암 1기 완치",
                short_term_risk="낮음", rental_amount_10k=500, rental_period_months=36),
        11: lambda: assess_healthy_body_loan(
                age=46, gender="여", consecutive_checkups=4,
                vital_stability="상", bfc_tier=6,
                dsr_ratio_pct=52.0, loan_purpose="생활자금", loan_amount_10k=5000),
        12: lambda: assess_health_secured_loan(
                age=52, gender="남", consecutive_checkups=3,
                vital_stability="상", lifelog_score=78,
                bfc_tier=5, dsr_ratio_pct=58.0, ltv_ratio_pct=82.0,
                loan_amount_10k=5000),
        # 신용 역선택 방지 (13~14)
        13: lambda: assess_adverse_selection_score(
                age=42, gender="남", credit_score=650, credit_drop_6m=130,
                insurance_amount_10k=10000, recent_checkup_months=30,
                multi_insurer=True, sudden_large_policy=True),
        14: lambda: assess_thin_filer_adverse_selection(
                age=28, gender="여", has_credit_history=False,
                consecutive_checkups=0, insurance_amount_10k=8000,
                sudden_application=True, vital_data_available=False),
        # 위험 관리 (15~16)
        15: lambda: assess_early_care(
                age=52, gender="남", finding="위 미란 소견",
                progression_risk_pct=42.0, early_intervention=True,
                insurance_coverage_10k=8000),
        16: lambda: assess_default_prevention(
                age=55, gender="남", loan_amount_10k=20000,
                sofa_score=2.0, severe_disease_risk_pct=38.0,
                has_repayment_insurance=False),
    }

    fn = DEMO_CALLS.get(scenario)
    if not fn:
        return jsonify({'error': f'시나리오 {scenario}를 찾을 수 없습니다.'}), 400

    try:
        raw = fn()
        result = json.loads(raw) if isinstance(raw, str) else raw
        return jsonify({'ok': True, 'scenario': scenario, 'result': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '').strip()
    sid = data.get('session_id', 'default')

    if not message:
        return jsonify({'error': '메시지가 비어있습니다.'}), 400

    if sid not in sessions:
        sessions[sid] = {'context': MockContext(), 'chatbot': None}

    sess = sessions[sid]

    api_live = _check_api_live()
    effective = _get_effective_mode(api_live)

    # Live mode
    if effective == 'live':
        try:
            if sess['chatbot'] is None:
                from agents.orchestrator import InsuranceChatbot
                sess['chatbot'] = InsuranceChatbot()
            response = sess['chatbot'].chat(message)
            return jsonify({'response': response, 'mode': 'live'})
        except Exception as e:
            err = str(e)
            _check_api_live._cache = {'ts': None, 'result': False}
            sess['chatbot'] = None
            # 강제 Live 모드인데 실패하면 오류 반환
            if forced_mode == 'live':
                return jsonify({'error': f'Live Mode 오류: {err}'}), 500
            # Auto 모드면 Mock으로 fallback
            if 'credit' not in err.lower() and '400' not in err:
                return jsonify({'error': err}), 500

    # Mock mode
    try:
        response = mock_response(message, sess['context'])
        return jsonify({'response': response, 'mode': 'mock'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    data = request.json
    message = data.get('message', '').strip()
    sid = data.get('session_id', 'default')

    if not message:
        return jsonify({'error': '메시지가 비어있습니다.'}), 400

    if sid not in sessions:
        sessions[sid] = {'context': MockContext(), 'chatbot': None}

    sess = sessions[sid]
    api_live = _check_api_live()
    effective = _get_effective_mode(api_live)

    def generate():
        if effective == 'live':
            try:
                if sess['chatbot'] is None:
                    from agents.orchestrator import InsuranceChatbot
                    sess['chatbot'] = InsuranceChatbot()
                for event in sess['chatbot'].stream_chat(message):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                return
            except Exception as e:
                err = str(e)
                _check_api_live._cache['ts'] = None
                sess['chatbot'] = None
                if forced_mode == 'live':
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Live Mode 오류: {err}'}, ensure_ascii=False)}\n\n"
                    return

        # Mock mode — return full response as single done event
        try:
            response = mock_response(message, sess['context'])
            yield f"data: {json.dumps({'type': 'done', 'full_text': response}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/api/reset', methods=['POST'])
def reset():
    sid = request.json.get('session_id', 'default')
    if sid in sessions:
        sessions[sid] = {'context': MockContext(), 'chatbot': None}
    return jsonify({'status': 'ok'})


# ── DIOBIO 카카오 채널 설정 ────────────────────────────────────
KAKAO_CHANNEL_URL  = 'http://pf.kakao.com/_xcPnxnX'
KAKAO_CHAT_URL     = 'http://pf.kakao.com/_xcPnxnX/chat'

# ── 카카오 i 오픈빌더 스킬 서버 ────────────────────────────────
# 카카오 비즈니스 > 챗봇 연결 > 스킬 서버 URL: http://<공인IP>:5000/kakao/skill
# (외부 접근 불가 시 ngrok 등으로 터널링 필요)

_kakao_sessions: dict = {}  # 카카오 유저별 대화 세션

import re as _re

def _strip_md(text: str) -> str:
    """마크다운을 카카오 텍스트용 평문으로 변환"""
    text = _re.sub(r'\*\*(.+?)\*\*', r'\1', text)       # bold
    text = _re.sub(r'\*(.+?)\*', r'\1', text)            # italic
    text = _re.sub(r'#{1,6}\s+', '', text)               # heading
    text = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text) # link → text만
    text = _re.sub(r'`{1,3}[^`]*`{1,3}', '', text)      # code
    text = _re.sub(r'^\s*[-*]\s+', '• ', text, flags=_re.M)  # bullet
    text = _re.sub(r'^\s*\|.*\|.*$', '', text, flags=_re.M)  # table row 제거
    text = _re.sub(r'\n{3,}', '\n\n', text)             # 빈줄 정리
    return text.strip()

def _kakao_resp(outputs: list, quick_replies: list | None = None) -> dict:
    resp: dict = {"version": "2.0", "template": {"outputs": outputs}}
    if quick_replies:
        resp["template"]["quickReplies"] = quick_replies
    return resp

def _kakao_text(text: str, quick_replies: list | None = None):
    return jsonify(_kakao_resp([{"simpleText": {"text": text}}], quick_replies))

def _kakao_card(title: str, desc: str, buttons: list | None = None):
    card: dict = {"title": title, "description": desc}
    if buttons:
        card["buttons"] = buttons
    return {"basicCard": card}

_KAKAO_QUICK = [
    {"label": "보험 추천", "action": "message", "messageText": "내 상황에 맞는 보험 추천해줘"},
    {"label": "실손보험", "action": "message", "messageText": "실손보험 최신 상품 추천해줘"},
    {"label": "암보험",   "action": "message", "messageText": "암보험 추천해줘"},
    {"label": "웰니스 분석", "action": "message", "messageText": "DIOBIO 웰니스 분석 받고 싶어"},
]

@app.route('/kakao/skill', methods=['POST'])
def kakao_skill():
    """카카오 i 오픈빌더 스킬 서버 엔드포인트 (DIOBIO_BOT 연동)"""
    try:
        body         = request.json or {}
        user_req     = body.get('userRequest', {})
        utterance    = user_req.get('utterance', '').strip()
        user_id      = user_req.get('user', {}).get('id', 'kakao_anon')
        session_key  = f"kakao_{user_id}"

        # 웰컴/fallback 메시지
        if not utterance or utterance in ('안녕', '안녕하세요', '시작', '처음'):
            return _kakao_text(
                "안녕하세요! DIOBIO AI 보험·웰니스 상담 챗봇입니다.\n\n"
                "보험 추천, 실손보험, 암보험, 건강 유형 분석 등 궁금하신 내용을 말씀해 주세요.",
                _KAKAO_QUICK
            )

        # AI 응답 생성 (동기 호출)
        api_live = _check_api_live()
        effective = _get_effective_mode(api_live)

        if effective == 'live':
            try:
                from agents.orchestrator import InsuranceChatbot
                # 유저별 세션 재사용
                if session_key not in _kakao_sessions:
                    _kakao_sessions[session_key] = InsuranceChatbot()
                bot = _kakao_sessions[session_key]
                raw = bot.chat(utterance)
                text = _strip_md(raw)
                # 카카오 단일 버블 최대 1000자 → 초과 시 분할
                if len(text) <= 900:
                    return _kakao_text(text, _KAKAO_QUICK)
                # 1000자 초과: 앞 900자 + 안내 카드
                part1 = text[:900] + "..."
                card  = _kakao_card(
                    "더 자세한 상담 안내",
                    "전체 상담 내용은 DIOBIO 웹 상담을 이용해 주세요.",
                    [{"label": "웹 상담 열기", "action": "webLink",
                      "webLinkUrl": "http://localhost:5000"}]
                )
                return jsonify(_kakao_resp(
                    [{"simpleText": {"text": part1}}, card],
                    _KAKAO_QUICK
                ))
            except Exception as e:
                app.logger.error(f"kakao_skill AI error: {e}")
                return _kakao_text(
                    "잠시 AI 처리 중 오류가 발생했습니다.\n다시 질문하시거나 웹 상담을 이용해 주세요.",
                    _KAKAO_QUICK
                )
        else:
            # Mock 모드 안내
            return _kakao_text(
                f"[{utterance}]에 대한 상담입니다.\n\n"
                "현재 AI 서버 연결 준비 중입니다.\n"
                "더 정확한 상담은 웹 채팅을 이용해 주세요.",
                _KAKAO_QUICK
            )
    except Exception as e:
        app.logger.error(f"kakao_skill error: {e}")
        return _kakao_text("서비스 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")


@app.route('/kakao/skill', methods=['GET'])
def kakao_skill_health():
    """스킬 서버 헬스체크 (카카오 연결 테스트용)"""
    return jsonify({"status": "ok", "service": "DIOBIO_BOT", "version": "1.0"})

@app.route('/diobio')
def diobio_homepage():
    return '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>DIOBIO — AI 웰니스 건강 파트너</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Apple SD Gothic Neo","Noto Sans KR",sans-serif;color:#1e293b;line-height:1.6}
a{text-decoration:none;color:inherit}

/* 네비 */
nav{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.95);backdrop-filter:blur(10px);
  border-bottom:1px solid #e2e8f0;padding:0 24px;display:flex;align-items:center;justify-content:space-between;height:60px}
.nav-logo{font-size:22px;font-weight:900;background:linear-gradient(135deg,#10b981,#0284c7);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.nav-links{display:flex;gap:28px;font-size:14px;font-weight:500;color:#475569}
.nav-links a:hover{color:#10b981}
.nav-cta{background:linear-gradient(135deg,#10b981,#059669);color:#fff;border:none;
  padding:8px 20px;border-radius:20px;font-size:13px;font-weight:700;cursor:pointer}
.nav-cta:hover{opacity:.9}

/* 히어로 */
.hero{background:linear-gradient(135deg,#f0fdf4 0%,#e0f2fe 50%,#f0fdf4 100%);
  padding:80px 24px 60px;text-align:center}
.hero-badge{display:inline-block;background:#dcfce7;color:#166534;font-size:12px;font-weight:700;
  padding:6px 16px;border-radius:20px;margin-bottom:20px}
.hero h1{font-size:clamp(28px,5vw,52px);font-weight:900;line-height:1.2;margin-bottom:16px}
.hero h1 span{background:linear-gradient(135deg,#10b981,#0284c7);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hero p{font-size:clamp(14px,2vw,18px);color:#475569;max-width:560px;margin:0 auto 32px}
.hero-btns{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
.btn-primary{background:linear-gradient(135deg,#10b981,#059669);color:#fff;border:none;
  padding:14px 32px;border-radius:12px;font-size:15px;font-weight:700;cursor:pointer}
.btn-primary:hover{opacity:.9;transform:translateY(-1px)}
.btn-kakao{background:#FEE500;color:#191600;border:none;
  padding:14px 32px;border-radius:12px;font-size:15px;font-weight:700;cursor:pointer}
.btn-kakao:hover{opacity:.9;transform:translateY(-1px)}
.hero-stats{display:flex;gap:32px;justify-content:center;margin-top:48px;flex-wrap:wrap}
.stat{text-align:center}
.stat-num{font-size:28px;font-weight:900;color:#10b981}
.stat-label{font-size:12px;color:#64748b;margin-top:2px}

/* 섹션 공통 */
section{padding:72px 24px}
.section-title{text-align:center;font-size:clamp(22px,3vw,32px);font-weight:800;margin-bottom:8px}
.section-sub{text-align:center;color:#64748b;font-size:15px;margin-bottom:48px}
.container{max-width:1100px;margin:0 auto}

/* 서비스 카드 */
.services{background:#fff}
.service-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px}
.service-card{background:#f8fafc;border-radius:20px;padding:28px;border:1.5px solid #e2e8f0;
  transition:transform .2s,box-shadow .2s}
.service-card:hover{transform:translateY(-4px);box-shadow:0 12px 40px rgba(16,185,129,.12)}
.service-icon{font-size:40px;margin-bottom:16px}
.service-name{font-size:16px;font-weight:700;margin-bottom:8px}
.service-desc{font-size:13px;color:#64748b;line-height:1.6}

/* 작동 방식 */
.how{background:linear-gradient(135deg,#f0fdf4,#e0f2fe)}
.steps{display:flex;gap:0;justify-content:center;flex-wrap:wrap;position:relative}
.step{text-align:center;max-width:260px;padding:24px 16px;position:relative}
.step-num{width:48px;height:48px;background:linear-gradient(135deg,#10b981,#059669);
  color:#fff;border-radius:50%;font-size:18px;font-weight:900;
  display:flex;align-items:center;justify-content:center;margin:0 auto 16px}
.step-title{font-size:15px;font-weight:700;margin-bottom:8px}
.step-desc{font-size:13px;color:#475569;line-height:1.6}
.step-arrow{font-size:24px;color:#10b981;align-self:flex-start;margin-top:36px;padding:0 4px}

/* 요금제 */
.pricing{background:#fff}
.plan-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}
.plan-card{border-radius:20px;padding:32px;border:2px solid #e2e8f0;position:relative;
  transition:transform .2s,box-shadow .2s}
.plan-card:hover{transform:translateY(-4px)}
.plan-card.popular{border-color:#10b981;background:#f0fdf4}
.plan-popular-badge{position:absolute;top:-14px;left:50%;transform:translateX(-50%);
  background:linear-gradient(135deg,#10b981,#059669);color:#fff;
  font-size:12px;font-weight:700;padding:5px 16px;border-radius:20px;white-space:nowrap}
.plan-name{font-size:18px;font-weight:800;margin-bottom:4px}
.plan-price{font-size:32px;font-weight:900;color:#10b981;margin-bottom:4px}
.plan-price span{font-size:14px;font-weight:500;color:#64748b}
.plan-desc{font-size:13px;color:#64748b;margin-bottom:20px;padding-bottom:20px;border-bottom:1px solid #e2e8f0}
.plan-features{list-style:none;display:flex;flex-direction:column;gap:10px;margin-bottom:28px}
.plan-features li{font-size:13px;color:#374151;display:flex;gap:8px;align-items:flex-start}
.plan-features li::before{content:"✓";color:#10b981;font-weight:700;flex-shrink:0}
.plan-btn{width:100%;padding:12px;border-radius:10px;font-size:14px;font-weight:700;
  cursor:pointer;border:none;background:linear-gradient(135deg,#10b981,#059669);color:#fff}
.plan-card.popular .plan-btn{background:linear-gradient(135deg,#059669,#047857)}

/* 후기 */
.reviews{background:#f8fafc}
.review-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}
.review-card{background:#fff;border-radius:16px;padding:24px;border:1px solid #e2e8f0}
.review-stars{color:#f59e0b;font-size:14px;margin-bottom:10px}
.review-text{font-size:13px;color:#374151;line-height:1.7;margin-bottom:14px}
.review-author{font-size:12px;color:#94a3b8;font-weight:600}

/* CTA 섹션 */
.cta-section{background:linear-gradient(135deg,#064e3b,#065f46);color:#fff;text-align:center;padding:72px 24px}
.cta-section h2{font-size:clamp(24px,4vw,40px);font-weight:900;margin-bottom:12px}
.cta-section p{font-size:16px;opacity:.85;margin-bottom:36px;max-width:500px;margin-left:auto;margin-right:auto}
.cta-btns{display:flex;gap:16px;justify-content:center;flex-wrap:wrap}
.cta-btn-kakao{background:#FEE500;color:#191600;padding:16px 36px;border-radius:14px;
  font-size:15px;font-weight:700;cursor:pointer;border:none}
.cta-btn-consult{background:rgba(255,255,255,.15);color:#fff;border:2px solid rgba(255,255,255,.4);
  padding:16px 36px;border-radius:14px;font-size:15px;font-weight:700;cursor:pointer}
.cta-btn-consult:hover{background:rgba(255,255,255,.25)}

/* 푸터 */
footer{background:#0f172a;color:#94a3b8;padding:48px 24px 32px}
.footer-inner{max-width:1100px;margin:0 auto;display:flex;gap:48px;flex-wrap:wrap;justify-content:space-between}
.footer-brand .logo{font-size:24px;font-weight:900;color:#10b981;margin-bottom:10px}
.footer-brand p{font-size:13px;line-height:1.8}
.footer-links h4{font-size:14px;font-weight:700;color:#e2e8f0;margin-bottom:12px}
.footer-links ul{list-style:none;display:flex;flex-direction:column;gap:8px}
.footer-links li{font-size:13px;cursor:pointer}
.footer-links li:hover{color:#10b981}
.footer-bottom{max-width:1100px;margin:32px auto 0;padding-top:24px;
  border-top:1px solid #1e293b;display:flex;justify-content:space-between;
  flex-wrap:wrap;gap:8px;font-size:12px}
.kakao-float{position:fixed;bottom:24px;right:24px;background:#FEE500;
  border-radius:50%;width:56px;height:56px;display:flex;align-items:center;justify-content:center;
  font-size:26px;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,.2);z-index:999}
.kakao-float:hover{transform:scale(1.1)}

@media(max-width:640px){
  .nav-links{display:none}
  .steps{flex-direction:column;align-items:center}
  .step-arrow{display:none}
}
</style>
</head>
<body>

<nav>
  <div class="nav-logo">DIOBIO</div>
  <div class="nav-links">
    <a href="#services">서비스</a>
    <a href="#how">이용방법</a>
    <a href="#pricing">요금제</a>
    <a href="#reviews">후기</a>
  </div>
  <button class="nav-cta" onclick="openKakaoChannel()">무료 상담 받기</button>
</nav>

<!-- 히어로 -->
<section class="hero">
  <div class="hero-badge">AI 기반 개인 맞춤 웰니스 플랫폼</div>
  <h1>당신의 건강을<br><span>AI가 분석</span>하고 케어합니다</h1>
  <p>DIOBIO Balance Check로 나만의 건강 유형을 파악하고, 맞춤 식품·운동·영양제·여행까지 한 번에 관리하세요.</p>
  <div class="hero-btns">
    <button class="btn-primary" onclick="location.href='/'">Balance Check 시작하기 →</button>
    <button class="btn-kakao" onclick="openKakaoChannel()">💬 카카오 상담하기</button>
  </div>
  <div class="hero-stats">
    <div class="stat"><div class="stat-num">6가지</div><div class="stat-label">건강 유형 분석</div></div>
    <div class="stat"><div class="stat-num">24종</div><div class="stat-label">맞춤 식품 추천</div></div>
    <div class="stat"><div class="stat-num">24곳</div><div class="stat-label">웰니스 여행지</div></div>
    <div class="stat"><div class="stat-num">AI</div><div class="stat-label">개인 맞춤 케어</div></div>
  </div>
</section>

<!-- 서비스 -->
<section class="services" id="services">
  <div class="container">
    <div class="section-title">DIOBIO 핵심 서비스</div>
    <div class="section-sub">건강의 모든 영역을 AI가 통합 관리합니다</div>
    <div class="service-grid">
      <div class="service-card">
        <div class="service-icon">🩺</div>
        <div class="service-name">AI Balance Check</div>
        <div class="service-desc">6가지 건강 유형 정밀 분석. 에너지·피부·모발·수면·대사·복합 유형별 맞춤 솔루션을 즉시 제공합니다.</div>
      </div>
      <div class="service-card">
        <div class="service-icon">🥗</div>
        <div class="service-name">DIOFARM 맞춤 식품</div>
        <div class="service-desc">건강 유형에 맞는 기능성 식품 24종 추천. 네이버 쇼핑 연동으로 바로 구매까지 가능합니다.</div>
      </div>
      <div class="service-card">
        <div class="service-icon">✈️</div>
        <div class="service-name">웰니스 여행</div>
        <div class="service-desc">건강 유형별 국내 웰니스 여행지 24곳 추천. 산림치유·해양치유·디톡스 리트릿·템플스테이 등.</div>
      </div>
      <div class="service-card">
        <div class="service-icon">💊</div>
        <div class="service-name">영양제 솔루션</div>
        <div class="service-desc">유형별 맞춤 영양제 조합 제안. 과잉 섭취 없이 꼭 필요한 영양소만 정확하게 안내합니다.</div>
      </div>
      <div class="service-card">
        <div class="service-icon">💉</div>
        <div class="service-name">GLP-1 원격 상담</div>
        <div class="service-desc">대사·비만 유형 전용. GLP-1(혈당 조절 장호르몬 기반 비만·당뇨 치료제) 원격 의료 상담 연계 서비스.</div>
      </div>
      <div class="service-card">
        <div class="service-icon">🛡️</div>
        <div class="service-name">건강 보험 연계</div>
        <div class="service-desc">AI 보험 상담과 연동하여 건강 유형에 맞는 보험 상품을 추천하고, 건강체 할인 혜택도 안내합니다.</div>
      </div>
    </div>
  </div>
</section>

<!-- 이용 방법 -->
<section class="how" id="how">
  <div class="container">
    <div class="section-title">이용 방법</div>
    <div class="section-sub">3단계로 나만의 웰니스 플랜을 완성하세요</div>
    <div class="steps">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-title">Balance Check</div>
        <div class="step-desc">7가지 간단한 질문으로 나의 건강 유형을 AI가 정밀 분석합니다.</div>
      </div>
      <div class="step-arrow">→</div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-title">맞춤 솔루션 확인</div>
        <div class="step-desc">식품·운동·영양제·병원·여행 솔루션을 유형별로 즉시 제공받습니다.</div>
      </div>
      <div class="step-arrow">→</div>
      <div class="step">
        <div class="step-num">3</div>
        <div class="step-title">전문가 상담 & 구독</div>
        <div class="step-desc">카카오 채널로 전문가 1:1 상담 후 DIOBIO 구독으로 지속 관리합니다.</div>
      </div>
    </div>
  </div>
</section>

<!-- 요금제 -->
<section class="pricing" id="pricing">
  <div class="container">
    <div class="section-title">구독 요금제</div>
    <div class="section-sub">건강 관리 목표에 맞는 플랜을 선택하세요</div>
    <div class="plan-grid">

      <div class="plan-card">
        <div class="plan-name">Basic</div>
        <div class="plan-price">무료<span> / 월</span></div>
        <div class="plan-desc">처음 시작하는 분들을 위한 기본 플랜</div>
        <ul class="plan-features">
          <li>AI Balance Check (월 1회)</li>
          <li>건강 유형 분석 결과</li>
          <li>맞춤 식품 추천 (4종)</li>
          <li>웰니스 여행 추천 (4곳)</li>
          <li>보험 상담 AI 연동</li>
        </ul>
        <button class="plan-btn" onclick="location.href='/'">무료 시작하기</button>
      </div>

      <div class="plan-card popular">
        <div class="plan-popular-badge">가장 인기 있는 플랜</div>
        <div class="plan-name">Premium</div>
        <div class="plan-price">29,900<span>원 / 월</span></div>
        <div class="plan-desc">건강 관리를 체계적으로 시작하는 분들을 위한 플랜</div>
        <ul class="plan-features">
          <li>AI Balance Check (무제한)</li>
          <li>맞춤 식품 추천 전체 (24종)</li>
          <li>웰니스 여행 전체 (24곳)</li>
          <li>영양제 1:1 맞춤 처방</li>
          <li>카카오 전문가 상담 (월 2회)</li>
          <li>GLP-1 원격 상담 우선 연결</li>
          <li>건강체 보험료 할인 분석</li>
        </ul>
        <button class="plan-btn" onclick="openKakaoChannel()">구독 신청하기</button>
      </div>

      <div class="plan-card">
        <div class="plan-name">VIP</div>
        <div class="plan-price">89,000<span>원 / 월</span></div>
        <div class="plan-desc">최상의 건강 케어를 원하는 분들을 위한 프리미엄 플랜</div>
        <ul class="plan-features">
          <li>Premium 모든 혜택 포함</li>
          <li>카카오 전문가 상담 (무제한)</li>
          <li>GLP-1 처방 원격 진료 연계</li>
          <li>DIOFARM 식품 월정액 배송</li>
          <li>웰니스 여행 패키지 할인 20%</li>
          <li>검사 키트 분기별 무료 제공</li>
          <li>건강 포트폴리오 전담 관리</li>
        </ul>
        <button class="plan-btn" onclick="openKakaoChannel()">VIP 상담 신청</button>
      </div>

    </div>
  </div>
</section>

<!-- 후기 -->
<section class="reviews" id="reviews">
  <div class="container">
    <div class="section-title">이용 후기</div>
    <div class="section-sub">DIOBIO와 함께 건강을 되찾은 분들의 이야기</div>
    <div class="review-grid">
      <div class="review-card">
        <div class="review-stars">★★★★★</div>
        <div class="review-text">"Balance Check를 통해 제가 수면·스트레스 유형인 걸 처음 알았어요. 추천해준 마그네슘과 L-테아닌을 복용하고 수면의 질이 정말 달라졌습니다."</div>
        <div class="review-author">김*영 · 38세 직장인 · Premium 구독</div>
      </div>
      <div class="review-card">
        <div class="review-stars">★★★★★</div>
        <div class="review-text">"대사 유형으로 나왔는데, 추천해준 제주 팜스테이 다녀오고 나서 체중이 3kg 빠졌어요. 웰니스 여행 추천이 이렇게 실질적인 효과가 있을 줄 몰랐습니다."</div>
        <div class="review-author">이*준 · 45세 자영업자 · VIP 구독</div>
      </div>
      <div class="review-card">
        <div class="review-stars">★★★★☆</div>
        <div class="review-text">"카카오 상담 연결이 정말 빠르고 친절해요. GLP-1 원격 진료도 연계해줘서 오프라인 병원 방문 없이 처방받을 수 있어 편리했습니다."</div>
        <div class="review-author">박*숙 · 52세 주부 · Premium 구독</div>
      </div>
    </div>
  </div>
</section>

<!-- CTA -->
<section class="cta-section">
  <h2>지금 바로 시작하세요</h2>
  <p>AI Balance Check는 무료입니다. 지금 바로 나의 건강 유형을 확인하고 맞춤 케어를 받아보세요.</p>
  <div class="cta-btns">
    <button class="cta-btn-kakao" onclick="openKakaoChannel()">💬 카카오 상담하기</button>
    <button class="cta-btn-consult" onclick="location.href='/'">무료 Balance Check →</button>
  </div>
</section>

<!-- 푸터 -->
<footer>
  <div class="footer-inner">
    <div class="footer-brand">
      <div class="logo">DIOBIO</div>
      <p>AI 기반 개인 맞춤 웰니스 플랫폼<br>
      대한민국 헬스케어의 미래를 만들어갑니다.<br><br>
      이노베이션 존 데이터 기반 정밀 건강 분석<br>
      보험·금융·웰니스 통합 AI 서비스</p>
    </div>
    <div class="footer-links">
      <h4>서비스</h4>
      <ul>
        <li onclick="location.href='/'">Balance Check</li>
        <li>DIOFARM 식품</li>
        <li>웰니스 여행</li>
        <li>GLP-1 원격 상담</li>
      </ul>
    </div>
    <div class="footer-links">
      <h4>고객 지원</h4>
      <ul>
        <li onclick="openKakaoChannel()">카카오 상담</li>
        <li>이용약관</li>
        <li>개인정보처리방침</li>
        <li>공지사항</li>
      </ul>
    </div>
    <div class="footer-links">
      <h4>상담 채널</h4>
      <ul>
        <li onclick="openKakaoChannel()">💬 카카오톡 채널</li>
        <li>운영시간: 평일 09:00~18:00</li>
        <li>주말·공휴일 AI 자동 응대</li>
      </ul>
    </div>
  </div>
  <div class="footer-bottom">
    <span>© 2026 DIOBIO. All rights reserved.</span>
    <span>본 서비스는 건강 정보 제공 목적이며, 의료 진단을 대체하지 않습니다.</span>
  </div>
</footer>

<!-- 카카오 플로팅 버튼 -->
<div class="kakao-float" onclick="openKakaoChannel()" title="카카오 상담하기">💬</div>

<script>
function openKakaoChannel() {
  window.open('http://pf.kakao.com/_xcPnxnX/chat', '_blank');
}
</script>
</body>
</html>'''


if __name__ == '__main__':
    print("=" * 50)
    print("  보험 상담 AI 웹 서버 시작")
    print("=" * 50)
    print("  접속 주소: http://localhost:5000")
    print("  종료: Ctrl+C")
    print("=" * 50)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
