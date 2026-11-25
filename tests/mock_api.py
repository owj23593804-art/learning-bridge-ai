"""Local Chat Completions fixture for tests and reproducible browser demos."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
from urllib.parse import urlsplit


class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if urlsplit(self.path).path != "/v1/chat/completions":
            self.send_error(404)
            return
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        messages = request["messages"]
        event = json.loads(messages[1]["content"])["event"]
        plans = {
            "diagnostic_done": ("diagnose_level", "update_learning_plan"),
            "advance": ("evaluate_answer", "update_learning_plan"),
            "hint": ("search_material", "generate_hint"),
            "retry": ("evaluate_answer", "search_material", "generate_hint"),
            "prerequisite": ("search_material", "update_learning_plan"),
            "review": ("search_material", "update_learning_plan"),
        }
        outputs = {m["tool_call_id"]: json.loads(m["content"])
                   for m in messages if m["role"] == "tool"}
        remaining = [name for name in plans[event] if name not in outputs]
        if remaining:
            name = remaining[0]
            message = {"content": None, "tool_calls": [{
                "id": name, "type": "function", "function": {"name": name, "arguments": "{}"},
            }]}
        else:
            sources = outputs.get("search_material", {}).get("sources", [])
            message = {"content": json.dumps({
                "style": "steps", "evidence_id": sources[0]["id"] if sources else None,
            })}
        content = json.dumps({"choices": [{"message": message}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765),
                             MockHandler) as server:
        server.serve_forever()
