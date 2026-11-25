from pathlib import Path
import os

from dotenv import load_dotenv
import streamlit as st

from bridge.agent import CompatibleAPI, LearningAgent
from bridge.bank import BY_ID, CONCEPTS, DIAGNOSTIC
from bridge.retrieval import MaterialIndex
from bridge.store import Store


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
STAGES = {
    1: "학생 상태 분석", 2: "필요한 도구 선택", 3: "도구 실행",
    4: "실행 결과 확인", 5: "다음 학습 행동 결정", 6: "최종 학습 결과 제공",
}
ACTIONS = {
    "retry": "힌트를 참고하고 같은 문제를 한 번 더 풀어 보세요.",
    "advance": "맞았어요! 다음 문제를 풀어 볼까요?",
    "diagnostic_done": "진단평가를 마쳤어요. 이제 나에게 맞는 문제를 풀어 봐요.",
    "prerequisite": "이 문제에 필요한 기초 개념부터 연습해요.",
    "review": "같은 개념을 다른 문제로 한 번 더 연습해요.",
}

st.set_page_config(page_title="배움이음 AI", page_icon="🌱", layout="centered")
st.title("🌱 배움이음 AI")
st.caption("초등 4–6학년 분수 학습 코치")


@st.cache_resource
def get_store(path):
    return Store(path)


@st.cache_resource
def get_index(directory, model_path):
    return MaterialIndex(directory, model_path)


store = get_store(os.getenv("BRIDGE_DB_PATH") or str(ROOT / "data" / "learning.sqlite3"))
api_key = os.getenv("OPENAI_API_KEY", "").strip()
demo = os.getenv("BRIDGE_MOCK_API") == "1"
api = CompatibleAPI(
    api_key, os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1",
    os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
) if api_key else None

with st.sidebar:
    st.header("내 학습")
    st.caption("모의 API 검증 모드" if demo and api else
               "온라인 AI 연결 설정됨" if api else "기본 학습 모드")
    if st.session_state.get("learner"):
        st.code(st.session_state.learner, language=None, wrap_lines=True)
        st.caption("학습 코드를 저장하면 다음에 이어서 할 수 있어요.")
        if st.button("학습 종료"):
            for key in ("learner", "feedback", "display_page"):
                st.session_state.pop(key, None)
            st.rerun()

learner = st.session_state.get("learner")
if not learner:
    st.subheader("분수를 함께 배워요")
    st.write("먼저 10문제를 풀어 보고, 연습이 필요한 부분을 찾아요.")
    st.write("분수의 의미와 비교 · 약분과 통분 · 분수의 덧셈과 뺄셈")
    if st.button("새로 시작하기", type="primary"):
        st.session_state.learner = store.create()
        st.rerun()
    with st.form("restore"):
        code = st.text_input("학습 코드로 이어 하기", max_chars=32, type="password")
        restore = st.form_submit_button("기록 불러오기")
    if restore:
        if store.exists(code.strip().lower()):
            st.session_state.learner = code.strip().lower()
            st.rerun()
        st.error("저장된 학습 코드를 찾지 못했어요.")
    st.stop()

state = store.state(learner)
navigation = ("문제 풀기", "학습 결과", "Agent 실행 로그", "프로젝트 소개")
page = st.sidebar.radio("화면 선택", navigation, key="display_page")


def get_feedback(problem, event, answer=None, outcome=None):
    index = get_index(str(ROOT / "materials"), os.getenv("EMBEDDING_MODEL_PATH"))
    agent = LearningAgent(index, problem, store.state(learner), answer, outcome, api)
    feedback = agent.run(event)
    store.save_log(learner, feedback["log"])
    return feedback


def show_feedback():
    feedback = st.session_state.get("feedback")
    if not feedback:
        return
    if feedback.get("message"):
        st.info(feedback["message"])
    if feedback.get("explanation"):
        st.caption("이전 문제 풀이")
        st.write(feedback["explanation"])
    if feedback.get("hint"):
        st.subheader("힌트")
        st.write(feedback["hint"])
    for source in feedback.get("sources", []):
        with st.expander(f"개념 설명 · {source.source}", expanded=True):
            st.write(source.text)
            st.caption(f"출처 {source.source}")
    if feedback.get("notice"):
        st.caption(feedback["notice"])
    if feedback.get("connection_notice"):
        st.caption(feedback["connection_notice"])
    if feedback.get("mode"):
        mode = feedback["mode"]
        st.caption("온라인 경로 · 모의 API" if demo and mode == "온라인 AI 모드" else mode)


if page == "문제 풀기":
    diagnostic = state["diagnostic"] < len(DIAGNOSTIC)
    if diagnostic:
        number = state["diagnostic"]
        problem = DIAGNOSTIC[number]
        st.subheader(f"기초 진단평가 · {number + 1} / {len(DIAGNOSTIC)}")
        st.progress(number / len(DIAGNOSTIC))
        st.caption("진단이 끝나면 개념별 결과를 확인할 수 있어요.")
    else:
        problem = BY_ID[state["current"]]
        st.subheader("나에게 맞는 문제")
        st.caption(CONCEPTS[problem.concept])
    st.write(problem.prompt)
    with st.form(f"answer-{state['revision']}", clear_on_submit=True):
        answer = st.text_input("내 답", placeholder="예: 3/4 또는 9", max_chars=24)
        submitted = st.form_submit_button("답 제출", type="primary")
    if submitted:
        try:
            outcome = store.submit(learner, problem, answer, state["revision"],
                                   "diagnostic" if diagnostic else "practice")
        except ValueError as error:
            st.error(str(error))
        else:
            event = outcome["action"]
            if event != "diagnostic_next":
                feedback = get_feedback(problem, event, answer, outcome)
                feedback["message"] = ACTIONS[event]
                if outcome["correct"] and not diagnostic:
                    feedback["explanation"] = problem.explanation
                st.session_state.feedback = feedback
            st.rerun()
    if not diagnostic and st.button("힌트 보기"):
        try:
            store.add_hint(learner, problem, state["position"], current_required=True)
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state.feedback = get_feedback(problem, "hint")
    show_feedback()

elif page == "학습 결과":
    st.header("나의 학습 결과")
    history = store.history(learner)
    attempts = history["attempts"]
    correct = sum(item["correct"] for item in attempts)
    a, b, c = st.columns(3)
    a.metric("맞힌 횟수", correct)
    b.metric("틀린 횟수", len(attempts) - correct)
    c.metric("힌트 횟수", history["hints"])
    st.subheader("개념별 숙달도")
    for concept, label in CONCEPTS.items():
        passed, total = state["mastery"][concept]
        if total:
            score = passed / total
            level = "잘하고 있어요" if score >= .8 else "연습이 필요해요"
            st.progress(score, text=f"{label} · {passed}/{total} · {level}")
        else:
            st.write(f"{label} · 아직 풀지 않았어요")
    if state["recommendation"]:
        st.info(f"다음 추천 학습 · {CONCEPTS[state['recommendation']]}")
    if attempts:
        with st.expander("문제 풀이 기록"):
            st.table([{"개념": CONCEPTS[row["concept"]], "문제": BY_ID[row["problem"]].prompt,
                       "내 답": row["answer"], "결과": "정답" if row["correct"] else "오답"}
                      for row in reversed(attempts)])

elif page == "Agent 실행 로그":
    st.header("AI Agent 실행 로그")
    logs = store.history(learner)["logs"]
    if not logs:
        st.info("진단을 마치거나 연습에서 힌트를 사용하면 로그가 생겨요.")
    for number, entries in enumerate(logs):
        with st.expander("최근 학습 활동" if number == 0 else f"이전 활동 {number}", expanded=number == 0):
            for entry in entries:
                label = f"{entry['stage']}. {STAGES[entry['stage']]}"
                if "tool" in entry:
                    label += f" · {entry['tool']}"
                st.markdown(f"**{label}**")
                if isinstance(entry["result"], dict):
                    st.json(entry["result"], expanded=1)
                else:
                    st.write(entry["result"])

else:
    st.header("프로젝트 소개")
    st.write("교육 인프라가 부족한 지역에서도 분수를 꾸준히 연습할 수 있도록 만든 지능시스템 프로젝트예요.")
    st.write("학습 코드를 기억해 두면 다음에 같은 기기에서 기록을 이어 볼 수 있어요.")
    st.write("대구대학교 컴퓨터공학과 · 지능시스템")
