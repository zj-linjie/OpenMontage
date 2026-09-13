"""Agnes AI video generation (agnes-video-2.5 / agnes-video-2.5-flash / agnes-video-v2.0).

Async submit-then-poll provider against the Agnes OpenAI-style API
(https://apihub.agnes-ai.com/v1 by default). Latency is high: generation
commonly takes several minutes, and the endpoint rate-limits submissions to
~2 per minute, so poll_interval/timeout defaults are generous.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolTier,
)

DEFAULT_BASE_URL = "https://apihub.agnes-ai.com/v1"
DEFAULT_MODEL = "agnes-video-2.5-flash"

_MODELS_25 = ("agnes-video-2.5-flash", "agnes-video-2.5")

# Response JSON fields (in any nesting) that may carry the finished video.
_VIDEO_URL_FIELDS = (
    ("video_url",),
    ("url",),
    ("output_url",),
    ("video", "url"),
    ("data", "url"),
    ("data", 0, "url"),
    ("metadata", "video_url"),
)

_DONE_STATUSES = {"completed", "succeeded", "success", "done"}
_FAILED_STATUSES = {"failed", "error", "cancelled", "canceled"}


def _extract_video_url(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None

    def dig(node: Any, path: tuple) -> Any:
        for key in path:
            if isinstance(node, dict):
                node = node.get(key)
            elif isinstance(node, list) and isinstance(key, int) and len(node) > key:
                node = node[key]
            else:
                return None
        return node

    for path in _VIDEO_URL_FIELDS:
        value = dig(payload, path)
        if isinstance(value, str) and value.startswith(
            ("http://", "https://", "data:video/")
        ):
            return value
    return None


def _response_content_type(response: Any) -> str:
    headers = getattr(response, "headers", {}) or {}
    value = headers.get("Content-Type") or headers.get("content-type") or ""
    return str(value).split(";", 1)[0].strip().lower()


def _is_video_response(response: Any) -> bool:
    content_type = _response_content_type(response)
    return content_type.startswith("video/") or content_type == "application/octet-stream"


def _decode_video_data_uri(value: str) -> bytes:
    header, separator, encoded = value.partition(",")
    if not separator or ";base64" not in header.lower():
        raise ValueError("Agnes returned an invalid video data URI")
    return base64.b64decode(encoded, validate=True)


def _retry_after_seconds(response: Any, default: int) -> int:
    headers = getattr(response, "headers", {}) or {}
    value = headers.get("Retry-After") or headers.get("retry-after")
    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return max(1, default)


def _legacy_num_frames(duration: int) -> int:
    """Nearest 8n+1 frame count (Agnes v2.0 constraint) for a duration at 24fps."""
    target = max(1, duration) * 24 + 1
    n = max(1, round((target - 1) / 8))
    return min(441, 8 * n + 1)


_LEGACY_RESOLUTIONS = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "1:1": (960, 960),
    "4:3": (1024, 768),
    "3:4": (768, 1024),
}


class AgnesVideo(BaseTool):
    name = "agnes_video"
    version = "0.2.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "agnes"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:AGNES_API_KEY"]
    install_instructions = (
        "Set AGNES_API_KEY to your Agnes API key (https://platform.agnes-ai.com).\n"
        "  Optional: AGNES_BASE_URL to override https://apihub.agnes-ai.com/v1"
    )
    agent_skills = ["ai-video-gen"]

    capabilities = ["text_to_video", "image_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "first_frame": True,
        "last_frame": True,
        "last_frame_models": list(_MODELS_25),
    }
    best_for = [
        "4-12 second clips when a local Agnes subscription is the available budget",
        "keyframe-conditioned motion from a generated still (first/last frame)",
    ]
    not_good_for = [
        "fast turnaround (minutes-level latency, ~2 submissions per minute)",
        "footage longer than 12 seconds per clip",
    ]
    fallback_tools = ["veo_video", "kling_video", "grok_video"]

    input_schema = {
        "type": "object",
        "required": ["prompt", "output_path"],
        "properties": {
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video"],
                "default": "text_to_video",
            },
            "model": {
                "type": "string",
                "enum": ["agnes-video-2.5-flash", "agnes-video-2.5", "agnes-video-v2.0"],
                "default": DEFAULT_MODEL,
            },
            "duration": {
                "type": "integer",
                "minimum": 4,
                "maximum": 12,
                "default": 6,
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"],
                "default": "16:9",
            },
            "image_url": {
                "type": "string",
                "description": "First-frame HTTP(S) URL or data URI for image_to_video",
            },
            "last_frame_url": {
                "type": "string",
                "description": "Optional last-frame image URL (agnes-video-2.5 keyframe mode)",
            },
            "seed": {"type": "integer"},
            "output_path": {"type": "string"},
            "poll_interval_seconds": {"type": "integer", "minimum": 5, "default": 10},
            "timeout_seconds": {"type": "integer", "minimum": 60, "default": 1500},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = [
        "prompt",
        "operation",
        "model",
        "duration",
        "aspect_ratio",
        "image_url",
        "last_frame_url",
        "seed",
    ]
    side_effects = ["writes video file to output_path", "calls Agnes video API"]
    user_visible_verification = ["Watch generated clip for motion quality and prompt fidelity"]

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # Agnes bills through the user's own subscription; no per-clip USD
        # pricing is published, so report zero to keep budget gates honest
        # about out-of-pocket API spend.
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 240.0 + int(inputs.get("duration", 6)) * 20.0

    def _build_payload(self, inputs: dict[str, Any]) -> dict[str, Any]:
        model = inputs.get("model", DEFAULT_MODEL)
        operation = inputs.get("operation", "text_to_video")
        prompt = inputs["prompt"]
        duration = int(inputs.get("duration", 6))
        aspect_ratio = inputs.get("aspect_ratio", "16:9")

        if model not in _MODELS_25 and inputs.get("last_frame_url"):
            raise ValueError("last_frame_url is supported only by Agnes 2.5 models")

        if model in _MODELS_25:
            payload: dict[str, Any] = {
                "model": model,
                "prompt": prompt,
                "seconds": str(duration),
                "size": "720P",
            }
            if operation == "image_to_video":
                if not inputs.get("image_url"):
                    raise ValueError("image_to_video requires image_url")
                payload["mode"] = "keyframe"
                payload["first_frame"] = inputs["image_url"]
                if inputs.get("last_frame_url"):
                    payload["last_frame"] = inputs["last_frame_url"]
            else:
                payload["mode"] = "text"
                payload["aspect_ratio"] = aspect_ratio
            if inputs.get("seed") is not None:
                payload["seed"] = int(inputs["seed"])
            return payload

        # Legacy agnes-video-v2.0 shape: explicit width/height/num_frames.
        width, height = _LEGACY_RESOLUTIONS.get(aspect_ratio, (1280, 720))
        payload = {
            "model": model,
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_frames": _legacy_num_frames(duration),
            "frame_rate": 24,
        }
        if operation == "image_to_video":
            if not inputs.get("image_url"):
                raise ValueError("image_to_video requires image_url")
            payload["image"] = inputs["image_url"]
        if inputs.get("seed") is not None:
            payload["seed"] = int(inputs["seed"])
        return payload

    @staticmethod
    def _task_id(payload: dict[str, Any]) -> str | None:
        for key in ("video_id", "task_id", "id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        import requests

        from tools.video._shared import probe_output

        output_value = inputs.get("output_path")
        if not output_value:
            return ToolResult(
                success=False,
                error=(
                    "output_path is required; write Agnes outputs under "
                    "projects/<project-id>/assets/video/"
                ),
            )

        api_key = os.environ.get("AGNES_API_KEY")
        if not api_key:
            return ToolResult(
                success=False,
                error="AGNES_API_KEY not set. " + self.install_instructions,
            )
        base_url = os.environ.get("AGNES_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

        start = time.time()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            payload = self._build_payload(inputs)
            model = payload["model"]

            submit = requests.post(
                f"{base_url}/videos",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if submit.status_code == 429:
                return ToolResult(
                    success=False,
                    error="Agnes rate limit (max ~2 submissions/minute). Wait 60s and retry.",
                )
            submit.raise_for_status()
            task_id = self._task_id(submit.json())
            if not task_id:
                return ToolResult(
                    success=False,
                    error=f"Agnes submit response missing task id: {submit.text[:300]}",
                )

            timeout_seconds = int(inputs.get("timeout_seconds", 1500))
            poll_interval = int(inputs.get("poll_interval_seconds", 10))
            deadline = time.time() + timeout_seconds
            result_data: dict[str, Any] | None = None
            video_bytes: bytes | None = None

            while time.time() < deadline:
                time.sleep(poll_interval)
                if model in _MODELS_25:
                    poll = requests.get(
                        f"{base_url}/agnesapi",
                        headers={"Authorization": headers["Authorization"]},
                        params={"video_id": task_id, "model_name": model},
                        timeout=60,
                    )
                else:
                    poll = requests.get(
                        f"{base_url}/videos/{task_id}",
                        headers={"Authorization": headers["Authorization"]},
                        timeout=60,
                    )
                if poll.status_code == 429 or poll.status_code >= 500:
                    remaining = max(0, int(deadline - time.time()))
                    if remaining:
                        time.sleep(
                            min(_retry_after_seconds(poll, poll_interval), remaining)
                        )
                    continue
                poll.raise_for_status()

                if _is_video_response(poll) and poll.content:
                    video_bytes = poll.content
                    break

                try:
                    result_data = poll.json()
                except ValueError:
                    continue

                status = str(result_data.get("status", "")).lower()
                if _extract_video_url(result_data):
                    break
                if status in _DONE_STATUSES:
                    break
                if status in _FAILED_STATUSES:
                    detail = result_data.get("error") or result_data.get("message") or status
                    return ToolResult(
                        success=False,
                        error=f"Agnes video generation failed: {detail}",
                    )

            video_url = _extract_video_url(result_data) if result_data else None
            if video_bytes is None and video_url:
                if video_url.startswith("data:video/"):
                    video_bytes = _decode_video_data_uri(video_url)
                else:
                    download = requests.get(video_url, timeout=300)
                    download.raise_for_status()
                    video_bytes = download.content

            # Some Agnes responses report completion without an output URL.
            # The content endpoint is the documented final fallback for those tasks.
            if video_bytes is None:
                content_response = requests.get(
                    f"{base_url}/videos/{task_id}/content",
                    headers={"Authorization": headers["Authorization"]},
                    timeout=300,
                )
                content_response.raise_for_status()
                if _is_video_response(content_response) and content_response.content:
                    video_bytes = content_response.content
                else:
                    try:
                        content_data = content_response.json()
                    except ValueError:
                        content_data = None
                    content_url = _extract_video_url(content_data)
                    if content_url and content_url.startswith("data:video/"):
                        video_bytes = _decode_video_data_uri(content_url)
                    elif content_url:
                        download = requests.get(content_url, timeout=300)
                        download.raise_for_status()
                        video_bytes = download.content

            if not video_bytes:
                return ToolResult(
                    success=False,
                    error=(
                        "Agnes video generation timed out or returned no video "
                        f"after {timeout_seconds}s (task {task_id})"
                    ),
                )

            output_path = Path(output_value)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(video_bytes)

        except Exception as e:
            return ToolResult(success=False, error=f"Agnes video generation failed: {e}")

        probed = probe_output(output_path)
        return ToolResult(
            success=True,
            data={
                "provider": "agnes",
                "model": model,
                "prompt": inputs["prompt"],
                "operation": inputs.get("operation", "text_to_video"),
                "task_id": task_id,
                "output": str(output_path),
                "output_path": str(output_path),
                "format": "mp4",
                **probed,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )
