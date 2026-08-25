from unittest.mock import patch

from src.notify import send_ntfy


def test_ntfy_title_with_emoji_does_not_crash(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.sh")

    with patch("src.notify.httpx.post") as post:
        post.return_value.raise_for_status.return_value = None
        send_ntfy("✈ Orlando in winter: $406", "some body")

    _, kwargs = post.call_args
    assert kwargs["headers"]["Title"] == "✈ Orlando in winter: $406".encode("utf-8")
