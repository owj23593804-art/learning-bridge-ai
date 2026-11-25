from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pymupdf

from bridge.agent import CompatibleAPI, LearningAgent
from bridge.bank import BY_ID
from bridge.retrieval import MaterialIndex
from bridge.store import Store
from mock_api import MockHandler


ROOT = Path(__file__).resolve().parents[1]


def test_real_http_tool_calling_against_local_fixture(tmp_path):
    with ThreadingHTTPServer(("127.0.0.1", 0), MockHandler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            api = CompatibleAPI("mock-key", f"http://127.0.0.1:{server.server_port}/v1", "mock")
            store = Store(tmp_path / "learning.sqlite3")
            learner = store.create()
            agent = LearningAgent(MaterialIndex(ROOT / "materials"), BY_ID["p1"],
                                  store.state(learner), api=api)
            result = agent.run("hint")
            assert result["mode"] == "온라인 AI 모드"
            assert result["hint"]
            assert result["sources"][0].concept == "meaning"
        finally:
            server.shutdown()
            thread.join()


def test_tagged_pdf_is_indexed_with_page_citation(tmp_path):
    with pymupdf.open() as document:
        document.new_page()
        document.new_page().insert_text((40, 40), "[compare]\nEqual denominators: compare numerators.")
        document.save(tmp_path / "lesson.pdf")
    result = MaterialIndex(tmp_path).search("compare", "Compare numerators")
    assert result[0].source == "lesson.pdf · 2쪽"
    assert "compare numerators" in result[0].text
