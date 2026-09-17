# FactForge free runner

This public GitHub Actions repository runs FactForge production without a paid
text-generation, speech, or video-rendering API. It uses a local Qwen model,
Piper text-to-speech, original procedural artwork, and FFmpeg.

The default series is an original motion comic starring Mali, a fictional Thai
woman in her mid-twenties. Her long dark hair, teal apron, gold jasmine pin, and
warm practical personality remain consistent in every episode. Each story uses
animated comic frames, facial and arm poses, moving props, action lines, camera
pans, scene-matched narration, and timed captions. No real person's likeness or
existing franchise character is used.

The factual cooking and cultural details still pass the two-source evidence gate.
The story itself is clearly disclosed as original fiction. Before upload, a motion
gate samples every scene and stops the job if the rendered comic is effectively
static. Removing the old heavy presenter model also makes scheduled runs much
faster and prevents static-host failures.

The workflow authenticates to FactForge with GitHub Actions OIDC. There are no
repository secrets to add: the Google refresh token stays encrypted in the
FactForge Site, and the runner never receives it.

## Setup

1. Create a **public** GitHub repository named `factforge-free-runner` under
   `aafiyaaservicesltd-bit`.
2. Put this directory's files at the repository root and use `main` as the
   default branch.
3. The first push starts **FactForge free runner** automatically. If GitHub asks,
   open **Actions**, enable workflows, and use **Run workflow** once.
4. Return to FactForge. The free runner should turn green after its heartbeat.

The scheduled workflow checks every four hours and completes at most one video
per run. Public uploads require Autopilot to be armed. Explicitly queued private
tests can run while Autopilot is paused, so quality can be reviewed safely.
GitHub may delay scheduled runs, and GitHub automatically disables
scheduled workflows in public repositories after prolonged repository
inactivity. A missing heartbeat makes FactForge pause safely; it never falls
back to a billable provider.

Standard GitHub-hosted runners are currently free for public repositories.
GitHub's terms and limits can change, so confirm the repository remains public
and review GitHub's Actions billing page periodically.

## Security boundaries

- OIDC audience must be `factforge-ai`.
- FactForge accepts only the exact public repository, default branch `main`,
  and GitHub's signed token.
- MP4 uploads are limited to 95 MB and stored only until YouTube accepts them.
- FactForge re-checks the Autopilot switch immediately before publishing.
- A failed safety, source, render, or upload check pauses the job visibly.
