"""Agnes presenter-presence motion from a local portrait image.

This adapter deliberately does not promise speech or lip synchronization. It
creates a short motion plate that can be used for intros, outros, and reaction
beats while narration is composed separately.
"""

from __future__ import annotations

import base64
import mimetypes
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
from tools.video.agnes_video import AgnesVideo


NO_OVERLAY_PROMPT = (
    "Do not add subtitles, captions, text, words, letters, logos, watermarks, "
    "UI elements, signs, labels, or graphic overlays anywhere in the frame."
)


class AgnesAvatar(BaseTool):
    """Create presenter motion, then leave narration muxing to compose."""

    name = "agnes_avatar"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "avatar"
    provider = "agnes"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:AGNES_API_KEY"]
    install_instructions = AgnesVideo.install_instructions
    agent_skills = ["ai-video-gen", "avatar-video"]

    capabilities = ["photo_to_video", "portrait_motion", "presenter_presence"]
    supports = {
        "photo_to_video": True,
        "audio_driven_animation": False,
        "speech_sync": False,
        "lip_sync": False,
        "local_image": True,
        "cloud_render": True,
    }
    best_for = [
        "short presenter clips where natural motion matters more than accurate lip sync",
        "Agnes image-to-video followed by separately generated narration",
    ]
    not_good_for = [
        "accurate lip sync",
        "continuous clips longer than 12 seconds",
    ]
    fallback_tools = ["talking_head", "kling_avatar"]

    input_schema = {
        "type": "object",
        "required": ["prompt", "image_path", "output_path"],
        "properties": {
            "prompt": {"type": "string"},
            "image_path": {"type": "string"},
            "duration": {
                "type": "integer",
                "minimum": 4,
                "maximum": 12,
                "default": 6,
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"],
                "default": "9:16",
            },
            "seed": {"type": "integer"},
            "output_path": {
                "type": "string",
                "description": "Explicit project asset path for the generated motion plate",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=768, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=1,
        backoff_seconds=10.0,
        retryable_errors=["rate_limit", "timeout"],
    )
    idempotency_key_fields = [
        "prompt",
        "image_path",
        "duration",
        "aspect_ratio",
        "seed",
    ]
    side_effects = ["calls Agnes video API", "writes avatar video to output_path"]
    user_visible_verification = [
        "Confirm the presenter has natural motion and identity remains recognizable",
        "Confirm stakeholders understand mouth motion is not synchronized to narration",
    ]

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return AgnesVideo().estimate_cost(inputs)

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return AgnesVideo().estimate_runtime(inputs)

    @staticmethod
    def _image_data_uri(image_path: str) -> str:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Avatar image not found: {path}")
        mime_type, _ = mimetypes.guess_type(path.name)
        if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("Agnes avatar image must be PNG, JPEG, or WebP")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        output_path = inputs.get("output_path")
        if not output_path:
            return ToolResult(
                success=False,
                error=(
                    "output_path is required; write presenter motion under "
                    "projects/<project-id>/assets/video/"
                ),
            )

        try:
            image_url = self._image_data_uri(inputs["image_path"])
        except (KeyError, OSError, ValueError) as exc:
            return ToolResult(success=False, error=str(exc))

        prompt = f"{inputs['prompt'].strip()}\n\n{NO_OVERLAY_PROMPT}"

        delegated_inputs: dict[str, Any] = {
            "prompt": prompt,
            "operation": "image_to_video",
            "model": "agnes-video-2.5-flash",
            "duration": int(inputs.get("duration", 6)),
            "aspect_ratio": inputs.get("aspect_ratio", "9:16"),
            "image_url": image_url,
            "output_path": output_path,
        }
        if inputs.get("seed") is not None:
            delegated_inputs["seed"] = int(inputs["seed"])

        result = AgnesVideo().execute(delegated_inputs)
        if result.success:
            result.data.update(
                {
                    "operation": "image_to_avatar_video",
                    "source_image": str(Path(inputs["image_path"])),
                    "lip_sync": False,
                    "speech_sync": False,
                    "presenter_mode": "generated_presence",
                    "overlays_forbidden_in_prompt": True,
                }
            )
        return result
