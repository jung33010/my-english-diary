import streamlit as st
import openai
from notion_client import Client
from datetime import datetime
import json

# 세션 상태 초기화
if 'ai_result' not in st.session_state:
    st.session_state.ai_result = None

# Secrets에서 정보 가져오기
try:
    openai.api_key = st.secrets["openai_key"]
    notion = Client(auth=st.secrets["notion_token"])
    DATABASE_ID = st.secrets["notion_db_id"]
except:
    st.warning("Streamlit Secrets 설정을 확인해주세요.")

st.title("📝 나만의 영어 학습 일기장")

# 입력창
user_input = st.text_area("한글 일기를 쓰고, 아래에 연습하고 싶은 영어 문장을 적어주세요.", 
                          height=200, 
                          placeholder="오늘은 운동을 했다. (연습) I did exercise today.")

if st.button("🔍 AI 교정 받기"):
    with st.spinner("AI가 분석 중..."):
        prompt = f"다음 글에서 영어 문장을 찾아 문법을 고치고 원어민 표현 3개를 추천해줘. JSON 형식으로 답해줘. 구조: {{'original': '...', 'corrected': '...', 'suggestions': ['...', '...', '...']}} \n\n내용: {user_input}"
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        st.session_state.ai_result = json.loads(response.choices[0].message.content)

# 결과 표시 및 노션 업로드
if st.session_state.ai_result:
    res = st.session_state.ai_result
    st.success(f"**✅ 교정:** {res['corrected']}")
    st.info("**💡 원어민 표현:** \n" + "\n".join([f"- {s}" for s in res['suggestions']]))
    
    if st.button("📓 노션에 저장하기"):
        date_str = datetime.now().strftime("%Y-%m-%d")
        notion.pages.create(
            parent={"database_id": DATABASE_ID},
            properties={
                "Name": {"title": [{"text": {"content": f"{date_str} 일기"}}]},
                "Date": {"date": {"start": date_str}},
                "Korean Diary": {"rich_text": [{"text": {"content": user_input}}]},
                "English Corrected": {"rich_text": [{"text": {"content": res['corrected']}}]},
                "Native Suggestions": {"rich_text": [{"text": {"content": ", ".join(res['suggestions'])}}]}
            }
        )
        st.balloons()
        st.success("노션 저장 완료!")
