# Agnes Presenter-Presence Smoke Validation

Date: 2026-09-13

Branch: `codex/feat/agnes-avatar-smoke`

## Purpose

Validate one minimum path from a generated portrait through Agnes image-to-video
and OpenMontage composition. This is a smoke result, not a provider benchmark or
a claim that Agnes provides audio-driven avatar speech.

## Proven Path

- Agnes produced a 12.25-second vertical presenter-motion source clip.
- OpenMontage looped/cut that source against 33.5 seconds of externally supplied
  Mandarin narration.
- `Uplifting Sunset.mp3` was mixed beneath narration with ducking.
- The final output is H.264 at 704×1280 with mono AAC audio at 48 kHz.
- FFmpeg decoded the complete 33.5-second output without errors.

The regenerable local evidence remains under
`projects/agnes-avatar-smoke/` and is intentionally excluded from Git.

## Findings

1. The Agnes image-to-video path is operational and suitable for short
   presenter-presence or reaction footage.
2. The model is not driven by the narration. Mouth motion does not align with
   the spoken words, so this path must not be represented as lip-synchronized
   digital-human speech.
3. The accepted source clip contained hallucinated white text. Future presenter
   prompts must explicitly forbid subtitles, captions, words, letters, logos,
   watermarks, UI elements, signs, labels, and graphic overlays, followed by
   visual review.
4. The appropriate default treatment is hybrid: short non-speaking presenter
   beats plus narration-led graphics, screen material, or B-roll.

## Minimum Regression Gate

No full-suite run is required for this experimental provider branch. Before
merge, run only:

- Agnes provider contract tests with mocked network transport,
- Agnes presenter adapter tests,
- registry discovery for both tools,
- focused compose tests for project-relative paths and 48 kHz AAC muxing,
- schema validation for the `approval_policy` decision category.
