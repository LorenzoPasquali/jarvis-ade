# Jarvis Desktop Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement each task. Use a worktree before code changes if isolation is needed.

**Goal:** Create a versioned Tauri desktop app shell with a Rust coordinator, TypeScript/React UI, and local SQLite storage.

**Architecture:** The workspace root becomes the Jarvis repository while existing cloned prototypes remain ignored reference folders. The Tauri UI invokes named Rust commands; filesystem and process access stay in the Rust layer.

**Tech Stack:** Tauri 2, Rust, TypeScript/React, Vite, SQLite.

**Spec:** `docs/superpowers/specs/jarvis-orca-cockpit.md`, sections 5, 13, and 16.

**Execution note:** The user authorized continuing this independent foundation while the Orca bridge remains blocked, including manually selected local project roots. `/git/jarvis/.git` is an empty read-only directory in this workspace, not a valid repository; preserve it and defer Git initialization and commits. App files are being developed in the dedicated workspace without committing. The npm registry did not respond during lockfile generation, and the local cache lacks `@tauri-apps/api`; `package-lock.json` remains pending, now including the native dialog dependency.

## Global Constraints

- Ignore `J.A.R.V.I.S/`, `jarvis-local/`, `JarvisExample.mp3`, model files, build output, and local Python environments.
- The Rust command layer is the only app layer that may access project files or spawn subprocesses.
- Tauri capabilities expose only named app operations; do not grant a generic frontend shell command.
- Persist Jarvis conversations and configuration locally; do not persist raw microphone audio.
- Do not store full terminal output until a retention policy is explicitly defined.
- After each task passes its manual acceptance, commit only that task's files; never stage nested clones, the MP3, or model files.

---

### Task 1: Establish the Jarvis repository boundary

**Files:**
- Create: `.gitignore`
- Create: `.git/` via `git init` at `/git/jarvis`
- Include: `docs/superpowers/specs/jarvis-orca-cockpit.md` and `docs/superpowers/plans/*.md`
- Include when it exists: `docs/spikes/orca-session-bridge.md`

**Interfaces:**
- Consumes: the current workspace containing docs and nested reference clones.
- Produces: a Git root for Jarvis docs and future app code, excluding the reference clones and voice sample.

- [x] Add ignore rules for `/J.A.R.V.I.S/`, `/jarvis-local/`, `/JarvisExample.mp3`, `node_modules/`, `target/`, `dist/`, Python caches/virtual environments, and downloaded model directories.
- [ ] Initialize Git at `/git/jarvis` only after confirming `/git/jarvis/.git` is still absent.
- [ ] Confirm the spec and plan docs are visible to Git while nested clones and large voice/model assets remain ignored.
- [ ] Commit `.gitignore` and the Jarvis spec/plan/spike documents as `chore: initialize jarvis workspace`.

**Manual acceptance:** `git status --short` lists only Jarvis docs and new app files; no nested clone or audio/model asset is staged.

### Task 2: Scaffold Tauri 2 with React and TypeScript

**Files:**
- Create: `package.json`
- Create: `package-lock.json`
- Create: `tsconfig.json`
- Create: `vite.config.ts`
- Create: `index.html`
- Create: `src/main.tsx`
- Create: `src/app/App.tsx`
- Create: `src/app/App.css`
- Create: `src-tauri/Cargo.toml`
- Create: `src-tauri/tauri.conf.json`
- Create: `src-tauri/src/main.rs`
- Create: `src-tauri/src/lib.rs`
- Create: `src-tauri/capabilities/default.json`

**Interfaces:**
- Consumes: the approved Tauri/Rust + TypeScript/React architecture.
- Produces: a desktop window that loads `App.tsx` and a Rust backend ready to register named commands.

- [x] Scaffold the Tauri 2 React/TypeScript source layout at `/git/jarvis` without changing either reference clone.
- [x] Set the product name to `Jarvis`, the identifier to `local.jarvis.orca-cockpit`, and the development frontend entry to Vite.
- [x] Keep the initial window and navigation usable without Orca or voice services running.
- [x] Configure capabilities with no arbitrary shell access; grant only commands required by later tasks.
- [ ] Generate `package-lock.json`; npm registry access timed out and the local cache does not contain the required packages.

**Manual acceptance:** the desktop shell opens to a Jarvis page with Projects, Inbox, and Settings navigation and no dependency on network services.

**Manual acceptance status:** pending; the Tauri app has not been launched or built in this environment.

### Task 3: Define shared domain types and safe Tauri command errors

**Files:**
- Create: `src-tauri/src/domain/mod.rs`
- Create: `src-tauri/src/domain/project.rs`
- Create: `src-tauri/src/domain/session.rs`
- Create: `src-tauri/src/domain/inbox_event.rs`
- Create: `src-tauri/src/error.rs`
- Create: `src/shared/types/project.ts`
- Create: `src/shared/types/session.ts`
- Create: `src/shared/types/inbox.ts`
- Modify: `src-tauri/src/lib.rs`

**Interfaces:**
- Produces `ProjectSummary { id: String, name: String, repo_path: String, worktree_path: Option<String>, branch: Option<String>, git_state: GitState, activity: ActivityEvidence }`.
- `GitState { clean: bool, changed_file_count: u32 }`.
- `ActivityState = "working_now" | "needs_reply" | "recent" | "inactive" | "unknown"`.
- `ActivityEvidence { state: ActivityState, source: "orca" | "git" | "manual" | "unknown", observed_at: Option<String> }`.
- Produces `SessionSummary { id: String, project_id: String, terminal_id: Option<String>, claude_session_id: Option<String>, agent: String, state: SessionState, last_seen_at: Option<String> }`.
- `SessionState` serializes as `working | needs_reply | completed | unknown`.
- Produces `InboxEvent { id, session_id, kind, text, created_at }`, where `kind` is `output | approval | user_message | assistant_message | state_changed`.
- The TypeScript files export matching `ProjectSummary`, `GitState`, `ActivityState`, `ActivityEvidence`, `SessionSummary`, `SessionState`, and `InboxEvent` types.
- Rust errors serialize to `{ code: string, message: string }` without leaking environment variables or credentials.

- [x] Add Rust serializable types and matching TypeScript interfaces with identical field names and state variants.
- [x] Add error variants for `OrcaUnavailable`, `ProjectNotFound`, `PathOutsideProject`, `PermissionRequired`, and `OperationFailed`.
- [x] Register a harmless `get_app_version` command as the first typed UI-to-Rust call.

**Manual acceptance:** the UI can invoke `get_app_version` and display a typed success or a sanitized error.

**Manual acceptance status:** pending; the Tauri app has not been launched or typechecked in this environment.

### Task 4: Add local SQLite storage and persistence boundaries

**Files:**
- Create: `src-tauri/src/store/mod.rs`
- Create: `src-tauri/src/store/migrations.rs`
- Create: `src-tauri/src/store/repository.rs`
- Create: `src-tauri/src/commands/settings.rs`
- Create: `src/shared/api/settings.ts`
- Modify: `src-tauri/src/lib.rs`

**Interfaces:**
- `Store::open(app_data_dir) -> Result<Store, AppError>`.
- Store tables: `projects`, `sessions`, `preferences`, `chat_messages`, and `inbox_events`.
- `save_chat_message(role, body, created_at)` and `list_chat_messages(limit)` persist only text messages owned by Jarvis.
- `clear_chat_history() -> Result<(), AppError>` and frontend `clearChatHistory() -> Promise<void>`.
- No table stores raw microphone audio or unbounded terminal output.

- [x] Open SQLite under the Tauri application data directory and add versioned migrations.
- [x] Persist user/Jarvis chat messages, project mappings, session mappings, and preferences.
- [x] Add `clear_chat_history` so the user can delete the Jarvis conversation history.
- [x] Keep full terminal scrollback in memory only; store a selected inbox excerpt only when the adapter supplies a bounded event.

**Manual acceptance:** configuration and Jarvis text history survive app restart, and the user can clear the stored chat history.

**Manual acceptance status:** pending; persistence has not been exercised in the desktop app.
