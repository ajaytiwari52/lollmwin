import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ollama_coder.cli import CoderError, _project_path, _request_streaming_chat, _write_file


class ProjectPathTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rejects_paths_outside_project(self):
        with self.assertRaises(CoderError):
            _project_path(self.root, "..\\outside.txt")

    def test_rejects_git_directory(self):
        with self.assertRaises(CoderError):
            _project_path(self.root, ".git\\config")

    def test_rejects_environment_files(self):
        with self.assertRaises(CoderError):
            _project_path(self.root, ".env")

    def test_declined_write_leaves_file_unchanged(self):
        target = self.root / "sample.txt"
        target.write_text("before\n", encoding="utf-8")
        with patch("ollama_coder.cli._approved", return_value=False):
            result = _write_file(self.root, {"path": "sample.txt", "content": "after\n"})
        self.assertIn("declined", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "before\n")

    def test_approved_write_updates_file(self):
        target = self.root / "sample.txt"
        with patch("ollama_coder.cli._approved", return_value=True):
            result = _write_file(self.root, {"path": "sample.txt", "content": "created\n"})
        self.assertIn("Wrote sample.txt", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "created\n")

    def test_streams_response_content_and_collects_tool_calls(self):
        chunks = [
            {"message": {"role": "assistant", "content": "Creating "}, "done": False},
            {
                "message": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {
                                "name": "write_file",
                                "arguments": {"path": "main.py", "content": "print('hello')"},
                            },
                        }
                    ]
                },
                "done": True,
            },
        ]
        body = b"".join(json.dumps(chunk).encode("utf-8") + b"\n" for chunk in chunks)
        with patch("ollama_coder.cli.urllib.request.urlopen", return_value=io.BytesIO(body)):
            with redirect_stdout(io.StringIO()) as output:
                message = _request_streaming_chat("http://localhost:11434/api/chat", {})
        self.assertEqual(message["content"], "Creating ")
        self.assertEqual(message["tool_calls"][0]["function"]["name"], "write_file")
        self.assertEqual(
            message["tool_calls"][0]["function"]["arguments"],
            {"path": "main.py", "content": "print('hello')"},
        )
        self.assertIn("Creating ", output.getvalue())

    def test_collects_partial_streamed_tool_arguments(self):
        chunks = [
            {
                "message": {
                    "tool_calls": [
                        {"index": 0, "function": {"name": "write_file", "arguments": "{\"path\":"}}
                    ]
                },
                "done": False,
            },
            {
                "message": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {"arguments": " \"main.py\", \"content\": \"print(1)\"}"},
                        }
                    ]
                },
                "done": True,
            },
        ]
        body = b"".join(json.dumps(chunk).encode("utf-8") + b"\n" for chunk in chunks)
        with patch("ollama_coder.cli.urllib.request.urlopen", return_value=io.BytesIO(body)):
            with redirect_stdout(io.StringIO()):
                message = _request_streaming_chat("http://localhost:11434/api/chat", {})
        self.assertEqual(
            message["tool_calls"][0]["function"]["arguments"],
            {"path": "main.py", "content": "print(1)"},
        )


if __name__ == "__main__":
    unittest.main()
