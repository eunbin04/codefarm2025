# mcdata_detail.py
import streamlit as st
import seaborn as sns
import matplotlib.pyplot as plt


def show_detailed_view(data, selected_vars):


    for var in selected_vars:
        st.subheader(f"{var} 상세 정보")

        st.write("기본 통계")
        desc = data[var].describe()
        st.write(desc)

        st.write("시간에 따른 값 변화")
        st.line_chart(data[var])

        st.write("분포도")
        fig, ax = plt.subplots()
        sns.histplot(data[var].dropna(), bins=30, ax=ax)
        st.pyplot(fig)

        st.write("이상치 확인")
        # 간단히 박스플롯으로 이상치 시각화
        fig2, ax2 = plt.subplots()
        sns.boxplot(x=data[var], ax=ax2)
        st.pyplot(fig2)

        st.markdown("---")
