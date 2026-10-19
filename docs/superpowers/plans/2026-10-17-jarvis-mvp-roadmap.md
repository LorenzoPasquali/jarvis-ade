# Jarvis Orca Cockpit Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this roadmap task by task. Use `superpowers:using-git-worktrees` before code work that needs isolation. Do not delegate unless the user asks for it.

**Goal:** Build a local desktop Jarvis that shows the user's Orca projects and Claude Code sessions in one inbox, while keeping each session context independent.

**Architecture:** Tauri 2 provides the desktop shell, a TypeScript/React UI, and a Rust coordinator for project access, Orca commands, permission checks, and SQLite. Local voice runs behind a Python worker interface; online Claude Code sessions remain the user's existing Orca/Claude processes.

**Tech Stack:** Tauri 2, Rust, TypeScript/React, SQLite, and a Python STT/TTS worker after local compatibility checks.

**Spec:** `docs/superpowers/specs/jarvis-orca-cockpit.md`

## Global Constraints

- Keep each agent's conversation and project context separate.
- Use supported Orca interfaces; do not depend on Orca's internal database or undocumented formats.
- Restrict project reads to configured roots and avoid indexing the whole disk.
- Show exact command and working directory and ask before Jarvis executes a shell command.
- Preserve Claude Code's own permission prompts; do not bypass them.
- Keep project reading, project catalog, Jarvis history, and voice processing local.
- Do not send project files to Claude automatically.
- Keep the app usable by text if local voice models are unavailable.
- Do not add wake word, unattended shell execution, automatic agent-to-agent forwarding, or a full Orca clone to the MVP.
- After each task passes its manual acceptance, commit only the task files; never stage reference clones, audio, or model assets.

---

## Plan files and order

1. [Orca session bridge feasibility](2026-10-17-jarvis-orca-session-spike.md) — first gate; confirm read/send/resume behavior without touching a live work session.
2. [Desktop foundation](2026-10-17-jarvis-desktop-foundation.md) — initialize the Jarvis repository root, scaffold Tauri, and add local storage and app shell.
3. [Orca project catalog and inbox](2026-10-17-jarvis-orca-inbox.md) — list projects/sessions, observe events, and route messages.
4. [Local project access and commands](2026-10-17-jarvis-project-access.md) — read bounded project context and execute user-confirmed commands.
5. [Offline voice](2026-10-17-jarvis-offline-voice.md) — connect push-to-talk/STT/TTS and evaluate the supplied voice sample.

## Status after first local launch (2026-10-17)

- Desktop foundation, configured project roots, bounded file access, and Git activity are implemented and build locally.
- The app now opens into a central conversation, answers deterministic questions from configured folders/Git, and probes Orca through its documented read-only CLI command.
- Push-to-talk uses cached Whisper in offline mode; the edited transcript stays in the composer until the user submits it. Response playback was removed after the user rejected the generic system voice.
- With the corrected reference transcript, OmniVoice needed 102.9 seconds to generate 4.1 seconds of audio on CPU. Keep it experimental; do not use generic system speech as fallback.
- The Orca session bridge is still unimplemented and its CLI calls return `runtime_unavailable` in the assistant's execution context even though the Orca UI is open. Do not route messages or import sessions until a desktop-runtime connection succeeds and the disposable-session spike verifies read/send.

## Dependency order

```text
Orca bridge spike ────────────────────────> Orca catalog and inbox
desktop foundation ───────────────────────> Orca catalog and inbox
                 ├────────────────────────> manually configured project roots and Git activity
                 ├────────────────────────> bounded file reads and confirmed commands
                 └────────────────────────> offline voice
```

The Orca spike remains the gate for session control and importing projects from Orca. The user authorized manually configured local project roots while the CLI-to-runtime connection is unresolved; this does not inspect Orca internals or grant broad disk access. If supported Orca operations cannot observe or message existing sessions, pause that subsystem and revise the SPEC before building an alternative. The voice plan can proceed after the app foundation, but the Python worker and model choices depend on the target machine.

## Manual acceptance gate for the MVP

- Two sessions in different projects appear separately, with their project/worktree labels intact.
- A reply selected for one session reaches only that session.
- An uncertain terminal state is displayed as uncertain.
- Project status and file context are derived from configured local paths and Git/Orca evidence.
- A direct shell action shows the exact command and working directory before the user confirms it.
- Push-to-talk creates an editable transcript, and local TTS can read the selected message.
- The app retains its local Jarvis history and remains usable by text if voice is unavailable.
