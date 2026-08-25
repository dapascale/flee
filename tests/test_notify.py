from unittest.mock import patch

from src.notify import notify_all, send_ntfy


def test_ntfy_title_with_emoji_does_not_crash(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.sh")

    with patch("src.notify.httpx.post") as post:
        post.return_value.raise_for_status.return_value = None
        send_ntfy("✈ Orlando in winter: $406", "some body")

    _, kwargs = post.call_args
    assert kwargs["headers"]["Title"] == "✈ Orlando in winter: $406".encode("utf-8")


def test_ntfy_click_url_sets_click_header(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")

    with patch("src.notify.httpx.post") as post:
        post.return_value.raise_for_status.return_value = None
        send_ntfy("title", "body", click_url="https://example.github.io/flee/")

    _, kwargs = post.call_args
    assert kwargs["headers"]["Click"] == b"https://example.github.io/flee/"


def test_ntfy_without_click_url_omits_click_header(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")

    with patch("src.notify.httpx.post") as post:
        post.return_value.raise_for_status.return_value = None
        send_ntfy("title", "body")

    _, kwargs = post.call_args
    assert "Click" not in kwargs["headers"]


def test_notify_all_appends_app_url_to_message_and_sets_click(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    monkeypatch.setenv("APP_URL", "https://example.github.io/flee/")

    with patch("src.notify.send_ntfy") as ntfy, patch("src.notify.send_email") as email:
        notify_all(["ntfy", "email"], "title", "body")

    ntfy_kwargs = ntfy.call_args.kwargs
    assert ntfy_kwargs["click_url"] == "https://example.github.io/flee/"
    assert "https://example.github.io/flee/" in ntfy.call_args.args[1]
    assert "https://example.github.io/flee/" in email.call_args.args[1]


def test_notify_all_without_app_url_leaves_message_unchanged(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    monkeypatch.delenv("APP_URL", raising=False)

    with patch("src.notify.send_ntfy") as ntfy, patch("src.notify.send_email"):
        notify_all(["ntfy"], "title", "body")

    assert ntfy.call_args.args[1] == "body"
    assert ntfy.call_args.kwargs["click_url"] is None
