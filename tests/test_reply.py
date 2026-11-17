import json
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from core.config import Settings
from core.reply import LLMError, build_system_prompt, build_user_prompt, generate_reply, parse_reply

MODEL_OUTPUT = {
    "natural": "I'd love to hear more about that.",
    "advanced": "Seldom have I encountered such an intriguing proposition; do elaborate.",
    "target_words": [
        {"word": "intriguing", "meaning": "menarik", "example": "An intriguing idea."},
        {"word": "", "meaning": "ignored"},
    ],
}


def make_settings(provider: str, base_url: str, key: str = "") -> Settings:
    return Settings(
        whisper_model="small",
        whisper_device="auto",
        whisper_compute_type="int8",
        llm_provider=provider,
        llm_base_url=base_url,
        llm_api_key=key,
        llm_model="test-model",
        native_language="Indonesian",
        level="C2",
        db_path=Path("unused.db"),
    )


class ParseTests(unittest.TestCase):
    def test_plain_json(self):
        reply = parse_reply(json.dumps(MODEL_OUTPUT))
        self.assertEqual(reply.natural, MODEL_OUTPUT["natural"])
        self.assertEqual([t.word for t in reply.target_words], ["intriguing"])
        self.assertEqual(reply.target_words[0].meaning, "menarik")

    def test_json_inside_code_fence_with_chatter(self):
        raw = "Sure! Here you go:\n```json\n" + json.dumps(MODEL_OUTPUT) + "\n```\nHope that helps."
        self.assertEqual(parse_reply(raw).advanced, MODEL_OUTPUT["advanced"])

    def test_plain_text_falls_back(self):
        reply = parse_reply("Just a plain sentence.")
        self.assertEqual(reply.natural, "Just a plain sentence.")
        self.assertEqual(reply.advanced, "Just a plain sentence.")
        self.assertEqual(reply.target_words, [])

    def test_missing_advanced_uses_natural(self):
        reply = parse_reply(json.dumps({"natural": "Hello there."}))
        self.assertEqual(reply.advanced, "Hello there.")

    def test_empty_raises(self):
        with self.assertRaises(LLMError):
            parse_reply("   ")
        with self.assertRaises(LLMError):
            parse_reply("{}")

    def test_pick(self):
        reply = parse_reply(json.dumps(MODEL_OUTPUT))
        self.assertEqual(reply.pick("natural"), MODEL_OUTPUT["natural"])
        self.assertEqual(reply.pick("advanced"), MODEL_OUTPUT["advanced"])


class PromptTests(unittest.TestCase):
    def test_system_prompt_mentions_level_and_language(self):
        prompt = build_system_prompt("C2", "Indonesian")
        self.assertIn("IELTS band 9", prompt)
        self.assertIn("Indonesian", prompt)

    def test_unknown_level(self):
        with self.assertRaises(ValueError):
            build_system_prompt("Z9", "Indonesian")

    def test_user_prompt_includes_recent_history(self):
        prompt = build_user_prompt("What do you do?", [("Hi", "Hello"), ("How are you?", "Splendid")])
        self.assertIn("Partner: How are you?", prompt)
        self.assertIn("Learner: Splendid", prompt)
        self.assertTrue(prompt.endswith('Partner (just now): "What do you do?"'))


class _Handler(BaseHTTPRequestHandler):
    captured: dict = {}

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Handler.captured = {"path": self.path, "body": body, "headers": {k.lower(): v for k, v in self.headers.items()}}
        text = json.dumps(MODEL_OUTPUT)
        if self.path.endswith("/messages"):
            payload = {"content": [{"type": "text", "text": text}]}
        else:
            payload = {"choices": [{"message": {"content": text}}]}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        # talk to the local server directly, ignoring any proxy in the environment
        urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

    def tearDown(self):
        urllib.request.install_opener(None)

    def test_openai_compatible_endpoint(self):
        settings = make_settings("ollama", self.base + "/v1")
        reply = generate_reply(settings, "Tell me about your weekend.")
        self.assertEqual(reply.natural, MODEL_OUTPUT["natural"])
        self.assertEqual(_Handler.captured["path"], "/v1/chat/completions")
        messages = _Handler.captured["body"]["messages"]
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("Tell me about your weekend.", messages[1]["content"])

    def test_anthropic_endpoint(self):
        settings = make_settings("anthropic", self.base, key="test-key")
        reply = generate_reply(settings, "Tell me about your weekend.", level="B2")
        self.assertEqual(reply.advanced, MODEL_OUTPUT["advanced"])
        self.assertEqual(_Handler.captured["path"], "/v1/messages")
        self.assertEqual(_Handler.captured["headers"]["x-api-key"], "test-key")
        self.assertIn("B2", _Handler.captured["body"]["system"])

    def test_sends_custom_user_agent(self):
        generate_reply(make_settings("ollama", self.base + "/v1"), "Hi there")
        self.assertTrue(_Handler.captured["headers"]["user-agent"].startswith("CorrectMe/"))

    def test_missing_api_key(self):
        with self.assertRaises(LLMError):
            generate_reply(make_settings("openai", self.base + "/v1"), "Hi there")
        with self.assertRaises(LLMError):
            generate_reply(make_settings("anthropic", self.base), "Hi there")

    def test_server_down_gives_clear_error(self):
        with self.assertRaises(LLMError):
            generate_reply(make_settings("ollama", "http://127.0.0.1:9/v1"), "Hi there")


if __name__ == "__main__":
    unittest.main()
