from pathlib import Path

from streamlit.testing.v1 import AppTest

from bridge.bank import DIAGNOSTIC


def test_streamlit_offline_learning_and_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIDGE_DB_PATH", str(tmp_path / "learning.sqlite3"))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=20).run()
    next(button for button in app.button if button.label == "새로 시작하기").click().run()
    code = app.session_state["learner"]
    for question in DIAGNOSTIC:
        answer = "0" if question.concept == "subtract" else question.answer
        app.text_input[0].set_value(answer)
        next(button for button in app.button if button.label == "답 제출").click().run()
        assert not app.exception
    assert any("나에게 맞는 문제" in heading.value for heading in app.subheader)
    app.text_input[0].set_value("0")
    next(button for button in app.button if button.label == "답 제출").click().run()
    assert any(heading.value == "힌트" for heading in app.subheader)
    assert any("기본 학습 모드" == caption.value for caption in app.caption)
    app.radio[0].set_value("Agent 실행 로그").run()
    assert any("AI Agent 실행 로그" == heading.value for heading in app.header)

    resumed = AppTest.from_file(str(app_path), default_timeout=20).run()
    resumed.text_input[0].set_value(code)
    next(button for button in resumed.button if button.label == "기록 불러오기").click().run()
    resumed.radio[0].set_value("학습 결과").run()
    assert [metric.value for metric in resumed.metric] == ["8", "3", "1"]
    assert not resumed.exception
