# Local Project Access and Command Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement each task after the desktop foundation exists.

**Goal:** Let Jarvis inspect configured project roots and run directly requested commands only after showing the exact action for confirmation.

**Architecture:** Rust resolves configured root IDs, canonicalizes every requested path, obtains Git/file evidence, and mediates process execution. The frontend receives bounded results and cannot request arbitrary shell access directly.

**Tech Stack:** Rust filesystem/process APIs, Git CLI, `rg` CLI for on-demand search, Tauri file picker/dialog, TypeScript/React.

**Spec:** `docs/superpowers/specs/jarvis-orca-cockpit.md`, sections 2, 13, 14, and 17.

**Execution status (2026-10-17):** Tasks 1–4 have implementation source in place. Task 1 supports manual folder selection; Orca-based import remains gated on the Orca bridge. Git activity is read only and refuses to inspect a repository whose Git root is above the configured folder. File reads and searches require an explicitly registered root and return bounded local excerpts. Direct commands use a short-lived server-side preview ID and run only after confirmation; no command has been executed through the Jarvis UI. Build validation now passes: `npm run build`, `cargo check --manifest-path src-tauri/Cargo.toml`, and `cargo build --manifest-path src-tauri/Cargo.toml` all succeeded. Rust emitted three dead-code warnings for `InboxEventKind`, `InboxEvent`, and `AppError::OrcaUnavailable`. The missing Tauri icon was generated from the UI's existing orbit mark, and `get_activity` now borrows its resolved path at all four `run_git` call sites. Launching `npm run tauri dev` from the assistant sandbox remains blocked because Vite cannot bind `127.0.0.1:1420` (`EPERM`); `orca-ide terminal list` also returned `runtime_unavailable`. Desktop launch and manual acceptance must be confirmed from the user's local terminal.

## Global Constraints

- Only roots explicitly added by the user can be read.
- Canonical resolved paths must remain under a configured root, including symlink resolution.
- No full-disk scan, vector index, or implicit upload to Claude.
- Direct commands require confirmation showing program/command, arguments, and working directory.
- Use argument arrays and a controlled process API; do not interpolate untrusted text into a shell command.
- Claude Code retains its own file and command permission flow.
- After each task passes its manual acceptance, commit only that task's files.

---

### Task 1: Add configured project roots

**Files:**
- Create: `src-tauri/src/project_access/mod.rs`
- Create: `src-tauri/src/project_access/roots.rs`
- Create: `src-tauri/src/commands/project_roots.rs`
- Create: `src/shared/api/projectRoots.ts`
- Create: `src/features/settings/ProjectRoots.tsx`
- Modify: `src-tauri/src/store/repository.rs`
- Modify: `src-tauri/src/lib.rs`

**Interfaces:**
- `add_project_root(path: String) -> Result<ProjectRoot, AppError>`; Rust canonicalizes the selected folder.
- `list_project_roots() -> Result<Vec<ProjectRoot>, AppError>`.
- `remove_project_root(project_id: String) -> Result<(), AppError>`.

- [x] Use a native folder picker and persist the selected canonical directory.
- [x] Reject missing, non-directory, or duplicate roots with a clear UI message.
- [ ] Import paths discovered from Orca; selecting a path manually is implemented, but Orca import remains blocked by the bridge spike.
- [x] Provide a confirmed remove control without deleting project files.

**Manual acceptance:** after restart, configured roots remain listed, and removing a root does not alter its files.

### Task 2: Add evidence-based Git activity

**Files:**
- Create: `src-tauri/src/project_access/git.rs`
- Create: `src-tauri/src/commands/project_activity.rs`
- Modify: `src/app/App.tsx`
- Modify: `src/shared/types/project.ts`
- Modify: `src-tauri/src/domain/project.rs`

**Interfaces:**
- `get_git_activity(project_id: String) -> Result<GitActivity, AppError>`.
- `GitActivity { availability, branch, changed_paths, recent_commits, diff_summary, clean, observed_at_unix_ms }`.

- [x] Run fixed Git argument arrays with the configured repo path as `current_dir`.
- [x] Collect branch, bounded short status, diff summary, and recent commit subjects without reading file contents wholesale.
- [x] Render branch/status/commit evidence and distinguish clean, changed, non-Git, out-of-scope, and unavailable states.
- [x] Never infer active work from file modification time alone.

**Manual acceptance:** a clean repo, a dirty worktree, and a missing Git repo each produce distinct and understandable project status.

### Task 3: Add bounded on-demand file read/search

**Files:**
- Create: `src-tauri/src/project_access/files.rs`
- Create: `src-tauri/src/commands/project_files.rs`
- Create: `src/shared/api/projectFiles.ts`
- Create: `src/features/projects/ProjectContextPanel.tsx`
- Modify: `src-tauri/src/lib.rs`

**Interfaces:**
- `read_project_file(project_id: String, relative_path: String) -> Result<FileExcerpt, AppError>`.
- `search_project(project_id: String, query: String, limit: u32) -> Result<Vec<FileExcerpt>, AppError>`.
- `FileExcerpt { relative_path, start_line, text }`.

- [x] Resolve requested files under the registered project root and reject traversal or symlink escapes.
- [x] Search only text files while respecting ignored directories and fixed result/byte limits.
- [x] Start with `AGENTS.md`, `README`, recent Git changes, and user-selected files; do not recursively index the full repository.
- [x] Display source paths and line numbers for every excerpt shown in the local context panel.
- [x] Keep retrieved excerpts local; sending any excerpt to a Claude session requires an explicit preview/action.

**Manual acceptance:** reading a file inside a configured root works; `../` traversal, outside absolute paths, and symlinks escaping the root are rejected.

### Task 4: Add direct command preview and confirmation

**Files:**
- Create: `src-tauri/src/commands/command_runner.rs`
- Create: `src-tauri/src/project_access/command_runner.rs`
- Create: `src/shared/api/commands.ts`
- Create: `src/features/commands/CommandApprovalDialog.tsx`
- Create: `src/features/commands/CommandOutput.tsx`
- Modify: `src-tauri/src/lib.rs`

**Interfaces:**
- `CommandRequest { project_id: String, command_line: String }`; command text comes from a dedicated composer populated by text or corrected voice transcription. Working directory is resolved from the project, never supplied by the UI.
- `CommandPreview { confirmation_id: String, project_id: String, program: String, args: Vec<String>, working_directory: String, expires_at_unix_ms: u64 }`.
- `preview_command(request: CommandRequest) -> Result<CommandPreview, AppError>`.
- `run_confirmed_command(confirmation_id: String) -> Result<CommandResult, AppError>`; Rust retrieves the exact preview bound to the ID.
- `CommandResult { exit_code: Option<i32>, stdout_excerpt: String, stderr_excerpt: String, truncated: bool, timed_out: bool }`.

- [x] Render the exact program, argument list, and working directory before execution.
- [x] Parse the composer text into a program and argument list without shell expansion; reject pipes, redirections, substitutions, and unsupported syntax.
- [x] Never pass the original command text to a shell. A future Claude-suggested command may populate the composer but cannot bypass preview or confirmation.
- [x] Bind confirmation to a short-lived, one-use ID holding the exact preview; re-check the registered directory before execution.
- [x] Spawn with the argument vector and project working directory; do not use a shell implicitly.
- [x] Bound displayed output and mark truncated output; do not persist full command output by default.
- [ ] Require voice-dictated commands to pass through editable transcript and this same approval dialog; voice input is not implemented yet.

**Manual acceptance:** cancel runs nothing; confirmation runs exactly the displayed command in the displayed project directory; changing the payload invalidates confirmation.
