# perdata_report.py
import streamlit as st
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
import os
import numpy as np


# ==== 나눔고딕 폰트 등록 ====
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "NanumGothic.ttf")
pdfmetrics.registerFont(TTFont("NanumGothic", FONT_PATH))

BOLD_FONT_PATH = os.path.join(BASE_DIR, "fonts", "NanumGothicBold.ttf")
pdfmetrics.registerFont(TTFont("NanumGothic-Bold", BOLD_FONT_PATH))


def get_health_status(series, sensor_name):
    """센서 건강도 평가 (정상/주의/경고)"""
    if series.empty:
        return "데이터 없음", "#999999"
    
    mean = series.mean()
    std = series.std()
    
    # 기본 기준값 (온도, 습도 등)
    thresholds = {
        "temperature": {"min": 18, "max": 28, "warn_min": 15, "warn_max": 32},
        "humidity": {"min": 60, "max": 80, "warn_min": 50, "warn_max": 90},
        "light": {"min": 1000, "max": 25000, "warn_min": 500, "warn_max": 30000},
    }
    
    for key, threshold in thresholds.items():
        if key in sensor_name.lower():
            if threshold["min"] <= mean <= threshold["max"]:
                return "정상", "#28a745"  # 녹색
            elif threshold["warn_min"] <= mean <= threshold["warn_max"]:
                return "주의", "#ffc107"  # 노랑색
            else:
                return "경고", "#dc3545"  # 빨강색
    
    return "정상", "#28a745"


def count_anomalies(series):
    """IQR 기반 이상치 개수 반환"""
    if len(series) < 4:
        return 0
    Q1 = series.quantile(0.25)
    Q3 = series.quantile(0.75)
    IQR = Q3 - Q1
    lower = Q1 - 1.5 * IQR
    upper = Q3 + 1.5 * IQR
    anomalies = ((series < lower) | (series > upper)).sum()
    return int(anomalies)


def generate_farm_report(filtered, selected_table, start_date, end_date, all_columns):
    """
    농가 센서 데이터 자동 PDF 리포트 생성 (확장판)
    """
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
            doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.8*cm, bottomMargin=0.8*cm)
            base_styles = getSampleStyleSheet()

            # 나눔고딕이 적용된 스타일들 정의
            title_style = ParagraphStyle(
                "KoreanTitle",
                parent=base_styles["Title"],
                fontName="NanumGothic-Bold",
                fontSize=20,
                leading=26,
                alignment=1,  # center
                textColor=colors.HexColor("#224B6E"),
            )
            heading_style = ParagraphStyle(
                "KoreanHeading",
                parent=base_styles["Heading2"],
                fontName="NanumGothic-Bold",
                fontSize=13,
                leading=18,
                textColor=colors.HexColor("#1E4363"),
                spaceAfter=6,
            )
            normal_style = ParagraphStyle(
                "KoreanNormal",
                parent=base_styles["Normal"],
                fontName="NanumGothic",
                fontSize=10,
                leading=15,
            )
            small_style = ParagraphStyle(
                "KoreanSmall",
                parent=base_styles["Normal"],
                fontName="NanumGothic",
                fontSize=8.5,
                leading=12,
            )

            story = []
            
            # ============================================
            # 1. 제목 페이지
            # ============================================
            title = Paragraph(
                f"🌱 농가 센서 데이터 리포트<br/>"
                f"<font size=12>{selected_table}</font><br/>"
                f"<font size=10 color='#666'>{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}</font>",
                title_style,
            )
            story.extend([title, Spacer(1, 18)])
            
            # ============================================
            # 2. 센서별 상태 요약 (건강도 표시)
            # ============================================
            story.append(Paragraph("<b>센서 상태 현황</b>", heading_style))
            
            status_data = [["센서명", "상태", "평균값", "범위", "이상치 개수"]]
            for var in report_vars:
                series = filtered[var].dropna()
                if not series.empty:
                    health, color = get_health_status(series, var)
                    anomaly_count = count_anomalies(series) if include_anomaly else 0
                    status_data.append([
                        var,
                        health,
                        f"{series.mean():.2f}",
                        f"{series.min():.2f}~{series.max():.2f}",
                        str(anomaly_count),
                    ])
            
            if len(status_data) > 1:
                status_table = Table(status_data, colWidths=[2.5*cm, 1.8*cm, 1.8*cm, 2*cm, 1.5*cm])
                status_table.setStyle([
                    ("FONTNAME", (0, 0), (-1, -1), "NanumGothic"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E88E5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F0F8FF")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#E8F4F8")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ])
                story.extend([status_table, Spacer(1, 14)])
            
            # ============================================
            # 3. 상세 통계 분석
            # ============================================
            story.append(Paragraph("<b>상세 통계 분석</b>", heading_style))
            
            summary_data = [["센서", "평균", "최대", "최소", "표준편차", "데이터개수"]]
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
                summary_table = Table(summary_data, colWidths=[2.5*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm])
                summary_table.setStyle([
                    ("FONTNAME", (0, 0), (-1, -1), "NanumGothic"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 8.5),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#ECF0F1")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ])
                story.extend([summary_table, Spacer(1, 14)])
            
            # ============================================
            # 4. 일일 추세 분석
            # ============================================
            story.append(Paragraph("<b>일일 변화 추세</b>", heading_style))
            
            trend_data = [["센서", "일 최저", "일 최고", "일평균", "변동폭"]]
            for var in report_vars:
                series = filtered[var].dropna()
                if not series.empty and hasattr(series.index, 'date'):
                    daily_min = series.groupby(series.index.date).min().mean()
                    daily_max = series.groupby(series.index.date).max().mean()
                    daily_mean = series.groupby(series.index.date).mean().mean()
                    variation = daily_max - daily_min
                    trend_data.append([
                        var,
                        f"{daily_min:.2f}",
                        f"{daily_max:.2f}",
                        f"{daily_mean:.2f}",
                        f"{variation:.2f}",
                    ])
            
            if len(trend_data) > 1:
                trend_table = Table(trend_data, colWidths=[2.5*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm])
                trend_table.setStyle([
                    ("FONTNAME", (0, 0), (-1, -1), "NanumGothic"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#27AE60")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#EAFAF1")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ])
                story.extend([trend_table, Spacer(1, 14)])
            
            # ============================================
            # 5. 개선 조언 (센서별 맞춤형)
            # ============================================
            story.append(Paragraph("<b>작물 재배 개선 조언</b>", heading_style))
            
            advice_list = []
            for var in report_vars:
                series = filtered[var].dropna()
                if series.empty:
                    continue
                    
                mean = series.mean()
                health, _ = get_health_status(series, var)
                
                if "temperature" in var.lower():
                    if mean < 18:
                        advice = "🔴 온도가 낮습니다. 보온재 추가 또는 난방 강화를 검토하세요."
                    elif mean > 28:
                        advice = "🔴 온도가 높습니다. 환기 또는 냉방 시설 가동을 검토하세요."
                    else:
                        advice = "✅ 온도 관리가 양호합니다. 현재 수준 유지하세요."
                        
                elif "humidity" in var.lower():
                    if mean < 60:
                        advice = "🟡 습도가 낮습니다. 가습 시설 가동 또는 스프레이 관수를 권장합니다."
                    elif mean > 80:
                        advice = "🔴 습도가 높습니다. 환기 강화 및 병해 예방 조치를 실시하세요."
                    else:
                        advice = "✅ 습도 관리가 양호합니다."
                        
                elif "light" in var.lower():
                    if mean < 1000:
                        advice = "🟡 채광 부족입니다. 인공 조명 추가 또는 위치 변경을 검토하세요."
                    elif mean > 25000:
                        advice = "🟡 광량이 과합니다. 차광막 사용을 권장합니다."
                    else:
                        advice = "✅ 광량 관리가 양호합니다."
                else:
                    advice = "📊 데이터 범위 내에서 안정적으로 관리 중입니다."
                
                advice_list.append(f"• {var}: {advice}")
            
            if advice_list:
                advice_text = Paragraph(
                    "<br/>".join(advice_list),
                    normal_style,
                )
                story.extend([advice_text, Spacer(1, 14)])
            
            # ============================================
            # 6. 주의 알람 (이상치 있을 경우)
            # ============================================
            if include_anomaly:
                anomaly_sensors = []
                for var in report_vars:
                    series = filtered[var].dropna()
                    if not series.empty and count_anomalies(series) > 0:
                        anomaly_sensors.append((var, count_anomalies(series)))
                
                if anomaly_sensors:
                    story.append(Paragraph("<b>주의 알람</b>", heading_style))
                    alarm_text = "다음 센서에서 이상치가 감지되었습니다:<br/>"
                    for sensor, count in anomaly_sensors:
                        alarm_text += f"• {sensor}: {count}개 이상치 발견<br/>"
                    alarm_text += "<br/>센서 재보정 또는 장비 점검을 권장합니다."
                    
                    alarm_para = Paragraph(alarm_text, normal_style)
                    story.extend([alarm_para, Spacer(1, 14)])
        
            
            # ============================================
            # 8. 푸터
            # ============================================
            footer = Paragraph(
                "본 리포트는 자동으로 생성된 분석 결과입니다. 구체적인 운영 조정은 전문가 상담을 권장합니다.",
                small_style,
            )
            story.append(footer)
            
            # PDF 빌드
            doc.build(story)
            buffer.seek(0)
            pdf_bytes = buffer.getvalue()
            
            # 다운로드 버튼
            st.download_button(
                label=":material/download: PDF 다운로드",
                data=pdf_bytes,
                file_name=f"농가_리포트_{selected_table}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
            )
            
            # 미리보기 토글
            with st.expander("리포트 미리보기", expanded=False):
                import base64
                pdf_base64 = base64.b64encode(pdf_bytes).decode()
                pdf_display = f'<iframe src="data:application/pdf;base64,{pdf_base64}" width="100%" height="900" style="border:none;"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            
            st.success("✅ 리포트가 성공적으로 생성되었습니다!")

        except Exception as e:
                st.error(f"리포트 생성 중 오류: {e}")
    elif not report_vars:
        st.info("📋 리포트에 포함할 센서를 먼저 선택하세요.")
