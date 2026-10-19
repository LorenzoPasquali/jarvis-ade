# Orca Project Catalog and Inbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement each task after the bridge spike is marked `go`.

**Goal:** Show Orca projects and existing Claude sessions in a central inbox and route each response to its selected session.

**Architecture:** A Rust `OrcaAdapter` calls only documented Orca CLI operations and converts them to Jarvis domain types. The UI presents one inbox view but keeps a separate thread per project/worktree/session.

**Tech Stack:** Rust process API, Orca CLI, Tauri commands/events, TypeScript/React, SQLite.

**Spec:** `docs/superpowers/specs/jarvis-orca-cockpit.md`, sections 2, 3, 5, 11, and 12.

## Global Constraints

- Begin implementation only if `docs/spikes/orca-session-bridge.md` records the operation as supported.
- Do not access Orca's database or undocumented files.
- Never route by project name alone; use stable Orca terminal/session IDs.
- Keep session threads isolated and show `unknown` when status evidence is insufficient.
- Do not start a replacement session when an active session is already mapped to the project/worktree.
- After each task passes its manual acceptance, commit only that task's files.

---

### Task 1: Implement the version-checked Orca CLI wrapper

**Files:**
- Create: `src-tauri/src/orca/mod.rs`
- Create: `src-tauri/src/orca/cli.rs`
- Create: `src-tauri/src/orca/output.rs`
- Modify: `src-tauri/src/lib.rs`

**Interfaces:**
- `OrcaCli::resolve() -> Result<OrcaCli, AppError>` chooses the executable once from configured path/session environment.
- `OrcaCli::run(args: &[OsString]) -> Result<CommandOutput, AppError>` passes arguments without shell interpolation.
- `CommandOutput { stdout, stderr, exit_code }` preserves errors for user-visible diagnostics while redacting secrets.

- [ ] Store the selected executable in app configuration; do not fall through between `orca-ide`, `orca-dev`, or other binaries after an error.
- [ ] Implement argument-array process execution and a timeout/cancellation path.
- [ ] Decode JSON only for commands the matched guide marks as JSON-capable; keep plain output explicitly typed.

**Manual acceptance:** unavailable Orca produces a clear `OrcaUnavailable` state and does not prevent the rest of Jarvis from opening.

### Task 2: Discover configured repos and worktrees

**Files:**
- Create: `src-tauri/src/orca/projects.rs`
- Create: `src-tauri/src/commands/projects.rs`
- Create: `src/shared/api/projects.ts`
- Create: `src/features/projects/ProjectList.tsx`
- Create: `src/features/projects/ProjectCard.tsx`
- Modify: `src/app/App.tsx`
- Modify: `src-tauri/src/lib.rs`

**Interfaces:**
- `list_projects() -> Result<Vec<ProjectSummary>, AppError>`.
- `get_project(project_id: String) -> Result<ProjectSummary, AppError>`.
- TypeScript API exposes `listProjects()` and `getProject(projectId)`.

- [ ] Parse the documented Orca repo/worktree output and normalize stable identifiers and filesystem paths.
- [ ] Merge duplicate repo/worktree records without conflating separate worktrees.
- [ ] Render branch, worktree path, Git activity if available, and the evidence used to classify activity.
- [ ] Display an empty state for no configured projects and an offline state when Orca is unavailable.

**Manual acceptance:** projects and worktrees shown in Orca appear separately with matching names and paths; missing activity is shown as unknown, not fabricated.

### Task 3: Discover and observe terminal sessions

**Files:**
- Create: `src-tauri/src/orca/sessions.rs`
- Create: `src-tauri/src/commands/sessions.rs`
- Create: `src/shared/api/sessions.ts`
- Create: `src/features/inbox/InboxPage.tsx`
- Create: `src/features/inbox/SessionThreadList.tsx`
- Create: `src/features/inbox/SessionThread.tsx`
- Modify: `src/app/App.tsx`
- Modify: `src-tauri/src/lib.rs`

**Interfaces:**
- `list_sessions(project_id: Option<String>) -> Result<Vec<SessionSummary>, AppError>`.
- `read_session_output(terminal_id: String, max_bytes: usize) -> Result<String, AppError>`.
- `wait_for_session_event(terminal_id: String, timeout_ms: u64) -> Result<Option<InboxEvent>, AppError>`.

- [ ] Map every session to its Orca project/worktree and stable terminal/session IDs.
- [ ] Poll or wait using only the supported mechanism discovered in the spike; throttle polling and stop it when the app exits.
- [ ] Display a thread per session and keep the selected thread's output separate from other sessions.
- [ ] Mark state as `unknown` unless the CLI provides a structured state or an explicit user interaction establishes it.

**Manual acceptance:** two disposable sessions from different worktrees appear independently and output from one never appears under the other.

### Task 4: Route messages and resume stopped sessions

**Files:**
- Modify: `src-tauri/src/orca/sessions.rs`
- Create: `src-tauri/src/commands/inbox.rs`
- Create: `src/shared/api/inbox.ts`
- Modify: `src/features/inbox/SessionThread.tsx`
- Modify: `src-tauri/src/store/repository.rs`

**Interfaces:**
- `send_to_session(terminal_id: String, message: String) -> Result<(), AppError>`.
- `resume_session(project_id: String, claude_session_id: String) -> Result<SessionSummary, AppError>` only if the spike verified the resume route.
- `append_chat_message(session_id, role, body, created_at)` stores Jarvis-thread text separately per session.

- [ ] Require an explicit selected session before sending a response; if voice/text target is ambiguous, return a target-selection state without sending.
- [ ] Route by terminal ID, not display label, and persist the association to the Jarvis conversation thread.
- [ ] Add resume action only for a stopped session with a known Claude session ID and no active terminal mapped to it.
- [ ] Surface Claude/Orca approval prompts as pending inbox events; never auto-approve them.

**Manual acceptance:** replying to session A changes only session A; resuming a stopped disposable session preserves its prior conversation.
