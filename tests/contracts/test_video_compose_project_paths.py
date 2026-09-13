"""Focused regressions from the Agnes presenter smoke composition."""

from __future__ import annotations

from tools.base_tool import ToolResult
from tools.video.video_compose import VideoCompose


def test_render_resolves_manifest_assets_from_explicit_project_dir(
    monkeypatch,
    tmp_path,
):
    project_dir = tmp_path / "projects" / "smoke"
    source = project_dir / "assets" / "video" / "clip.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    captured = {}
    tool = VideoCompose()

    monkeypatch.setattr(tool, "_pre_compose_validation", lambda *args: None)

    def fake_render_via_ffmpeg(**kwargs):
        captured.update(kwargs)
        return ToolResult(success=True)

    monkeypatch.setattr(tool, "_render_via_ffmpeg", fake_render_via_ffmpeg)
    result = tool._render(
        {
            "project_dir": str(project_dir),
            "output_path": str(project_dir / "renders" / "final.mp4"),
            "edit_decisions": {
                "render_runtime": "ffmpeg",
                "cuts": [
                    {
                        "source": "presenter",
                        "in_seconds": 0,
                        "out_seconds": 4,
                    }
                ],
            },
            "asset_manifest": {
                "assets": [
                    {"id": "presenter", "path": "assets/video/clip.mp4"}
                ]
            },
        }
    )

    assert result.success is True
    assert captured["resolved_cuts"][0]["source"] == str(source.resolve())


def test_render_rejects_project_relative_asset_escape(tmp_path):
    project_dir = tmp_path / "projects" / "smoke"
    tool = VideoCompose()
    result = tool._render(
        {
            "project_dir": str(project_dir),
            "output_path": str(project_dir / "renders" / "final.mp4"),
            "edit_decisions": {
                "render_runtime": "ffmpeg",
                "cuts": [
                    {
                        "source": "presenter",
                        "in_seconds": 0,
                        "out_seconds": 4,
                    }
                ],
            },
            "asset_manifest": {
                "assets": [{"id": "presenter", "path": "../outside.mp4"}]
            },
        }
    )

    assert result.success is False
    assert "escapes project_dir" in (result.error or "")


def test_compose_external_audio_is_mapped_and_normalized_to_48khz(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "source.mp4"
    audio = tmp_path / "narration.wav"
    source.write_bytes(b"video")
    audio.write_bytes(b"audio")
    commands = []
    tool = VideoCompose()

    monkeypatch.setattr(tool, "_has_audio_stream", lambda _: True)
    monkeypatch.setattr(tool, "run_command", lambda command, **kwargs: commands.append(command))

    result = tool._compose(
        {
            "edit_decisions": {
                "cuts": [
                    {
                        "source": str(source),
                        "in_seconds": 0,
                        "out_seconds": 4,
                    }
                ]
            },
            "audio_path": str(audio),
            "output_path": str(tmp_path / "final.mp4"),
        }
    )

    assert result.success is True
    final_command = commands[-1]
    first_map = final_command.index("-map")
    assert final_command[first_map:first_map + 4] == ["-map", "0:v", "-map", "1:a"]
    assert final_command[final_command.index("-b:a") + 1] == "192k"
    assert final_command[final_command.index("-ar") + 1] == "48000"
