# -*- coding: utf-8 -*-
"""
2026 금융 AI Challenge 공모전 서류 PDF 생성
- 기획서.pdf
- 기능명세서.pdf
"""

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── 한글 폰트 등록 ────────────────────────────────────────────────
MALGUN = "C:/Windows/Fonts/malgun.ttf"
MALGUN_BOLD = "C:/Windows/Fonts/malgunbd.ttf"

pdfmetrics.registerFont(TTFont("Malgun", MALGUN))
pdfmetrics.registerFont(TTFont("MalgunBold", MALGUN_BOLD))

W, H = A4
MARGIN = 20 * mm

# ── 공통 스타일 ───────────────────────────────────────────────────
styles = getSampleStyleSheet()

TITLE_STYLE = ParagraphStyle(
    "Title", fontName="MalgunBold", fontSize=16, leading=22,
    textColor=colors.HexColor("#1F3864"), spaceAfter=4 * mm, alignment=1
)
SECTION_STYLE = ParagraphStyle(
    "Section", fontName="MalgunBold", fontSize=11, leading=16,
    textColor=colors.white, spaceAfter=2 * mm
)
BODY_STYLE = ParagraphStyle(
    "Body", fontName="Malgun", fontSize=9.5, leading=15,
    textColor=colors.black, spaceAfter=1 * mm
)
BULLET_STYLE = ParagraphStyle(
    "Bullet", fontName="Malgun", fontSize=9.5, leading=15,
    textColor=colors.black, leftIndent=8, spaceAfter=1 * mm
)
SMALL_STYLE = ParagraphStyle(
    "Small", fontName="Malgun", fontSize=9, leading=14,
    textColor=colors.HexColor("#333333")
)
HEADER_NOTE = ParagraphStyle(
    "HeaderNote", fontName="Malgun", fontSize=8.5, leading=13,
    textColor=colors.HexColor("#555555"), alignment=2
)

BLUE = colors.HexColor("#1F3864")
LIGHT_BLUE = colors.HexColor("#D6E4F0")
ACCENT = colors.HexColor("#2E75B6")


def section_header(text):
    """파란 배경 섹션 헤더 (표로 구현)."""
    t = Table([[Paragraph(text, SECTION_STYLE)]], colWidths=[W - 2 * MARGIN])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLUE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [BLUE]),
    ]))
    return t


def info_table(label_val_pairs):
    """팀명/구성원 정보 테이블."""
    data = [[
        Paragraph(lbl, ParagraphStyle("lbl", fontName="MalgunBold", fontSize=10,
                                      textColor=BLUE, alignment=1)),
        Paragraph(val, ParagraphStyle("val", fontName="Malgun", fontSize=10,
                                      textColor=BLUE, alignment=1))
    ] for lbl, val in label_val_pairs]
    t = Table(data, colWidths=[55 * mm, W - 2 * MARGIN - 55 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLUE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BLUE),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def content_box(content_paragraphs):
    """본문 박스 (테두리 있는 표)."""
    rows = [[p] for p in content_paragraphs]
    t = Table(rows, colWidths=[W - 2 * MARGIN])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#AAAAAA")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (0, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (1, 0), (-1, -1), 3),
    ]))
    return t


def bp(text):
    return Paragraph("- " + text, BULLET_STYLE)


def body(text):
    return Paragraph(text, BODY_STYLE)


def sp(n=4):
    return Spacer(1, n * mm)


# ═══════════════════════════════════════════════════════════════
#  기획서 생성
# ═══════════════════════════════════════════════════════════════
def build_planning():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "2026_금융AI챌린지_기획서.pdf")
    doc = SimpleDocTemplate(out, pagesize=A4,
                            leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    story = []

    # ── 헤더 타이틀 ──────────────────────────────────────────
    header_data = [[
        Paragraph("첨부 1", ParagraphStyle("tag", fontName="MalgunBold", fontSize=12,
                                           textColor=colors.white, alignment=1)),
        Paragraph("2026 금융 AI Challenge  기획서",
                  ParagraphStyle("htitle", fontName="MalgunBold", fontSize=14,
                                 textColor=BLUE, alignment=1))
    ]]
    header_t = Table(header_data, colWidths=[30 * mm, W - 2 * MARGIN - 30 * mm])
    header_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), BLUE),
        ("BACKGROUND", (1, 0), (1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 1.5, BLUE),
        ("INNERGRID", (0, 0), (-1, -1), 1, BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header_t)
    story.append(sp(5))

    # ── 팀 정보 ──────────────────────────────────────────────
    story.append(info_table([
        ("팀명", "InsurAI Team"),
        ("구성원 성명", "이종재 (팀장)"),
    ]))
    story.append(Paragraph(
        "( * 필수항목)",
        ParagraphStyle("note", fontName="Malgun", fontSize=8.5,
                       textColor="#555555", alignment=2, spaceBefore=3)
    ))
    story.append(sp(4))

    # ── 1. 서비스 명칭 ────────────────────────────────────────
    story.append(section_header("1. 서비스 명칭*"))
    story.append(sp(1))
    story.append(content_box([
        body("<b>InsurAI</b>  —  AI 기반 개인 맞춤형 보험 포트폴리오 설계 플랫폼"),
        body("(Insurance + AI의 합성어 / 영문 슬로건: <i>\"Your AI Insurance Advisor, 24/7\"</i>)"),
    ]))
    story.append(sp(4))

    # ── 2. 아이디어 기획 핵심내용 ─────────────────────────────
    story.append(section_header("2. 아이디어 기획 핵심내용(요약)*"))
    story.append(sp(1))
    story.append(content_box([
        bp("생성형 AI(GPT-4o)가 사용자의 나이·성별·건강 상태·예산을 종합 분석하여 "
           "최적 보험 포트폴리오를 자동 설계"),
        bp("생명보험·실손보험·암보험·치과보험 전 영역을 단일 대화 인터페이스로 통합 상담·비교"),
        bp("보험다모아 공시 엑셀 데이터 + 금융감독원(FSS) API 실시간 연동으로 "
           "최신 상품 정보 제공 (정보 비대칭 해소)"),
        bp("ChromaDB 벡터 RAG 기반 보험 지식베이스로 복잡한 보험 용어·약관을 "
           "평이한 언어로 설명"),
        bp("건강위험도 AI 모델(ROC-AUC 0.85+) + 신용점수 5등급 분류로 "
           "개인화된 위험 프로파일 생성"),
        bp("멀티에이전트 구조: 오케스트레이터 + 개인화 추천 서브에이전트 협업"),
    ]))
    story.append(sp(4))

    # ── 3. 문제 정의 및 제안 배경 ────────────────────────────
    story.append(section_header("3. 문제 정의 및 제안 배경*"))
    story.append(sp(1))
    story.append(content_box([
        body("<b>[해결하고자 하는 금융 문제]</b>"),
        bp("정보 비대칭성: 보험사·설계사는 수백 가지 상품 정보를 보유하나 "
           "소비자는 접근 어려움 — 불완전 판매·과잉 가입 만연"),
        bp("상품 복잡성: 특약, 면책 조항, 갱신형/비갱신형 구분 등 전문 지식 없이 "
           "이해하기 어려운 구조"),
        bp("과소보장 문제: 금융감독원 2025년 보고서 기준 실손보험 비급여 청구 거절율 "
           "18.3%, 필요 보장을 받지 못하는 사례 다수"),
        bp("비교 수단 부재: 기존 보험 비교 플랫폼은 단순 가격 비교 수준 — "
           "개인 상황 맞춤 추천 부재"),
        sp(1),
        body("<b>[특정 금융 고객 및 채널 선택 이유]</b>"),
        bp("주요 타깃: 사회초년생(20~30대) 및 보험 재설계 필요 중장년층(40~60대)"),
        bp("채널: 모바일 웹/PC 웹 브라우저 — 언제 어디서나 접근 가능한 챗봇 인터페이스"),
        bp("사회초년생은 첫 보험 가입 시 정보 부족으로 인한 잘못된 선택 빈도 높음; "
           "중장년층은 기존 가입 보험의 적정성 재검토 수요 증가"),
    ]))
    story.append(sp(4))

    # ── 4. 서비스 컨셉 및 차별성 ──────────────────────────────
    story.append(section_header("4. 서비스 컨셉 및 차별성*"))
    story.append(sp(1))
    story.append(content_box([
        body("<b>[핵심 컨셉]</b>  \"AI 보험 전문 어드바이저 — 24시간 · 무료 · 개인 맞춤\""),
        sp(1),
        body("<b>[기존 금융 앱 대비 차별성]</b>"),
        bp("단순 가격 비교 → <b>AI 포트폴리오 설계</b>: 생명/의료/암/치과 통합 최적화"),
        bp("단방향 정보 제공 → <b>대화형 상담</b>: 자연어로 질문하면 즉시 전문가급 답변"),
        bp("정적 DB → <b>실시간 공시 데이터</b>: 보험다모아 엑셀 자동 반영 + FSS API"),
        bp("일반 추천 → <b>건강위험도 기반 개인화</b>: AI 모델이 흡연·BMI·병력 분석"),
        bp("단일 에이전트 → <b>멀티에이전트 AI</b>: 오케스트레이터 + 추천 서브에이전트 협업"),
        bp("기존 챗봇(단순 Q&A) → <b>Tool Calling 기반 실시간 계산</b>: "
           "나이·성별별 보험료 즉시 산출"),
    ]))
    story.append(sp(4))

    # ── 5. 활용 데이터 및 생성형 AI ──────────────────────────
    story.append(section_header("5. 활용 데이터 및 생성형 AI 모델 적용 방안*"))
    story.append(sp(1))

    data5 = [
        [Paragraph("<b>데이터 종류</b>", SMALL_STYLE),
         Paragraph("<b>수집·활용 방안</b>", SMALL_STYLE),
         Paragraph("<b>활용 목적</b>", SMALL_STYLE)],
        [Paragraph("보험다모아 공시 엑셀\n(*.xls, 11종)", SMALL_STYLE),
         Paragraph("보험다모아 사이트에서 주기적 다운로드;\nexcel_loader.py 자동 파싱", SMALL_STYLE),
         Paragraph("실시간 상품 보험료 조회 및 비교", SMALL_STYLE)],
        [Paragraph("금융감독원 FSS API", SMALL_STYLE),
         Paragraph("finlife.fss.or.kr 오픈API 활용\n(연금저축보험 실시간 조회)", SMALL_STYLE),
         Paragraph("최신 공시 금리·상품 정보", SMALL_STYLE)],
        [Paragraph("보험 지식베이스\n(ChromaDB 벡터 DB)", SMALL_STYLE),
         Paragraph("약관·보험 용어·비교 가이드를\nChromaDB에 임베딩 저장", SMALL_STYLE),
         Paragraph("RAG 기반 전문 지식 검색", SMALL_STYLE)],
        [Paragraph("건강검진 데이터\n(가명처리 샘플)", SMALL_STYLE),
         Paragraph("건강위험도 AI 모델 학습용;\n실제 서비스는 사용자 자가입력", SMALL_STYLE),
         Paragraph("개인 건강위험도 프로파일링", SMALL_STYLE)],
        [Paragraph("DuckDuckGo 실시간 검색", SMALL_STYLE),
         Paragraph("API 키 불필요; 웹 검색 도구\n(web_search_tool.py)", SMALL_STYLE),
         Paragraph("최신 보험 뉴스·정책 반영", SMALL_STYLE)],
    ]
    t5 = Table(data5, colWidths=[45 * mm, 75 * mm, W - 2 * MARGIN - 120 * mm])
    t5.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, BLUE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE),
        ("FONTNAME", (0, 0), (-1, 0), "MalgunBold"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t5)
    story.append(sp(3))
    story.append(content_box([
        body("<b>[생성형 AI 모델 활용 방안]</b>"),
        bp("모델: GPT-4o (OpenAI) — Tool Calling 기반 오케스트레이터"),
        bp("역할 ①  의도 파악: 사용자 발화에서 보험 유형·나이·예산·건강상태 추출"),
        bp("역할 ②  도구 선택: 상황에 맞는 도구(엑셀검색/RAG/FSS API/웹검색) 자동 호출"),
        bp("역할 ③  포트폴리오 설계: 서브에이전트(GPT-4o)가 개인 프로파일 기반 최적 조합 생성"),
        bp("역할 ④  리스크 설명: 건강위험도·신용등급 결과를 평이한 언어로 해설"),
        bp("SSE(Server-Sent Events) 스트리밍으로 실시간 응답 전송"),
    ]))
    story.append(sp(4))

    # ── 6. 기대 효과 및 확장 가능성 ──────────────────────────
    story.append(section_header("6. 기대 효과 및 확장 가능성*"))
    story.append(sp(1))
    story.append(content_box([
        body("<b>[구체적 문제 해결 및 기대 효과]</b>"),
        bp("소비자 정보 비대칭 해소: 전문 설계사 상담 없이도 동등한 수준의 맞춤 정보 제공"),
        bp("보험료 절감 효과: 중복 보장 제거·최적 상품 선택으로 월 평균 3~5만원 절감 예상"),
        bp("불완전 판매 감소: AI 객관적 비교로 설계사 이해충돌 리스크 제거"),
        bp("보험 접근성 향상: 24/7 무료 상담 → 금융 소외계층(사회초년생, 디지털 취약계층)"),
        sp(1),
        body("<b>[실질적 혜택]</b>"),
        bp("금융 소비자: 복잡한 보험 구조를 쉽게 이해, 최적 보장 설계, 비용 절감"),
        bp("금융 서비스 제공자: AI 상담 자동화로 상담 인력 비용 절감, 고객 만족도 향상"),
        sp(1),
        body("<b>[확장 가능성]</b>"),
        bp("단기: 보험 청구 자동화 연계 (AI가 청구 서류 작성·제출 대행)"),
        bp("중기: 연금·펀드·적금 등 전체 금융 포트폴리오로 서비스 확장"),
        bp("장기: 의료·건강 데이터 연동(마이데이터) → 실시간 건강 기반 보험료 재산정"),
        bp("타 영역 확장: 헬스케어 앱과 연동한 건강관리 + 보험 통합 플랫폼"),
    ]))
    story.append(sp(4))

    # ── 7. 기타 ──────────────────────────────────────────────
    story.append(section_header("7. 기술 스택 및 시스템 구조"))
    story.append(sp(1))
    story.append(content_box([
        body("<b>[기술 스택]</b>"),
        bp("Backend: Python 3.13, Flask (SSE 스트리밍), OpenAI SDK"),
        bp("AI/ML: GPT-4o (Tool Calling), ChromaDB, sentence-transformers (ko-sroberta-multitask)"),
        bp("데이터: 보험다모아 엑셀(*.xls), FSS API, DuckDuckGo 웹검색"),
        bp("Frontend: 반응형 HTML/CSS/JS (Flask render_template_string)"),
        bp("배포: Python 웹서버 (로컬/클라우드 모두 지원)"),
        sp(1),
        body("<b>[멀티에이전트 구조]</b>"),
        bp("오케스트레이터(GPT-4o): 사용자 의도 분석 + 도구 선택 + 응답 생성"),
        bp("추천 서브에이전트(GPT-4o): 개인화 포트폴리오 최종 설계"),
        bp("도구 계층: 엑셀검색 > 웹검색 > 정적DB > ChromaDB RAG > FSS API"),
    ]))

    story.append(sp(6))
    story.append(Paragraph("- 1 -", ParagraphStyle("pg", fontName="Malgun", fontSize=9,
                                                    alignment=1, textColor="#888888")))

    doc.build(story)
    print("기획서 저장:", out)


# ═══════════════════════════════════════════════════════════════
#  기능명세서 생성
# ═══════════════════════════════════════════════════════════════
def build_spec():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "2026_금융AI챌린지_기능명세서.pdf")
    doc = SimpleDocTemplate(out, pagesize=A4,
                            leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    story = []

    # ── 헤더 타이틀 ──────────────────────────────────────────
    header_data = [[
        Paragraph("첨부 2", ParagraphStyle("tag", fontName="MalgunBold", fontSize=12,
                                           textColor=colors.white, alignment=1)),
        Paragraph("2026 금융 AI Challenge  기능 명세서",
                  ParagraphStyle("htitle", fontName="MalgunBold", fontSize=14,
                                 textColor=BLUE, alignment=1))
    ]]
    header_t = Table(header_data, colWidths=[30 * mm, W - 2 * MARGIN - 30 * mm])
    header_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), BLUE),
        ("BACKGROUND", (1, 0), (1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 1.5, BLUE),
        ("INNERGRID", (0, 0), (-1, -1), 1, BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header_t)
    story.append(sp(5))

    # ── 팀 정보 ──────────────────────────────────────────────
    story.append(info_table([
        ("팀명", "InsurAI Team"),
        ("구성원 성명", "이종재 (팀장)"),
    ]))
    story.append(Paragraph(
        "( * 필수항목)",
        ParagraphStyle("note", fontName="Malgun", fontSize=8.5,
                       textColor="#555555", alignment=2, spaceBefore=3)
    ))
    story.append(sp(4))

    # ── 1. MVP 구현 범위 ──────────────────────────────────────
    story.append(section_header("1. MVP 구현 범위*"))
    story.append(sp(1))
    story.append(content_box([
        body("<b>[구현 완료 기능]</b>"),
        bp("AI 대화형 보험 상담 챗봇 (GPT-4o Tool Calling 기반, SSE 스트리밍)"),
        bp("보험 상품 검색 및 비교: 생명보험·실손보험·암보험·치과보험 (4개 유형)"),
        bp("나이·성별 기반 실시간 보험료 산출 (보험다모아 엑셀 11종 연동)"),
        bp("건강위험도 AI 평가 (흡연·BMI·혈압·병력 입력 → 위험등급 출력)"),
        bp("신용점수 포트폴리오 분석 (NICE+KCB 점수 기반 5등급 분류)"),
        bp("개인화 보험 포트폴리오 추천 (GPT-4o 서브에이전트)"),
        bp("ChromaDB 벡터 RAG 보험 지식 검색"),
        bp("금융감독원 FSS API 연동 (연금저축보험 실시간 조회)"),
        bp("웹 인터페이스 (Flask, 반응형 디자인, Live/Mock 자동 전환 모드)"),
        sp(1),
        body("<b>[미구현 (향후 예정)]</b>"),
        bp("보험 청구 자동화 연동"),
        bp("마이데이터 API 실시간 건강 데이터 연동"),
        bp("회원가입·로그인·상담 이력 저장"),
    ]))
    story.append(sp(4))

    # ── 2. 주요 기능 목록 ────────────────────────────────────
    story.append(section_header("2. 주요 기능 목록*"))
    story.append(sp(1))

    func_header = [
        Paragraph("<b>기능명</b>", SMALL_STYLE),
        Paragraph("<b>기능 설명</b>", SMALL_STYLE),
        Paragraph("<b>관련 화면</b>", SMALL_STYLE),
        Paragraph("<b>구현 상태</b>", SMALL_STYLE),
    ]
    funcs = [
        ("AI 보험 상담 챗봇",
         "자연어 대화로 보험 상품 추천·비교·설명.\nGPT-4o Tool Calling + SSE 스트리밍",
         "메인 채팅 화면", "완료"),
        ("보험 상품 검색",
         "유형(생명/실손/암/치과)·나이·예산·필요 조건\n으로 보험 상품 필터링 조회",
         "채팅 응답 카드", "완료"),
        ("실시간 보험료 산출",
         "보험다모아 엑셀 공시 데이터 기반\n나이·성별별 월 보험료 즉시 계산",
         "보험료 비교 테이블", "완료"),
        ("보험 상품 비교",
         "2~4개 상품 나란히 비교\n(보험료·보장·장단점·특약 비교표)",
         "비교 결과 테이블", "완료"),
        ("건강위험도 평가",
         "흡연·BMI·혈압·병력 입력 →\n개인 건강위험도 등급 및 추천 보험 유형 제시",
         "건강위험도 결과 화면", "완료"),
        ("신용점수 포트폴리오",
         "NICE·KCB 점수 입력 →\n5등급 분류 + 적정 보험 포트폴리오 산출",
         "신용점수 분석 화면", "완료"),
        ("보험 지식 검색",
         "ChromaDB 벡터 RAG로 보험 용어·약관·\n가이드 시맨틱 검색 (jhgan/ko-sroberta)",
         "채팅 응답 내 지식 인용", "완료"),
        ("FSS API 연동",
         "금융감독원 API로 연금저축보험\n최신 공시 상품 실시간 조회",
         "연금보험 조회 결과", "완료"),
        ("Live/Mock 자동 전환",
         "API 크레딧 확인 후 자동 전환\n(Live: GPT-4o / Mock: 로컬 도구)",
         "상태 표시 배지", "완료"),
        ("개인화 추천 리포트",
         "서브에이전트가 개인 정보 종합 →\n최적 보험 포트폴리오 보고서 생성",
         "추천 리포트 화면", "완료"),
    ]
    func_data = [func_header] + [
        [Paragraph(f[0], SMALL_STYLE), Paragraph(f[1], SMALL_STYLE),
         Paragraph(f[2], SMALL_STYLE),
         Paragraph(f[3], ParagraphStyle("done", fontName="MalgunBold", fontSize=9,
                                        textColor=ACCENT))]
        for f in funcs
    ]
    t2 = Table(func_data, colWidths=[38 * mm, 68 * mm, 40 * mm, 24 * mm])
    t2.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, BLUE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FBFF")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t2)
    story.append(sp(4))

    # ── 3. 사용자 이용 흐름 ──────────────────────────────────
    story.append(section_header("3. 사용자 이용 흐름*"))
    story.append(sp(1))

    flow_steps = [
        ("①", "접속", "배포 URL 접속 → 메인 채팅 화면 로드\n(Live/Mock 모드 자동 감지 후 표시)"),
        ("②", "질문 입력",
         "채팅창에 자연어 질문 입력\n예: \"45세 남성, 월 20만원으로 보험 추천해줘\""),
        ("③", "AI 분석",
         "GPT-4o가 의도 파악 → 적합한 도구 자동 선택\n(엑셀검색/RAG/FSS API/웹검색)"),
        ("④", "결과 출력",
         "SSE 스트리밍으로 실시간 추천 결과 표시\n(상품 카드·보험료 표·비교 테이블)"),
        ("⑤", "추가 상담",
         "\"두 상품 비교해줘\" / \"임플란트 보장 되는 거 알려줘\"\n등 후속 질문으로 대화 심화"),
        ("⑥", "건강·신용 분석",
         "건강위험도 평가 또는 신용점수 포트폴리오 요청 시\n별도 입력 폼 → AI 분석 리포트 출력"),
        ("⑦", "개인화 추천",
         "\"종합 보험 포트폴리오 만들어줘\" 요청 시\n서브에이전트가 개인화 최종 보고서 생성"),
    ]
    flow_data = [[
        Paragraph(s[0], ParagraphStyle("num", fontName="MalgunBold", fontSize=12,
                                       textColor=colors.white, alignment=1)),
        Paragraph(f"<b>{s[1]}</b>", SMALL_STYLE),
        Paragraph(s[2], SMALL_STYLE),
    ] for s in flow_steps]
    t3 = Table(flow_data, colWidths=[12 * mm, 30 * mm, W - 2 * MARGIN - 42 * mm])
    t3.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, BLUE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ("BACKGROUND", (0, 0), (0, -1), BLUE),
        ("ROWBACKGROUNDS", (1, 0), (2, -1),
         [colors.white, colors.HexColor("#F0F5FF")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t3)
    story.append(sp(4))

    # ── 4. AI 및 데이터 처리 방식 ────────────────────────────
    story.append(section_header("4. AI 및 데이터 처리 방식*"))
    story.append(sp(1))
    story.append(content_box([
        body("<b>[AI가 수행하는 역할]</b>"),
        bp("의도 분류: 사용자 발화에서 보험 유형·나이·성별·예산·건강상태 자동 추출"),
        bp("도구 오케스트레이션: Tool Calling으로 적합한 데이터 소스 자동 선택·호출"),
        bp("보험료 계산: 엑셀 데이터 기반 나이·성별별 보험료 즉시 산출"),
        bp("건강위험도 모델: 입력값 → 위험지수(0~100) + 등급(저/중/고위험) 출력"),
        bp("개인화 추천: 서브에이전트가 사용자 프로파일 종합 → 최적 포트폴리오 설계"),
        bp("RAG 지식 검색: 보험 용어·약관 질문 → ChromaDB에서 관련 문서 검색 후 답변"),
        sp(1),
        body("<b>[사용 데이터 및 입출력]</b>"),
        bp("입력: 나이, 성별, 예산, 건강 상태(흡연·BMI·혈압·병력), 신용점수(선택)"),
        bp("처리: 보험다모아 엑셀(11종) + ChromaDB 벡터 DB + FSS API + 웹 검색"),
        bp("출력: 추천 상품 목록(최대 5개), 보험료 비교표, 개인화 포트폴리오 리포트"),
        sp(1),
        body("<b>[개인정보 처리 방식]</b>"),
        bp("MVP 단계: 별도 회원가입 없음 — 세션 기반 임시 저장 (서버 재시작 시 삭제)"),
        bp("입력 정보(나이·건강상태)는 OpenAI API 전송 후 즉시 처리, 저장하지 않음"),
        bp("향후 마이데이터 연동 시 개인정보보호법 준수 및 암호화 처리 예정"),
    ]))
    story.append(sp(4))

    # ── 5. MVP 검증 방법 ─────────────────────────────────────
    story.append(section_header("5. MVP 검증 방법*"))
    story.append(sp(1))
    story.append(content_box([
        body("<b>[심사자 주요 기능 확인 절차]</b>"),
        bp("① 배포 URL 접속 → 채팅창 확인 (Live/Mock 모드 표시 확인)"),
        bp("② 아래 샘플 입력값으로 순서대로 입력 후 AI 응답 확인"),
        bp("③ 건강위험도 평가 및 신용점수 포트폴리오 기능 별도 테스트"),
        sp(1),
        body("<b>[테스트 샘플 입력값 및 예상 결과]</b>"),
    ]))
    story.append(sp(2))

    test_header = [
        Paragraph("<b>테스트 시나리오</b>", SMALL_STYLE),
        Paragraph("<b>입력값</b>", SMALL_STYLE),
        Paragraph("<b>예상 결과</b>", SMALL_STYLE),
    ]
    tests = [
        ("암보험 추천",
         "\"45세 남성, 월 10만원 예산\n암보험 추천해줘\"",
         "암보험 3종 추천 카드\n(월 보험료·보장 비교표)"),
        ("실손보험 비교",
         "\"4세대 실손보험 뭐가 좋아?\n비갱신형으로 찾아줘\"",
         "4세대 실손 상품 목록\n+ 갱신/비갱신 차이 설명"),
        ("치과보험",
         "\"임플란트 되는 치아보험\n어디가 제일 싸?\"",
         "치과보험 보험료 순위표\n+ 임플란트 대기기간 안내"),
        ("보험료 문의",
         "\"35세 여성 종신보험\n보험료 얼마야?\"",
         "종신보험 월 보험료\n나이·성별 맞춤 계산 결과"),
        ("건강위험도",
         "흡연: 예 / BMI: 28\n혈압: 135/85 입력",
         "위험지수 표시 + 권장 보험\n유형 (암보험 우선 권장)"),
        ("포트폴리오 설계",
         "\"40대 직장인, 월 30만원\n보험 포트폴리오 짜줘\"",
         "생명+실손+암 통합 포트폴리오\n추천 리포트 출력"),
    ]
    test_data = [test_header] + [
        [Paragraph(t[0], SMALL_STYLE), Paragraph(t[1], SMALL_STYLE),
         Paragraph(t[2], SMALL_STYLE)]
        for t in tests
    ]
    t5 = Table(test_data, colWidths=[35 * mm, 75 * mm, W - 2 * MARGIN - 110 * mm])
    t5.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, BLUE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FBFF")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t5)
    story.append(sp(3))

    story.append(content_box([
        body("<b>[실행 환경 및 브라우저 제한사항]</b>"),
        bp("권장 브라우저: Chrome 120+, Edge 120+, Firefox 115+ (IE 미지원)"),
        bp("실행 환경: Python 3.10+, pip install -r requirements.txt"),
        bp("필수 환경변수: OPENAI_API_KEY (.env 파일에 설정)"),
        bp("실행 명령어: python web_app.py → http://localhost:5000 접속"),
        sp(1),
        body("<b>[MVP 단계 제한사항]</b>"),
        bp("OPENAI_API_KEY 크레딧 없을 시 Mock 모드 자동 전환 (로컬 데이터 기반 응답)"),
        bp("ChromaDB 최초 실행 시 임베딩 모델 다운로드 필요 (~443MB, 약 2~5분)"),
        bp("보험다모아 엑셀은 현재 11종 포함 — 갱신 시 재다운로드 및 재구축 필요"),
        bp("회원가입·이력 저장 미구현 (세션 종료 시 대화 초기화)"),
        bp("FSS API는 연금저축보험 조회만 지원 (종신/실손/암/치과는 로컬 데이터)"),
    ]))

    story.append(sp(6))
    story.append(Paragraph("- 1 -", ParagraphStyle("pg", fontName="Malgun", fontSize=9,
                                                    alignment=1, textColor="#888888")))

    doc.build(story)
    print("기능명세서 저장:", out)


if __name__ == "__main__":
    build_planning()
    build_spec()
    print("PDF 생성 완료.")
