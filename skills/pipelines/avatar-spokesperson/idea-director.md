# Idea Director - Avatar Spokesperson Pipeline

## When To Use

Use this pipeline when the deliverable is a presenter-led avatar video: a spokesperson spot, product intro, onboarding message, internal comms update, or short scripted explainer where the speaker remains the visual anchor.

Your first job is to classify the avatar path honestly before anyone writes polished copy for an impossible production setup.

## Runtime Selection (MANDATORY — present the constraint, don't silently pick)

Lock `render_runtime = "remotion"`. **HyperFrames is NOT a valid runtime on this pipeline in Phase 1** — avatar-spokesperson depends on the Remotion `TalkingHead` composition and `remotion_caption_burn`, and neither has HyperFrames parity yet.

Per AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)": do NOT silently default. Tell the user: "HyperFrames is available on your machine, but avatar-spokesperson depends on the Remotion TalkingHead composition and caption burn, so remotion is the only viable runtime here — OK to proceed?" Record a `render_runtime_selection` decision with hyperframes `rejected_because: "TalkingHead + caption parity deferred on avatar-spokesperson"`.

## Reference Inputs

- `docs/avatar-spokesperson-best-practices.md`
- `skills/creative/storytelling.md`
- `skills/creative/short-form.md`

## Process

### 1. Classify The Presenter Mode

Record one `presenter_mode` and its delivery promise:

- `audio_driven_avatar` — a photo or platform avatar driven by the approved audio,
- `presenter_plate_lip_sync` — an existing video plate re-timed to approved audio,
- `generated_presence` — a model-generated motion plate for non-speaking intros,
  outros, or reaction beats; it does not promise lip sync,
- `narration_over_graphics` — no presenter performance; narration leads the visuals.

Also record `speech_sync_required` and whether the presenter source already
exists. Route ordinary source-footage speakers to `talking-head`; route reusable
rigged 2D/3D characters to `character-animation` instead of forcing them through
this pipeline.

### 2. Define The Message Shape

Capture:

- audience,
- core offer or CTA,
- runtime target,
- platform targets,
- whether the video is sales, onboarding, support, or announcement led.

Spokesperson videos work best when they have one clear job.

### 3. Capture Source Reality

The brief should explicitly state:

- whether clean narration is supplied,
- whether TTS is acceptable,
- whether brand backgrounds or overlays exist,
- whether subtitles are required,
- whether multilingual variants are expected.

### 4. Build The Brief

Recommended metadata keys:

- `presenter_mode`
- `speech_sync_required`
- `avatar_path` (legacy compatibility)
- `avatar_exists`
- `narration_source`
- `target_audience`
- `cta_type`
- `background_strategy`
- `deliverable_mix`
- `missing_capabilities`

### 5. Quality Gate

- the presenter mode and speech-sync promise are explicit,
- the message is narrow enough for a spokesperson format,
- missing narration or avatar dependencies are visible early,
- deliverables fit the actual source setup.

## Common Pitfalls

- Treating `generated_presence` as a deterministic or lip-synchronized avatar workflow.
- Writing the CTA before confirming the avatar and narration path.
- Planning multiple aspect ratios before the hero layout is proven.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
