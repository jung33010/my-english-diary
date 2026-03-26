import streamlit as st
import openai
from notion_client import Client
from datetime import datetime
import json
import base64
import io

# ─── 페이지 설정 ────────────────────────────────────────────────
st.set_page_config(
    page_title="나만의 영어 학습 일기장",
    page_icon="📖",
    layout="centered",
)

# ─── 커스텀 CSS ─────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;600&family=Lora:ital,wght@0,400;0,600;1,400&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans KR', sans-serif;
}
h1, h2, h3 { font-family: 'Lora', serif; }

.stTextArea textarea {
    border-radius: 12px;
    border: 1.5px solid #e0d6c8;
    background: #fdfaf6;
    font-size: 15px;
    line-height: 1.7;
}
.compare-box {
    display: flex;
    gap: 16px;
    margin: 12px 0;
}
.compare-left, .compare-right {
    flex: 1;
    padding: 16px 20px;
    border-radius: 12px;
    font-size: 14px;
    line-height: 1.8;
}
.compare-left {
    background: #fff3f3;
    border: 1.5px solid #f5c6c6;
}
.compare-right {
    background: #f0fff4;
    border: 1.5px solid #b2e0bf;
}
.compare-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-bottom: 6px;
    opacity: 0.6;
}
.feedback-card {
    background: #fffdf5;
    border: 1.5px solid #f0e6c0;
    border-radius: 12px;
    padding: 16px 20px;
    margin: 8px 0;
}
.suggestion-chip {
    display: inline-block;
    background: #eef3ff;
    border: 1px solid #c5d3f5;
    border-radius: 20px;
    padding: 4px 14px;
    margin: 4px 4px 4px 0;
    font-size: 13px;
    color: #3355aa;
}
.cost-bar {
    background: #f7f5f2;
    border-top: 1px solid #e8e2d8;
    border-radius: 0 0 12px 12px;
    padding: 10px 20px;
    font-size: 12px;
    color: #888;
    text-align: right;
    margin-top: 32px;
}
.cost-highlight {
    color: #c0783a;
    font-weight: 600;
}
.section-title {
    font-family: 'Lora', serif;
    font-size: 17px;
    font-weight: 600;
    color: #3a3228;
    margin: 20px 0 8px 0;
    padding-bottom: 4px;
    border-bottom: 2px solid #f0e6c0;
}
</style>
""", unsafe_allow_html=True)

# ─── 세션 상태 초기화 ────────────────────────────────────────────
for key in ['ai_result', 'tts_audio', 'total_tokens', 'total_cost_krw', 'last_input']:
    if key not in st.session_state:
        st.session_state[key] = None if key != 'total_tokens' else 0
if 'total_cost_krw' not in st.session_state:
    st.session_state.total_cost_krw = 0.0

# ─── Secrets 로드 ────────────────────────────────────────────────
try:
    client = openai.OpenAI(api_key=st.secrets["openai_key"])
    notion = Client(auth=st.secrets["notion_token"])
    DATABASE_ID = st.secrets["notion_db_id"]
    secrets_ok = True
except Exception as e:
    st.warning(f"⚠️ Streamlit Secrets 설정을 확인해주세요: {e}")
    secrets_ok = False

# ─── 비용 계산 함수 ──────────────────────────────────────────────
# gpt-4o-mini 기준: input $0.150/1M, output $0.600/1M tokens
# tts-1-hd: $0.030/1K chars   USD→KRW 약 1380
USD_TO_KRW = 1380
GPT_INPUT_PRICE  = 0.150 / 1_000_000
GPT_OUTPUT_PRICE = 0.600 / 1_000_000
TTS_PRICE_PER_CHAR = 0.030 / 1000

def calc_cost_krw(input_tokens=0, output_tokens=0, tts_chars=0):
    usd = (input_tokens * GPT_INPUT_PRICE
           + output_tokens * GPT_OUTPUT_PRICE
           + tts_chars * TTS_PRICE_PER_CHAR)
    return usd * USD_TO_KRW

# ─── UI ─────────────────────────────────────────────────────────
st.title("📖 나만의 영어 학습 일기장")
st.caption("한글 일기 + 영어 연습 → AI 교정 · 피드백 · TTS · 노션 저장")

st.markdown('<div class="section-title">✍️ 오늘의 일기</div>', unsafe_allow_html=True)
user_input = st.text_area(
    label="일기를 쓰고, 연습하고 싶은 영어 문장을 함께 적어주세요.",
    height=220,
    placeholder="예) 오늘은 친구랑 카페에서 공부했다.\n(연습) I study at the cafe with my friend today.",
    label_visibility="collapsed"
)

col1, col2 = st.columns([3, 1])
with col1:
    analyze_btn = st.button("🔍 AI 교정 받기", use_container_width=True, type="primary")
with col2:
    clear_btn = st.button("🗑️ 초기화", use_container_width=True)

if clear_btn:
    st.session_state.ai_result = None
    st.session_state.tts_audio = None
    st.rerun()

# ─── AI 교정 ─────────────────────────────────────────────────────
if analyze_btn and user_input.strip() and secrets_ok:
    with st.spinner("AI가 문장을 분석하고 있어요..."):
        system_prompt = """당신은 친절하고 꼼꼼한 영어 교사입니다.
사용자가 한글 일기와 함께 영어 연습 문장을 보내면:
1. 영어 문장을 찾아 문법/어색함을 교정합니다.
2. 뭐가 틀렸고 왜 어색했는지 한국어로 구체적으로 설명합니다 (2~4줄).
3. 원어민이 실제로 쓸 법한 자연스러운 표현 3개를 추천합니다.

반드시 아래 JSON 형식으로만 응답하세요 (마크다운 없이 순수 JSON):
{
  "original_english": "사용자가 쓴 영어 문장",
  "corrected": "교정된 영어 문장",
  "feedback": "뭐가 틀렸고 왜 어색했는지 한국어 설명",
  "suggestions": ["표현1", "표현2", "표현3"]
}"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            response_format={"type": "json_object"}
        )
        
        usage = response.usage
        cost = calc_cost_krw(usage.prompt_tokens, usage.completion_tokens)
        st.session_state.total_tokens = (st.session_state.total_tokens or 0) + usage.total_tokens
        st.session_state.total_cost_krw = (st.session_state.total_cost_krw or 0.0) + cost

        try:
            st.session_state.ai_result = json.loads(response.choices[0].message.content)
        except json.JSONDecodeError:
            st.error("AI 응답 파싱 실패. 다시 시도해주세요.")
        
        st.session_state.last_input = user_input
        st.session_state.tts_audio = None  # 이전 TTS 초기화

# ─── 결과 표시 ────────────────────────────────────────────────────
if st.session_state.ai_result:
    res = st.session_state.ai_result

    # 1. 원문 vs 교정 비교
    st.markdown('<div class="section-title">📝 문장 비교</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="compare-box">
        <div class="compare-left">
            <div class="compare-label">내가 쓴 문장</div>
            {res.get('original_english', '—')}
        </div>
        <div class="compare-right">
            <div class="compare-label">✅ 교정된 문장</div>
            {res.get('corrected', '—')}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. 피드백 (왜 틀렸는지)
    st.markdown('<div class="section-title">💬 피드백</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="feedback-card">{res.get("feedback", "")}</div>', unsafe_allow_html=True)

    # 3. 원어민 표현 추천
    st.markdown('<div class="section-title">🌟 원어민 표현 추천</div>', unsafe_allow_html=True)
    chips = "".join([f'<span class="suggestion-chip">💬 {s}</span>' for s in res.get("suggestions", [])])
    st.markdown(chips, unsafe_allow_html=True)

    st.markdown("---")

    # ─── TTS ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">🔊 TTS 듣기</div>', unsafe_allow_html=True)
    
    tts_text_options = {
        "교정된 문장": res.get("corrected", ""),
        "원어민 표현 1": res.get("suggestions", [""])[0],
        "원어민 표현 2": res.get("suggestions", ["", ""])[1] if len(res.get("suggestions", [])) > 1 else "",
        "원어민 표현 3": res.get("suggestions", ["", "", ""])[2] if len(res.get("suggestions", [])) > 2 else "",
    }
    tts_choice = st.selectbox("읽어줄 문장 선택", list(tts_text_options.keys()))
    tts_voice = st.select_slider("목소리", options=["alloy", "echo", "fable", "nova", "onyx", "shimmer"], value="nova")

    if st.button("▶️ 듣기", use_container_width=False) and secrets_ok:
        text_to_speak = tts_text_options[tts_choice]
        if text_to_speak:
            with st.spinner("음성 생성 중..."):
                tts_response = client.audio.speech.create(
                    model="tts-1-hd",
                    voice=tts_voice,
                    input=text_to_speak,
                )
                audio_bytes = tts_response.content
                st.session_state.tts_audio = audio_bytes
                
                # TTS 비용 추가
                tts_cost = calc_cost_krw(tts_chars=len(text_to_speak))
                st.session_state.total_cost_krw = (st.session_state.total_cost_krw or 0.0) + tts_cost

    if st.session_state.tts_audio:
        st.audio(st.session_state.tts_audio, format="audio/mp3")

    # ─── 녹음 / 재생 (저장 없이 브라우저 메모리) ──────────────────
    st.markdown('<div class="section-title">🎙️ 내 발음 녹음 & 재생</div>', unsafe_allow_html=True)
    st.caption("녹음은 이 페이지를 벗어나면 사라집니다. 저장 공간을 사용하지 않아요.")

    st.components.v1.html("""
    <style>
      .rec-wrap { display:flex; gap:10px; align-items:center; margin-top:4px; }
      .rec-btn {
        padding: 8px 20px; border-radius: 20px; border: 1.5px solid #d0c8bc;
        background: #fdfaf6; cursor: pointer; font-size:14px;
        font-family: 'Noto Sans KR', sans-serif; transition: all 0.2s;
      }
      .rec-btn:hover { background: #f0ebe3; }
      .rec-btn.recording { background: #ffe0e0; border-color: #e88; color: #c00; }
      #rec-status { font-size:12px; color:#999; margin-top:6px; }
    </style>
    <div class="rec-wrap">
      <button class="rec-btn" id="btnRec" onclick="toggleRecord()">⏺ 녹음 시작</button>
      <button class="rec-btn" id="btnPlay" onclick="playBack()" disabled>▶ 재생</button>
    </div>
    <div id="rec-status">마이크 권한이 필요합니다.</div>
    <audio id="playback" style="display:none"></audio>

    <script>
    let mediaRecorder, audioChunks = [], audioBlob = null;
    let isRecording = false;

    async function toggleRecord() {
      const btnRec = document.getElementById('btnRec');
      const status = document.getElementById('rec-status');

      if (!isRecording) {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          audioChunks = [];
          mediaRecorder = new MediaRecorder(stream);
          mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
          mediaRecorder.onstop = () => {
            audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const url = URL.createObjectURL(audioBlob);
            const audio = document.getElementById('playback');
            audio.src = url;
            document.getElementById('btnPlay').disabled = false;
            status.textContent = '✅ 녹음 완료! 재생 버튼을 눌러보세요.';
            stream.getTracks().forEach(t => t.stop());
          };
          mediaRecorder.start();
          isRecording = true;
          btnRec.textContent = '⏹ 녹음 중지';
          btnRec.classList.add('recording');
          status.textContent = '🔴 녹음 중...';
        } catch(err) {
          status.textContent = '❌ 마이크 접근 실패: ' + err.message;
        }
      } else {
        mediaRecorder.stop();
        isRecording = false;
        btnRec.textContent = '⏺ 다시 녹음';
        btnRec.classList.remove('recording');
      }
    }

    function playBack() {
      const audio = document.getElementById('playback');
      audio.play();
    }
    </script>
    """, height=120)

    # ─── 노션 저장 ────────────────────────────────────────────────
    st.markdown('<div class="section-title">📓 노션에 저장하기</div>', unsafe_allow_html=True)
    
    if st.button("📤 노션 페이지로 저장", use_container_width=True) and secrets_ok:
        date_str = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H:%M")
        diary_text = st.session_state.last_input or user_input
        suggestions = res.get("suggestions", [])

        try:
            notion.pages.create(
                parent={"database_id": DATABASE_ID},
                properties={
                    "Name": {"title": [{"text": {"content": f"📖 {date_str} 영어 학습 일기"}}]},
                    "Date": {"date": {"start": date_str}},
                },
                children=[
                    # 날짜 헤더
                    {
                        "object": "block", "type": "heading_2",
                        "heading_2": {"rich_text": [{"type": "text", "text": {"content": f"📖 {date_str} {time_str} 일기"}}]}
                    },
                    # 구분선
                    {"object": "block", "type": "divider", "divider": {}},

                    # 원문 섹션
                    {
                        "object": "block", "type": "heading_3",
                        "heading_3": {"rich_text": [{"type": "text", "text": {"content": "✍️ 오늘의 일기 (원문)"}}]}
                    },
                    {
                        "object": "block", "type": "paragraph",
                        "paragraph": {"rich_text": [{"type": "text", "text": {"content": diary_text}}]}
                    },

                    # 문장 비교 섹션
                    {
                        "object": "block", "type": "heading_3",
                        "heading_3": {"rich_text": [{"type": "text", "text": {"content": "📝 문장 비교"}}]}
                    },
                    {
                        "object": "block", "type": "callout",
                        "callout": {
                            "rich_text": [{"type": "text", "text": {"content": f"❌ 내가 쓴 문장\n{res.get('original_english', '—')}"}}],
                            "icon": {"emoji": "📌"},
                            "color": "red_background"
                        }
                    },
                    {
                        "object": "block", "type": "callout",
                        "callout": {
                            "rich_text": [{"type": "text", "text": {"content": f"✅ 교정된 문장\n{res.get('corrected', '—')}"}}],
                            "icon": {"emoji": "✅"},
                            "color": "green_background"
                        }
                    },

                    # 피드백
                    {
                        "object": "block", "type": "heading_3",
                        "heading_3": {"rich_text": [{"type": "text", "text": {"content": "💬 AI 피드백"}}]}
                    },
                    {
                        "object": "block", "type": "quote",
                        "quote": {"rich_text": [{"type": "text", "text": {"content": res.get("feedback", "")}}]}
                    },

                    # 원어민 표현
                    {
                        "object": "block", "type": "heading_3",
                        "heading_3": {"rich_text": [{"type": "text", "text": {"content": "🌟 원어민 표현 추천"}}]}
                    },
                    *[
                        {
                            "object": "block", "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": [{"type": "text", "text": {"content": s},
                                              "annotations": {"bold": False, "code": False}}]
                            }
                        }
                        for s in suggestions
                    ],

                    # 구분선 + 메타
                    {"object": "block", "type": "divider", "divider": {}},
                    {
                        "object": "block", "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {
                                "content": f"🤖 gpt-4o-mini · tts-1-hd  |  총 토큰: {st.session_state.total_tokens or 0:,}  |  누적 비용: ₩{st.session_state.total_cost_krw:.1f}"
                            }, "annotations": {"color": "gray"}}]
                        }
                    }
                ]
            )
            st.balloons()
            st.success("✅ 노션에 깔끔한 페이지로 저장됐어요!")
        except Exception as e:
            st.error(f"노션 저장 실패: {e}")

# ─── 하단 비용 표시 ───────────────────────────────────────────────
st.markdown("---")
total_tokens = st.session_state.total_tokens or 0
total_cost   = st.session_state.total_cost_krw or 0.0
st.markdown(
    f'<div class="cost-bar">'
    f'이 세션에서 사용한 토큰: <span class="cost-highlight">{total_tokens:,} tokens</span> &nbsp;|&nbsp; '
    f'누적 예상 비용: <span class="cost-highlight">₩{total_cost:.2f}</span>'
    f'<br><span style="font-size:10px; opacity:0.6;">gpt-4o-mini 기준 · USD→KRW 1,380 적용 · TTS tts-1-hd 포함</span>'
    f'</div>',
    unsafe_allow_html=True
)
