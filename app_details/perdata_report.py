# perdata_report.py
import streamlit as st
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
import os

# ==== 나눔고딕 폰트 등록 ====
# 현재 파일 기준으로 프로젝트의 fonts 폴더에 NanumGothic.ttf 가 있다고 가정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "NanumGothic.ttf")

if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("NanumGothic", FONT_PATH))
else:
    # 폰트 경로가 잘못됐을 때를 대비한 안내
    st.warning(f"한글 폰트 파일을 찾을 수 없습니다: {FONT_PATH}")

def generate_farm_report(filtered, selected_table, start_date, end_date, all_columns):

    st.subheader("📋 농가 리포트 생성")
    
    # 리포트 설정
    col1, col2, col3 = st.columns(3)
    with col1:
        report_vars = st.multiselect(
            "리포트에 포함할 센서",
            options=all_columns,
            default=all_columns[:3] if all_columns else []
        )
    with col2:
        period_type = st.selectbox("집계 기간", ["일별", "시간별", "전체"], index=2)
    with col3:
        include_anomaly = st.checkbox("이상치 표시 포함", value=True)
    
    if st.button("🚀 리포트 생성", type="primary") and report_vars:
        try:
            # PDF 버퍼 생성
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            base_styles = getSampleStyleSheet()

            # 나눔고딕이 적용된 스타일들 정의
            title_style = ParagraphStyle(
                "KoreanTitle",
                parent=base_styles["Title"],
                fontName="NanumGothic",
                fontSize=20,
                leading=26,
                alignment=1,  # center
            )
            normal_style = ParagraphStyle(
                "KoreanNormal",
                parent=base_styles["Normal"],
                fontName="NanumGothic",
                fontSize=11,
                leading=16,
            )
            small_style = ParagraphStyle(
                "KoreanSmall",
                parent=base_styles["Normal"],
                fontName="NanumGothic",
                fontSize=9,
                leading=13,
            )

            story = []
            
            # 1. 제목 페이지
            title = Paragraph(
                f"<font color='#1E88E5'>농가 센서 데이터 리포트</font><br/>"
                f"<font size=14>{selected_table}</font><br/>"
                f"<font size=11 color='#666'>{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}</font>",
                title_style,
            )
            story.extend([title, Spacer(1, 18)])
            
            # 2. 요약 통계 테이블
            summary_data = [["센서", "평균", "최대", "최소", "표준편차(σ)", "데이터 개수"]]
            for var in report_vars:
                series = filtered[var].dropna()
                if not series.empty:
                    summary_data.append([
                        var,
                        f"{series.mean():.2f}",
                        f"{series.max():.2f}",
                        f"{series.min():.2f}",
                        f"{series.std():.2f}",
                        f"{len(series):,}",
                    ])
            
            if len(summary_data) > 1:
                table = Table(
                    summary_data,
                    colWidths=[3*cm, 2*cm, 2*cm, 2*cm, 2.5*cm, 2.5*cm],
                    hAlign="CENTER",
                )
                table.setStyle([
                    ("FONTNAME", (0, 0), (-1, -1), "NanumGothic"),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#C7E6F5")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("TOPPADDING", (0, 1), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ])
                story.extend([table, Spacer(1, 16)])
            
            # 3. 분석 요약
            summary_text = Paragraph(
                (
                    f"<b>분석 요약</b><br/>"
                    f"• 분석 센서 수: {len(report_vars)}개<br/>"
                    f"• 전체 데이터 포인트: {len(filtered):,}개<br/>"
                    f"• 이상치 분석: {'포함' if include_anomaly else '제외'}"
                ),
                normal_style,
            )
            story.extend([summary_text, Spacer(1, 12)])
            
            # 4. 권장사항
            recommend_text = Paragraph(
                (
                    "<b>재배 환경 권장 범위</b><br/>"
                    "• 온도: 18–28°C (작물 종류에 따라 조정)<br/>"
                    "• 상대습도: 60–80% 유지 권장<br/>"
                    "• CO₂: 800–1200ppm 권장 범위<br/>"
                    "• 센서 이상치가 반복되면 장비 점검 또는 보정 필요"
                ),
                normal_style,
            )
            story.extend([recommend_text, Spacer(1, 10)])

            footer = Paragraph(
                "본 리포트는 자동으로 생성된 농가 환경 분석 결과입니다.",
                small_style,
            )
            story.append(footer)
            
            # PDF 빌드
            doc.build(story)
            buffer.seek(0)
            
            st.download_button(
                label=":material/download: PDF 다운로드",
                data=buffer.getvalue(),
                file_name=f"농가_리포트_{selected_table}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
            )
        except Exception as e:
            st.error(f"리포트 생성 중 오류: {e}")
    elif not report_vars:
        st.info("리포트에 포함할 센서를 먼저 선택하세요.")
