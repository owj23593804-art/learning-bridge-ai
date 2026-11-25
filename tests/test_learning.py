from pathlib import Path
from urllib.error import URLError

import pytest

from bridge.agent import LearningAgent
from bridge.bank import BY_ID, DIAGNOSTIC, grade
from bridge.retrieval import MaterialIndex
from bridge.store import StaleAction, Store


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def learning(tmp_path):
    store = Store(tmp_path / "learning.sqlite3")
    learner = store.create()
    return store, learner


def complete_diagnostic(store, learner, weak=None):
    for problem in DIAGNOSTIC:
        state = store.state(learner)
        answer = "0" if problem.concept == weak else problem.answer
        result = store.submit(learner, problem, answer, state["revision"], "diagnostic")
    return result


def practice(store, learner, answer):
    state = store.state(learner)
    problem = BY_ID[state["current"]]
    result = store.submit(learner, problem, answer, state["revision"], "practice")
    return problem, result


def agent_for(store, learner, problem, api=None, directory=None, answer=None, outcome=None):
    index = MaterialIndex(directory if directory is not None else ROOT / "materials")
    return LearningAgent(index, problem, store.state(learner), answer, outcome, api)


def test_diagnostic_ten_questions_and_mastery(learning):
    store, learner = learning
    result = complete_diagnostic(store, learner, weak="subtract")
    state = store.state(learner)
    assert result["action"] == "diagnostic_done"
    assert state["diagnostic"] == 10
    assert state["mastery"]["subtract"] == (0, 2)
    assert state["recommendation"] == "subtract"


def test_correct_answer_advances(learning):
    store, learner = learning
    complete_diagnostic(store, learner)
    before = store.state(learner)
    problem = BY_ID[before["current"]]
    _, result = practice(store, learner, problem.answer)
    after = store.state(learner)
    assert result["correct"] and result["action"] == "advance"
    assert after["position"] == before["position"] + 1
    assert after["current"] != before["current"]


def test_wrong_answer_provides_hint(learning):
    store, learner = learning
    complete_diagnostic(store, learner, weak="subtract")
    problem, result = practice(store, learner, "0")
    feedback = agent_for(store, learner, problem, answer="0", outcome=result).run(result["action"])
    assert result["action"] == "retry"
    assert feedback["hint"] == problem.hint
    assert problem.answer not in feedback["hint"]
    assert feedback["sources"][0].concept == problem.concept
    assert store.state(learner)["current"] == problem.id


def test_repeat_failure_routes_to_prerequisite(learning):
    store, learner = learning
    complete_diagnostic(store, learner, weak="subtract")
    practice(store, learner, "0")
    _, result = practice(store, learner, "0")
    assert result["action"] == "prerequisite"
    assert BY_ID[store.state(learner)["current"]].concept == "common"


def test_learners_have_isolated_records(learning):
    store, learner = learning
    another = store.create()
    complete_diagnostic(store, learner)
    assert len(store.history(learner)["attempts"]) == 10
    assert not store.history(another)["attempts"]


def test_restart_restores_state_and_history(learning):
    store, learner = learning
    complete_diagnostic(store, learner)
    state = store.state(learner)
    store.add_hint(learner, BY_ID[state["current"]], state["position"], current_required=True)
    store.save_log(learner, [{"stage": 1, "result": "test"}])
    restarted = Store(store.path)
    assert restarted.exists(learner)
    assert restarted.state(learner) == state
    assert restarted.history(learner) == store.history(learner)
    assert restarted.history(learner)["hints"] == 1


def test_search_without_material_shows_notice(learning, tmp_path):
    store, learner = learning
    (tmp_path / "broken.md").write_bytes(b"\xff")
    result = agent_for(store, learner, BY_ID["p1"], directory=tmp_path).run("hint")
    assert result["hint"] and result["notice"]
    assert result["sources"] == []


def test_connection_failure_keeps_basic_mode(learning):
    store, learner = learning

    def unavailable(messages, tools):
        raise URLError("offline")

    result = agent_for(store, learner, BY_ID["p1"], api=unavailable).run("hint")
    assert result["mode"] == "기본 학습 모드"
    assert result["hint"] and result["sources"]
    assert any("전환" in str(event["result"]) for event in result["log"])


def call(name):
    return {"tool_calls": [{"id": name, "type": "function",
                            "function": {"name": name, "arguments": "{}"}}]}


def test_agent_dispatches_tools_and_logs_results(learning):
    store, learner = learning
    evidence_id = MaterialIndex(ROOT / "materials").search("meaning")[0].id
    responses = iter([
        call("search_material"), call("generate_hint"),
        {"content": f'{{"style":"steps","evidence_id":"{evidence_id}"}}'},
    ])

    def fake_api(messages, tools):
        if messages[-1]["role"] == "tool":
            assert messages[-1]["tool_call_id"] in {"search_material", "generate_hint"}
        return next(responses)

    result = agent_for(store, learner, BY_ID["p1"], api=fake_api).run("hint")
    assert result["mode"] == "온라인 AI 모드"
    assert result["hint"].startswith("한 단계씩")
    assert [entry["tool"] for entry in result["log"] if entry["stage"] == 3] == [
        "search_material", "generate_hint"
    ]
    assert {entry["stage"] for entry in result["log"]} == set(range(1, 7))


@pytest.mark.parametrize("invalid", ["{broken", '{"style":"try","evidence_id":"forged"}'])
def test_invalid_response_is_retried_once_then_falls_back(learning, invalid):
    store, learner = learning
    requests = []

    def invalid_api(messages, tools):
        requests.append(messages[-1]["content"])
        return call("generate_hint") if len(requests) == 1 else {"content": invalid}

    result = agent_for(store, learner, BY_ID["p1"], api=invalid_api).run("hint")
    assert len(requests) == 3
    assert result["mode"] == "기본 학습 모드"
    assert result["hint"] == BY_ID["p1"].hint


def test_grading_enforces_problem_format_and_rejects_invalid_answers():
    assert grade(BY_ID["d7"], " 6 / 9 ")
    assert not grade(BY_ID["d5"], "6/8")
    assert not grade(BY_ID["d6"], "2/3")
    assert not grade(BY_ID["d2"], "9/1")
    with pytest.raises(ValueError):
        grade(BY_ID["p1"], "1/0")


def test_stale_submission_cannot_duplicate_attempt(learning):
    store, learner = learning
    question = DIAGNOSTIC[0]
    store.submit(learner, question, question.answer, 0, "diagnostic")
    with pytest.raises(StaleAction):
        store.submit(learner, question, question.answer, 0, "diagnostic")
    assert len(store.history(learner)["attempts"]) == 1
