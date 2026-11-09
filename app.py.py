"""전역까지 — Streamlit Community Cloud + Supabase

배포 (이 파일과 requirements.txt, 총 2개):
1. GitHub 저장소에 두 파일 업로드 → Streamlit Community Cloud에서 app.py 배포.
2. Supabase 프로젝트 생성 → SQL Editor에서 아래 SQL 실행.
3. Streamlit 앱 Settings > Secrets에 아래 TOML 입력 (실제 값으로 변경).
   SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
   SUPABASE_SERVICE_ROLE_KEY = "YOUR_SERVER_ONLY_SERVICE_ROLE_KEY"
   ADMIN_PASSWORD = "최소 12자 이상의 무작위 관리자 비밀번호"
   APP_URL = "https://YOUR_APP.streamlit.app"
   QR에는 배포된 APP_URL만 들어갑니다. QR을 휴대폰 기본 카메라로 스캔하세요.
   비밀키는 GitHub에 올리지 마세요. service_role은 서버 전용입니다.
4. 로컬 실행: pip install -r requirements.txt && streamlit run app.py

Supabase SQL (앱의 '설정' 창에서도 복사 가능):
create table if not exists public.military_tips (
 id bigint generated always as identity primary key,
 nickname text not null check (char_length(nickname) between 1 and 12),
 category text not null check (category in ('적응','준비물','건강','소통')),
 content text not null check (char_length(content) between 10 and 140),
 veteran boolean not null default false,
 approved boolean not null default false,
 created_at timestamptz not null default now()
);
alter table public.military_tips enable row level security;
revoke all on public.military_tips from anon, authenticated;
-- 공개 API 권한/정책을 만들지 않습니다. 서버의 service_role만 DB에 접근합니다.

주의: 전역일은 일반 현역병 기준 참고용. 실제 전역명령이 우선합니다.
부대명·위치·작전·장병 실명·연락처를 작성하지 마세요.
'전역자' 표시는 자기신고이며 신원 인증을 의미하지 않습니다.
대규모 공개 운영 시 별도 인증, CAPTCHA, 외부 속도제한을 추가하세요.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import hashlib
import hmac
import html
import io
import logging
import time
from urllib.parse import urlsplit

import qrcode
import streamlit as st
from dateutil.relativedelta import relativedelta
from supabase import create_client

st.set_page_config(page_title="전역까지 | 군생활 첫걸음", page_icon="🪖", layout="centered", initial_sidebar_state="collapsed")
LOG = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
MONTHS = {"육군": 18, "해병대": 18, "해군": 20, "공군": 21}
CATEGORIES = ["적응", "준비물", "건강", "소통"]
BASICS = {
    "적응": "모르면 바로 질문! 지시를 짧게 복창하고, 시간·장소·준비물을 확인하세요.",
    "준비물": "입영통지서의 준비물 목록이 우선입니다. 반입 가능한 물품인지 먼저 확인하세요.",
    "건강": "통증·어지럼·열은 참지 말고 간부나 의무요원에게 즉시 알리세요. 약은 임의로 나누지 마세요.",
    "소통": "실수는 숨기지 말고 사실과 필요한 도움을 짧게 말하세요. 괴롭힘·위협은 혼자 감당하지 마세요.",
}
SQL = '''create table if not exists public.military_tips (
 id bigint generated always as identity primary key,
 nickname text not null check (char_length(nickname) between 1 and 12),
 category text not null check (category in ('적응','준비물','건강','소통')),
 content text not null check (char_length(content) between 10 and 140),
 veteran boolean not null default false,
 approved boolean not null default false,
 created_at timestamptz not null default now()
);
alter table public.military_tips enable row level security;
revoke all on public.military_tips from anon, authenticated;'''


def secret(name):
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def database():
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key) if url and key else None


def discharge_day(start, branch):
    return start + relativedelta(months=MONTHS[branch]) - timedelta(days=1)


def service_stats(start, end, today):
    total = (end - start).days + 1
    served = min(total, max(0, (today - start).days + 1))
    return served, total, served / total


def safe(value):
    return html.escape(str(value), quote=True)


def admin_active():
    password = secret("ADMIN_PASSWORD")
    stamp = hashlib.sha256(password.encode()).hexdigest() if password else ""
    return bool(password and st.session_state.get("admin_stamp") == stamp
                and time.time() < st.session_state.get("admin_until", 0))


@st.dialog("배포 설정 · 도움말")
def setup_dialog():
    st.write("① 두 파일을 GitHub에 업로드 → Streamlit Community Cloud에서 app.py 배포")
    st.write("② Supabase SQL Editor에서 실행 (기존 같은 이름 테이블이 없는 새 프로젝트 권장)")
    st.code(SQL, language="sql")
    st.write("③ Streamlit Settings → Secrets에 아래 값 입력. 키는 절대 GitHub에 올리지 마세요.")
    st.code('SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"\nSUPABASE_SERVICE_ROLE_KEY = "SERVER_ONLY_KEY"\nADMIN_PASSWORD = "12자 이상의 무작위 비밀번호"\nAPP_URL = "https://YOUR_APP.streamlit.app"', language="toml")
    st.caption("무료 플랜 한도·휴면 정책은 서비스 제공사의 현재 정책에 따릅니다. DB 미연결 상태에서는 기본 팁과 계산기만 동작합니다.")
    st.link_button("병무청 복무기간 안내", "https://www.mma.go.kr/contents.do?mc=usr0000041")
    st.caption("육군·해병대 18개월 / 해군 20개월 / 공군 21개월. 2026-11-09 확인. 일반 현역병 참고 계산이며 복무기간 조정·개인별 사유는 자동 반영하지 않습니다.")


@st.dialog("QR로 앱 공유")
def qr_dialog():
    url = secret("APP_URL")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        st.info("배포 후 Secrets의 APP_URL에 공개 HTTPS 주소를 입력하세요.")
        return
    out = io.BytesIO()
    qrcode.make(url).save(out, format="PNG")
    st.image(out.getvalue(), width=220)
    st.link_button("앱 열기", url)
    st.caption("휴대폰 기본 카메라로 스캔하세요. QR은 설치파일이 아닌 이 웹앱으로 연결됩니다.")


@st.dialog("후임에게 한 줄 남기기")
def write_dialog():
    st.caption("관리자 승인 후 공개됩니다. 부대·작전 정보, 실명, 연락처, 비방은 금지합니다.")
    with st.form("new_tip", clear_on_submit=True):
        nickname = st.text_input("닉네임", max_chars=12)
        category = st.selectbox("분야", CATEGORIES)
        content = st.text_area("꿀팁 (10~140자)", max_chars=140, height=100)
        veteran = st.checkbox("전역자입니다 (자기신고)")
        agree = st.checkbox("공개 게시 및 위 작성 유의사항을 확인했습니다")
        sent = st.form_submit_button("승인 요청", use_container_width=True)
    if not sent:
        return
    nickname, content = nickname.strip(), content.strip()
    if not nickname or len(content) < 10 or not agree:
        st.warning("닉네임, 10자 이상 꿀팁, 확인 체크를 입력하세요.")
        return
    if time.time() - st.session_state.get("last_sent", 0) < 60:
        st.warning("1분 뒤 다시 작성해주세요.")
        return
    try:
        db = database()
        if db is None:
            st.warning("아직 DB가 연결되지 않았습니다. 운영자가 설정을 완료해야 합니다.")
            return
        db.table("military_tips").insert({"nickname": nickname, "category": category,
            "content": content, "veteran": veteran, "approved": False}).execute()
        st.session_state.last_sent = time.time()
        st.success("접수 완료! 관리자 승인 후 공개됩니다.")
    except Exception:
        LOG.exception("Tip submission failed")
        st.error("저장하지 못했습니다. 잠시 후 재시도하거나 운영자에게 문의하세요.")


@st.dialog("관리자 · 게시물 검토", width="large")
def admin_dialog():
    password = secret("ADMIN_PASSWORD")
    if len(password) < 12:
        st.warning("Secrets에 12자 이상의 ADMIN_PASSWORD를 먼저 설정하세요.")
        return
    if not admin_active():
        with st.form("admin_login"):
            entered = st.text_input("관리자 비밀번호", type="password")
            login = st.form_submit_button("로그인")
        if login:
            if time.time() < st.session_state.get("login_wait", 0):
                st.error("잠시 뒤 다시 시도하세요.")
            elif hmac.compare_digest(entered.encode(), password.encode()):
                st.session_state.admin_stamp = hashlib.sha256(password.encode()).hexdigest()
                st.session_state.admin_until = time.time() + 900
                st.rerun()
            else:
                st.session_state.login_wait = time.time() + 5
                st.error("비밀번호가 일치하지 않습니다.")
        return
    st.caption("로그인 유지 15분 · 검토 후 승인하세요. 전역자 여부는 인증되지 않습니다.")
    if st.button("로그아웃"):
        st.session_state.pop("admin_stamp", None)
        st.rerun()
    view = st.radio("목록", ["승인 대기", "공개됨"], horizontal=True)
    try:
        db = database()
        if db is None:
            st.info("DB 연결이 필요합니다.")
            return
        rows = db.table("military_tips").select("*").eq("approved", view == "공개됨").order("id", desc=True).limit(30).execute().data
        if not rows:
            st.info("게시물이 없습니다.")
        for row in rows:
            st.text(f"#{row['id']} · {row['category']} · {row['nickname']}")
            st.text(row["content"])
            left, right = st.columns(2)
            if view == "승인 대기" and left.button("승인", key=f"approve_{row['id']}"):
                if admin_active():
                    db.table("military_tips").update({"approved": True}).eq("id", row["id"]).execute()
                    st.rerun()
            if right.button("삭제 확인 열기", key=f"delete_{row['id']}"):
                st.session_state.delete_id = row["id"]
            if st.session_state.get("delete_id") == row["id"]:
                st.warning("삭제하면 복구할 수 없습니다.")
                if st.button("영구 삭제", key=f"confirm_{row['id']}") and admin_active():
                    db.table("military_tips").delete().eq("id", row["id"]).execute()
                    st.session_state.pop("delete_id", None)
                    st.rerun()
    except Exception:
        LOG.exception("Moderation failed")
        st.error("DB 작업 실패. 테이블과 연결 설정을 확인하세요.")


st.markdown('''<style>
.stApp {background:#f4f6f0; color:#182b25;}
.block-container {max-width:480px; padding:0.75rem 0.8rem 0.5rem;}
header[data-testid="stHeader"] {height:0; min-height:0; background:transparent;}
[data-testid="stToolbar"] {display:none;}
[data-testid="stVerticalBlock"] {gap:0.42rem;}
[data-testid="stHorizontalBlock"] {gap:0.4rem;}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {min-width:0!important;}
[data-testid="stHorizontalBlock"] {flex-wrap:nowrap!important;}
label p {font-size:0.78rem!important;}
.stButton button,.stFormSubmitButton button {min-height:2.3rem; border-radius:12px;}
.stButton button p {font-size:0.8rem;}
h1 {font-size:1.45rem!important; padding:0!important;}
.hero {background:#173e32;color:#fff;padding:13px 16px;border-radius:18px;}
.hero .number {font-size:2.35rem;font-weight:800;line-height:1.12;}
.hero .sub {font-size:0.76rem;color:#d1e2d5;}
.card {background:#fff;border:1px solid #e0e7db;border-radius:14px;padding:10px 12px;}
.card .tag {color:#476b4c;font-size:0.71rem;font-weight:700;margin-bottom:3px;}
.card .body {font-size:0.85rem;line-height:1.45;overflow-wrap:anywhere;}
.micro {font-size:0.65rem;color:#647568;line-height:1.4;}
.progress {height:6px;background:#406051;border-radius:10px;margin:8px 0 5px;overflow:hidden;}
.progress span {display:block;height:100%;background:#cbe48d;}
@media(max-width:480px){.block-container{padding-top:0.5rem;} [data-testid="stHorizontalBlock"]{gap:0.3rem;}}
</style>''', unsafe_allow_html=True)

st.markdown("# 🪖 전역까지")
a, b = st.columns([1, 1.5])
branch = a.selectbox("군별", list(MONTHS), label_visibility="collapsed")
today = datetime.now(KST).date()
start = b.date_input("입대일", value=today, min_value=date(2020, 1, 1), max_value=date(2035, 12, 31), format="YYYY-MM-DD", label_visibility="collapsed")
end = discharge_day(start, branch)
served, total, ratio = service_stats(start, end, today)
remaining = max(0, (end - today).days)
if today < start:
    headline, detail = f"입대 D-{(start-today).days}", "새로운 시작을 차근차근 준비해요"
elif today > end:
    headline, detail = "전역 완료 🎉", "다음 출발을 응원합니다"
elif today == end:
    headline, detail = "전역 D-DAY", "오늘까지 정말 수고했어요"
else:
    headline, detail = f"전역 D-{remaining}", f"{served}일차 · 전체 {total}일"
st.markdown(f'''<div class="hero"><div class="sub">{detail}</div><div class="number">{headline}</div>
<div class="progress"><span style="width:{ratio*100:.2f}%"></span></div>
<div class="sub">예상 {end:%Y.%m.%d} · {ratio*100:.1f}% 완료</div></div>''', unsafe_allow_html=True)
st.markdown('<div class="micro">참고용 계산 · 개인별 복무 조정 미반영 · 실제 전역명령 우선</div>', unsafe_allow_html=True)
category = st.selectbox("기초생활 분야", CATEGORIES, label_visibility="collapsed")
st.markdown(f'<div class="card"><div class="tag">🌱 처음이라면 · {category}</div><div class="body">{BASICS[category]}</div></div>', unsafe_allow_html=True)

rows = []
status = ""
try:
    db = database()
    if db is not None:
        rows = db.table("military_tips").select("id,nickname,category,content,veteran").eq("approved", True).eq("category", category).order("id", desc=True).limit(100).execute().data
    else:
        status = "DB 미연결 · 설정에서 연결하세요"
except Exception:
    LOG.exception("Public tips unavailable")
    status = "꿀팁 연결 오류 · 잠시 후 다시 시도하세요"

index_key = f"tip_index_{category}"
index = st.session_state.get(index_key, 0)
if rows:
    row = rows[index % len(rows)]
    tag = "전역자 · 자기신고" if row["veteran"] else "군생활 동료"
    title = f"💬 {safe(row['nickname'])} · {tag} ({index % len(rows)+1}/{len(rows)})"
    body = safe(row["content"])
else:
    title = "💬 후임에게 남기는 한 줄"
    body = "아직 승인된 글이 없어요. 경험에서 배운 안전한 생활 팁을 남겨주세요."
st.markdown(f'<div class="card"><div class="tag">{title}</div><div class="body">{body}</div></div>', unsafe_allow_html=True)
if status:
    st.markdown(f'<div class="micro">{status}</div>', unsafe_allow_html=True)
x, y, z = st.columns([1, 1, 1])
if x.button("✍️ 팁 쓰기", use_container_width=True):
    write_dialog()
if y.button("다른 팁 ↻", use_container_width=True, disabled=len(rows) < 2):
    st.session_state[index_key] = index + 1
    st.rerun()
if z.button("QR 공유", use_container_width=True):
    qr_dialog()
x, y = st.columns(2)
if x.button("⚙️ 설정 · 도움말", use_container_width=True):
    setup_dialog()
if y.button("🔒 관리자", use_container_width=True):
    admin_dialog()
st.markdown('<div class="micro">글은 승인 후 공개 · 개인정보·군사정보 금지<br>긴급상황은 주변 간부·의무요원에게 즉시 도움 요청</div>', unsafe_allow_html=True)
