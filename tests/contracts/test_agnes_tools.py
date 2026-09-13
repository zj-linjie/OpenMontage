"""Focused contract tests for the Agnes video and presenter adapters."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.avatar.agnes_avatar import AgnesAvatar, NO_OVERLAY_PROMPT
from tools.base_tool import ToolResult, ToolStatus
from tools.video.agnes_video import AgnesVideo, DEFAULT_MODEL


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data=None,
        content: bytes = b"",
        content_type: str = "application/json",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.text = str(json_data)

    def json(self):
        if self._json_data is None:
            raise ValueError("not json")
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_registry_discovers_agnes_tools(monkeypatch, isolated_tool_registry):
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    isolated_tool_registry.discover("tools")

    video = isolated_tool_registry.get("agnes_video")
    presenter = isolated_tool_registry.get("agnes_avatar")
    assert video is not None
    assert presenter is not None
    assert video.capability == "video_generation"
    assert presenter.capability == "avatar"
    assert presenter.supports["speech_sync"] is False


def test_agnes_status_tracks_api_key(monkeypatch):
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    assert AgnesVideo().get_status() == ToolStatus.UNAVAILABLE
    assert AgnesAvatar().get_status() == ToolStatus.UNAVAILABLE

    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    assert AgnesVideo().get_status() == ToolStatus.AVAILABLE
    assert AgnesAvatar().get_status() == ToolStatus.AVAILABLE


def test_agnes_25_payloads_and_idempotency_fields():
    tool = AgnesVideo()
    text_payload = tool._build_payload(
        {
            "prompt": "quiet presenter",
            "operation": "text_to_video",
            "duration": 6,
            "aspect_ratio": "9:16",
        }
    )
    assert text_payload == {
        "model": DEFAULT_MODEL,
        "prompt": "quiet presenter",
        "seconds": "6",
        "size": "720P",
        "mode": "text",
        "aspect_ratio": "9:16",
    }

    image_payload = tool._build_payload(
        {
            "prompt": "subtle head motion",
            "operation": "image_to_video",
            "image_url": "data:image/png;base64,AAAA",
            "last_frame_url": "https://example.com/end.png",
            "seed": 7,
        }
    )
    assert image_payload["mode"] == "keyframe"
    assert image_payload["first_frame"].startswith("data:image/png")
    assert image_payload["last_frame"].endswith("end.png")
    assert image_payload["seed"] == 7

    for field in ("image_url", "last_frame_url", "seed"):
        assert field in tool.idempotency_key_fields


def test_legacy_model_rejects_last_frame():
    with pytest.raises(ValueError, match="only by Agnes 2.5"):
        AgnesVideo()._build_payload(
            {
                "prompt": "legacy",
                "model": "agnes-video-v2.0",
                "last_frame_url": "https://example.com/end.png",
            }
        )


def test_execute_requires_explicit_project_output(monkeypatch):
    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    result = AgnesVideo().execute({"prompt": "test"})
    assert result.success is False
    assert "output_path is required" in (result.error or "")


def test_execute_submits_polls_and_downloads(monkeypatch, tmp_path):
    import requests

    output_path = tmp_path / "projects" / "smoke" / "assets" / "video" / "clip.mp4"
    calls: list[tuple[str, str]] = []

    def fake_post(url, **kwargs):
        calls.append(("post", url))
        assert kwargs["json"]["model"] == DEFAULT_MODEL
        return _FakeResponse(json_data={"video_id": "task-123"})

    def fake_get(url, **kwargs):
        calls.append(("get", url))
        if url.endswith("/agnesapi"):
            assert kwargs["params"] == {
                "video_id": "task-123",
                "model_name": DEFAULT_MODEL,
            }
            return _FakeResponse(
                json_data={
                    "status": "completed",
                    "video_url": "https://cdn.example.com/clip.mp4",
                }
            )
        return _FakeResponse(content=b"fake-mp4", content_type="video/mp4")

    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("tools.video.agnes_video.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "tools.video._shared.probe_output",
        lambda path: {"duration_seconds": 6.0},
    )

    result = AgnesVideo().execute(
        {
            "prompt": "presenter looks at camera",
            "output_path": str(output_path),
            "poll_interval_seconds": 5,
        }
    )

    assert result.success is True
    assert output_path.read_bytes() == b"fake-mp4"
    assert result.data["task_id"] == "task-123"
    assert result.data["duration_seconds"] == 6.0
    assert calls == [
        ("post", "https://apihub.agnes-ai.com/v1/videos"),
        ("get", "https://apihub.agnes-ai.com/v1/agnesapi"),
        ("get", "https://cdn.example.com/clip.mp4"),
    ]


def test_presenter_adapter_adds_overlay_guard_and_truthful_metadata(
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "portrait.png"
    image_path.write_bytes(b"png-bytes")
    output_path = tmp_path / "projects" / "smoke" / "assets" / "video" / "presenter.mp4"
    delegated = {}

    def fake_execute(self, inputs):
        delegated.update(inputs)
        return ToolResult(success=True, data={"provider": "agnes"})

    monkeypatch.setattr(AgnesVideo, "execute", fake_execute)
    result = AgnesAvatar().execute(
        {
            "prompt": "Subtle natural head movement.",
            "image_path": str(image_path),
            "output_path": str(output_path),
        }
    )

    assert result.success is True
    assert NO_OVERLAY_PROMPT in delegated["prompt"]
    assert delegated["image_url"].startswith("data:image/png;base64,")
    assert result.data["presenter_mode"] == "generated_presence"
    assert result.data["lip_sync"] is False
    assert result.data["speech_sync"] is False


def test_presenter_requires_explicit_project_output(tmp_path):
    image_path = tmp_path / "portrait.webp"
    image_path.write_bytes(b"webp-bytes")
    result = AgnesAvatar().execute(
        {"prompt": "test", "image_path": str(image_path)}
    )
    assert result.success is False
    assert "output_path is required" in (result.error or "")
