import streamlit as st
import json
from datetime import datetime

# ── 페이지 설정 (반드시 최상단) ────────────────────────────────────
st.set_page_config(
    page_title="영어 학습 일기장",
    page_icon="🌙",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── 세션 상태 초기화 ───────────────────────────────────────────────
for k, v in {
    "ai_result": None,
    "last_input": "",
    "session_tokens": 0,
    "session_cost_krw": 0.0,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Secrets & 클라이언트 ──────────────────────────────────────────
secrets_ok = False
try:
    from openai import OpenAI
    from notion_client import Client

    oai = OpenAI(api_key=st.secrets["openai_key"])
    notion = Client(auth=st.secrets["notion_token"])
    DATABASE_ID = st.secrets["notion_db_id"]
    secrets_ok = True
except ImportError as e:
    st.error(f"패키지 설치 필요: `pip install openai>=1.0 notion-client`\n\n{e}")
except Exception as e:
    st.error(f"Secrets 오류: {e}")

# ── 비용 상수 (gpt-4o-mini · USD→KRW 1,380) ──────────────────────
_KRW = 1_380
_IN  = 0.150 / 1_000_000
_OUT = 0.600 / 1_000_000

def add_cost(input_tok=0, output_tok=0):
    usd = input_tok * _IN + output_tok * _OUT
    st.session_state.session_cost_krw += usd * _KRW
    st.session_state.session_tokens   += input_tok + output_tok

# ═══════════════════════════════════════════════════════════════════
#  GLOBAL CSS  ── 딥 네이비 × 크림 × 앰버 골드 테마
# ═══════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Noto+Sans+KR:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --navy:   #0d1b2a;
    --navy2:  #1a2d42;
    --navy3:  #243d57;
    --cream:  #f5efe6;
    --cream2: #ede4d7;
    --gold:   #c9963a;
    --gold2:  #e8b455;
    --mint:   #4cc9a0;
    --rose:   #e07070;
    --text:   #e8ddd0;
    --muted:  #8fa3b8;
    --radius: 14px;
}

html, body,
[data-testid="stAppViewContainer"],
[data-testid="stApp"],
.main, section.main, .block-container {
    background: var(--navy) !important;
    color: var(--text) !important;
}
[data-testid="stHeader"]  { background: transparent !important; }
[data-testid="stSidebar"] { background: var(--navy2) !important; }

h1,h2,h3,h4 {
    font-family: 'DM Serif Display', serif !important;
    color: var(--cream) !important;
}
p, div, span, label, li, td, th {
    font-family: 'Noto Sans KR', sans-serif !important;
}

.app-title {
    font-family: 'DM Serif Display', serif;
    font-size: 2.5rem;
    color: var(--cream);
    letter-spacing: -0.02em;
    line-height: 1.15;
    padding: 6px 0 2px 0;
}
.app-sub {
    font-size: 13px;
    color: var(--muted);
    font-weight: 300;
    letter-spacing: 0.04em;
    margin-bottom: 28px;
}
.gold-line {
    width: 48px; height: 3px;
    background: linear-gradient(90deg, var(--gold), var(--gold2));
    border-radius: 2px;
    margin: 8px 0 16px 0;
}
.sec-label {
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--gold);
    margin: 20px 0 8px 0;
}
.cmp-wrap { display:flex; gap:12px; margin:4px 0; }
.cmp-box {
    flex:1; padding:14px 16px; border-radius:10px;
    font-size:14px; line-height:1.85;
}
.cmp-original {
    background: rgba(224,112,112,0.10);
    border: 1px solid rgba(224,112,112,0.28);
    color: #f0b8b8;
}
.cmp-corrected {
    background: rgba(76,201,160,0.10);
    border: 1px solid rgba(76,201,160,0.28);
    color: #9eecd4;
}
.cmp-tag {
    font-size:10px; font-weight:700; letter-spacing:0.08em;
    text-transform:uppercase; opacity:0.6; margin-bottom:6px;
}
.feedback-box {
    background: rgba(201,150,58,0.07);
    border-left: 3px solid var(--gold);
    border-radius: 0 10px 10px 0;
    padding: 14px 18px;
    font-size: 14px;
    line-height: 1.9;
    color: var(--cream2);
}
.chip-wrap { display:flex; flex-wrap:wrap; gap:8px; margin-top:4px; }
.chip {
    background: rgba(201,150,58,0.13);
    border: 1px solid rgba(201,150,58,0.32);
    border-radius: 20px;
    padding: 6px 16px;
    font-size: 13px;
    color: var(--gold2);
}

/* ElevenLabs 배너 */
.el-banner {
    display: flex;
    align-items: center;
    gap: 14px;
    background: linear-gradient(135deg, rgba(201,150,58,0.10), rgba(76,201,160,0.07));
    border: 1px solid rgba(201,150,58,0.25);
    border-radius: 12px;
    padding: 14px 18px;
    margin: 4px 0;
    text-decoration: none;
    transition: border-color 0.2s, background 0.2s;
}
.el-banner:hover {
    border-color: rgba(201,150,58,0.55);
    background: linear-gradient(135deg, rgba(201,150,58,0.16), rgba(76,201,160,0.10));
}
.el-icon { font-size: 26px; flex-shrink: 0; }
.el-text-title {
    font-size: 14px; font-weight: 600;
    color: var(--cream); margin-bottom: 2px;
}
.el-text-sub {
    font-size: 12px; color: var(--muted); line-height: 1.5;
}
.el-arrow {
    margin-left: auto; font-size: 18px;
    color: var(--gold); flex-shrink: 0;
}

textarea, .stTextArea textarea {
    background: var(--navy2) !important;
    color: var(--cream) !important;
    border: 1px solid var(--navy3) !important;
    border-radius: 10px !important;
    font-size: 14px !important;
    line-height: 1.85 !important;
    caret-color: var(--gold) !important;
}
textarea:focus, .stTextArea textarea:focus {
    border-color: var(--gold) !important;
    box-shadow: 0 0 0 3px rgba(201,150,58,0.15) !important;
    outline: none !important;
}
.stButton > button {
    background: linear-gradient(135deg, var(--gold), var(--gold2)) !important;
    color: var(--navy) !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 10px 22px !important;
    transition: opacity 0.2s, transform 0.15s !important;
    letter-spacing: 0.02em !important;
}
.stButton > button:hover {
    opacity: 0.88 !important;
    transform: translateY(-1px) !important;
}
.stButton > button:active { transform: translateY(0) !important; }
[data-testid="stSelectbox"] > div > div {
    background: var(--navy2) !important;
    color: var(--cream) !important;
    border: 1px solid var(--navy3) !important;
    border-radius: 8px !important;
}
div[data-baseweb="popover"] { background: var(--navy2) !important; }
div[data-baseweb="menu"] {
    background: var(--navy2) !important;
    border: 1px solid var(--navy3) !important;
}
audio { width: 100%; border-radius: 8px; accent-color: var(--gold); }
hr { border-color: var(--navy3) !important; margin: 20px 0 !important; }
[data-testid="stAlert"] {
    background: var(--navy2) !important;
    border: 1px solid var(--navy3) !important;
    color: var(--text) !important;
    border-radius: var(--radius) !important;
}
.cost-bar {
    background: var(--navy2);
    border: 1px solid var(--navy3);
    border-radius: var(--radius);
    padding: 12px 20px;
    margin-top: 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    color: var(--muted);
}
.cost-val {
    font-family: 'JetBrains Mono', monospace;
    color: var(--gold2);
    font-size: 13px;
}
.cost-note { font-size: 10px; color: var(--navy3); margin-top: 3px; }
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: var(--navy); }
::-webkit-scrollbar-thumb { background: var(--navy3); border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
#  HEADER
# ═══════════════════════════════════════════════════════════════════
st.markdown("""
<div class="app-title">🌙 영어 학습 일기장</div>
<div class="gold-line"></div>
<div class="app-sub">오늘의 일기를 쓰고 &nbsp;·&nbsp; AI 교정을 받고 &nbsp;·&nbsp; 원어민처럼 말해보세요</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
#  입력 영역
# ═══════════════════════════════════════════════════════════════════
st.markdown('<div class="sec-label">✍️ 오늘의 일기</div>', unsafe_allow_html=True)
user_input = st.text_area(
    label="diary",
    label_visibility="collapsed",
    height=210,
    placeholder=(
        "한글 일기와 함께 연습하고 싶은 영어 문장을 써주세요.\n\n"
        "예) 오늘은 친구랑 카페에서 공부를 했다.\n"
        "(연습) I study at the cafe with my friend today."
    ),
)

c1, c2 = st.columns([5, 1])
with c1:
    analyze_btn = st.button("🔍  AI 교정 받기", use_container_width=True, type="primary")
with c2:
    if st.button("↺ 초기화", use_container_width=True):
        st.session_state.ai_result = None
        st.rerun()

# ═══════════════════════════════════════════════════════════════════
#  AI 교정 요청
# ═══════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """당신은 친절하고 꼼꼼한 원어민 영어 교사입니다.
사용자 글에서 영어 문장을 찾아 다음을 분석하세요:
1. original_english: 사용자가 쓴 영어 문장 (원문 그대로)
2. corrected: 문법·자연스러움을 교정한 문장
3. feedback: 뭐가 틀렸고 왜 어색했는지 한국어로 2~4줄 구체적 설명
4. suggestions: 원어민이 실제 쓰는 자연스러운 표현 3가지 (영어 문장으로)

반드시 순수 JSON만 반환하세요 (마크다운 코드블록 없이):
{"original_english":"...","corrected":"...","feedback":"...","suggestions":["...","...","..."]}"""

if analyze_btn and user_input.strip():
    if not secrets_ok:
        st.error("Secrets 설정을 먼저 확인해주세요.")
    else:
        with st.spinner("AI가 문장을 분석하고 있어요..."):
            try:
                resp = oai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": user_input},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=800,
                )
                add_cost(
                    input_tok=resp.usage.prompt_tokens,
                    output_tok=resp.usage.completion_tokens,
                )
                result = json.loads(resp.choices[0].message.content)
                st.session_state.ai_result = result
                st.session_state.last_input = user_input
            except Exception as e:
                st.error(f"API 오류: {e}")

# ═══════════════════════════════════════════════════════════════════
#  결과 표시
# ═══════════════════════════════════════════════════════════════════
if st.session_state.ai_result:
    res   = st.session_state.ai_result
    orig  = res.get("original_english", "—")
    corr  = res.get("corrected", "—")
    fb    = res.get("feedback", "")
    suggs = res.get("suggestions", [])

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── 1. 문장 비교 ─────────────────────────────────────────────
    st.markdown('<div class="sec-label">📝 문장 비교</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="cmp-wrap">
        <div class="cmp-box cmp-original">
            <div class="cmp-tag">❌ 내가 쓴 문장</div>
            {orig}
        </div>
        <div class="cmp-box cmp-corrected">
            <div class="cmp-tag">✅ 교정된 문장</div>
            {corr}
        </div>
    </div>""", unsafe_allow_html=True)

    # ── 2. 피드백 ────────────────────────────────────────────────
    st.markdown('<div class="sec-label">💬 AI 피드백</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="feedback-box">{fb}</div>', unsafe_allow_html=True)

    # ── 3. 원어민 표현 ───────────────────────────────────────────
    st.markdown('<div class="sec-label">🌟 원어민 표현 추천</div>', unsafe_allow_html=True)
    chips = "".join(f'<div class="chip">💬 {s}</div>' for s in suggs)
    st.markdown(f'<div class="chip-wrap">{chips}</div>', unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── 4. TTS — ElevenLabs 링크 ─────────────────────────────────
    st.markdown('<div class="sec-label">🔊 TTS 듣기</div>', unsafe_allow_html=True)
    st.markdown("""
    <a class="el-banner" href="https://elevenlabs.io" target="_blank">
        <div class="el-icon">🎙️</div>
        <div>
            <div class="el-text-title">ElevenLabs — AI 음성 생성</div>
            <div class="el-text-sub">교정된 문장을 복사해서 원어민 발음으로 들어보세요.<br>무료 플랜으로도 충분히 사용 가능해요.</div>
        </div>
        <div class="el-arrow">→</div>
    </a>
    """, unsafe_allow_html=True)

    # ── 5. 녹음 & 재생 ───────────────────────────────────────────
    st.markdown('<div class="sec-label">🎙️ 내 발음 녹음 & 재생</div>', unsafe_allow_html=True)
    st.caption("💡 녹음은 서버에 저장되지 않습니다. 페이지를 벗어나면 사라져요.")

    st.components.v1.html("""
    <style>
    * { box-sizing:border-box; margin:0; padding:0; }
    body { background:transparent; font-family:'Noto Sans KR',sans-serif; }
    .rec-row { display:flex; gap:10px; align-items:center; padding:4px 0; }
    .rbtn {
        display:flex; align-items:center; gap:7px;
        padding:9px 20px; border-radius:8px;
        border:1px solid #243d57; background:#1a2d42;
        color:#e8ddd0; cursor:pointer; font-size:13px;
        font-family:'Noto Sans KR',sans-serif;
        transition:all 0.18s; white-space:nowrap;
    }
    .rbtn:hover  { background:#243d57; border-color:#c9963a; }
    .rbtn:disabled { opacity:0.35; cursor:not-allowed; }
    .rbtn.active {
        background:rgba(224,112,112,0.18);
        border-color:#e07070; color:#f0b8b8;
    }
    .dot {
        width:8px; height:8px; border-radius:50%;
        background:#e07070; animation:pulse 1s infinite; display:none;
    }
    .rbtn.active .dot { display:block; }
    @keyframes pulse {
        0%,100%{opacity:1;transform:scale(1)}
        50%{opacity:0.35;transform:scale(1.4)}
    }
    #status { margin-top:8px; font-size:12px; color:#8fa3b8; min-height:18px; }
    audio { width:100%; margin-top:10px; border-radius:8px; accent-color:#c9963a; }
    </style>

    <div class="rec-row">
        <button class="rbtn" id="btnRec" onclick="toggleRecord()">
            <span class="dot"></span>
            <span id="recLabel">⏺ 녹음 시작</span>
        </button>
        <button class="rbtn" id="btnPlay" onclick="playBack()" disabled>▶ 재생</button>
        <button class="rbtn" id="btnDL"   onclick="downloadRec()" disabled>↓ 다운로드</button>
    </div>
    <div id="status">마이크 권한을 허용하면 바로 녹음할 수 있어요.</div>
    <audio id="player" controls style="display:none"></audio>

    <script>
    let mr, chunks=[], blob=null, recOn=false;
    async function toggleRecord(){
        const btn=document.getElementById('btnRec');
        const lbl=document.getElementById('recLabel');
        const sts=document.getElementById('status');
        if(!recOn){
            try{
                const stream=await navigator.mediaDevices.getUserMedia({audio:true});
                chunks=[];
                mr=new MediaRecorder(stream);
                mr.ondataavailable=e=>chunks.push(e.data);
                mr.onstop=()=>{
                    blob=new Blob(chunks,{type:'audio/webm'});
                    const url=URL.createObjectURL(blob);
                    const p=document.getElementById('player');
                    p.src=url; p.style.display='block';
                    document.getElementById('btnPlay').disabled=false;
                    document.getElementById('btnDL').disabled=false;
                    sts.textContent='✅ 녹음 완료! 재생해보세요.';
                    stream.getTracks().forEach(t=>t.stop());
                    btn.classList.remove('active'); lbl.textContent='⏺ 다시 녹음';
                };
                mr.start(); recOn=true;
                btn.classList.add('active'); lbl.textContent='⏹ 중지';
                sts.textContent='🔴 녹음 중...';
            } catch(e){ sts.textContent='❌ 마이크 오류: '+e.message; }
        } else { mr.stop(); recOn=false; }
    }
    function playBack(){ document.getElementById('player').play(); }
    function downloadRec(){
        if(!blob) return;
        const a=document.createElement('a');
        a.href=URL.createObjectURL(blob);
        a.download='my_pronunciation_'+Date.now()+'.webm';
        a.click();
    }
    </script>
    """, height=175)

    # ── 6. 노션 저장 ─────────────────────────────────────────────
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="sec-label">📓 노션 저장</div>', unsafe_allow_html=True)

    if st.button("📤  노션 페이지로 저장", use_container_width=True):
        if not secrets_ok:
            st.error("Secrets 설정을 확인해주세요.")
        else:
            date_str   = datetime.now().strftime("%Y-%m-%d")
            time_str   = datetime.now().strftime("%H:%M")
            diary_text = st.session_state.last_input or user_input

            try:
                notion.pages.create(
                    parent={"database_id": DATABASE_ID},
                    properties={
                        "Name": {"title": [{"text": {"content": f"📖 {date_str} 영어 학습 일기"}}]},
                        "Date": {"date": {"start": date_str}},
                    },
                    children=[
                        {"object":"block","type":"heading_2","heading_2":{
                            "rich_text":[{"type":"text","text":{
                                "content":f"📖 {date_str}  {time_str}  —  영어 학습 일기"}}]}},
                        {"object":"block","type":"divider","divider":{}},
                        {"object":"block","type":"heading_3","heading_3":{
                            "rich_text":[{"type":"text","text":{"content":"✍️ 오늘의 일기"}}]}},
                        {"object":"block","type":"paragraph","paragraph":{
                            "rich_text":[{"type":"text","text":{"content": diary_text}}]}},
                        {"object":"block","type":"divider","divider":{}},
                        {"object":"block","type":"heading_3","heading_3":{
                            "rich_text":[{"type":"text","text":{"content":"📝 문장 비교"}}]}},
                        {"object":"block","type":"callout","callout":{
                            "rich_text":[{"type":"text","text":{"content":f"내가 쓴 문장\n{orig}"}}],
                            "icon":{"emoji":"❌"},"color":"red_background"}},
                        {"object":"block","type":"callout","callout":{
                            "rich_text":[{"type":"text","text":{"content":f"교정된 문장\n{corr}"},
                                          "annotations":{"bold":True}}],
                            "icon":{"emoji":"✅"},"color":"green_background"}},
                        {"object":"block","type":"heading_3","heading_3":{
                            "rich_text":[{"type":"text","text":{"content":"💬 AI 피드백"}}]}},
                        {"object":"block","type":"quote","quote":{
                            "rich_text":[{"type":"text","text":{"content": fb}}]}},
                        {"object":"block","type":"heading_3","heading_3":{
                            "rich_text":[{"type":"text","text":{"content":"🌟 원어민 표현 추천"}}]}},
                        *[{"object":"block","type":"bulleted_list_item","bulleted_list_item":{
                              "rich_text":[{"type":"text","text":{"content": s}}]}}
                          for s in suggs],
                        {"object":"block","type":"divider","divider":{}},
                        {"object":"block","type":"paragraph","paragraph":{
                            "rich_text":[{"type":"text","text":{
                                "content":(
                                    f"🤖 gpt-4o-mini  │  "
                                    f"토큰: {st.session_state.session_tokens:,}  │  "
                                    f"비용: ₩{st.session_state.session_cost_krw:.2f}"
                                )},
                                "annotations":{"color":"gray","italic":True}}]}},
                    ]
                )
                st.balloons()
                st.success("✅ 노션에 깔끔한 페이지로 저장됐어요!")
            except Exception as e:
                st.error(f"노션 저장 실패: {e}")

# ═══════════════════════════════════════════════════════════════════
#  하단 비용 바
# ═══════════════════════════════════════════════════════════════════
tok  = st.session_state.session_tokens
cost = st.session_state.session_cost_krw
st.markdown(f"""
<div class="cost-bar">
    <div style="color:var(--muted);">이번 세션</div>
    <div style="text-align:right;">
        <div class="cost-val">{tok:,} tokens &nbsp;·&nbsp; ₩{cost:.2f}</div>
        <div class="cost-note">gpt-4o-mini · USD→KRW 1,380 기준</div>
    </div>
</div>
""", unsafe_allow_html=True)
