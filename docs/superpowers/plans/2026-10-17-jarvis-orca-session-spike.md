# Orca Session Bridge Feasibility Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` for this spike. Operate only through the version-matched Orca CLI guide.

**Goal:** Establish whether Jarvis can discover, read, message, and resume existing Orca/Claude sessions using supported interfaces.

**Architecture:** Treat the Orca CLI as the adapter boundary. First record the CLI's supported operations, then exercise them against a disposable project/session and document the exact IDs and state transitions.

**Tech Stack:** `orca-ide` or the session-resolved Orca CLI executable, Claude Code CLI, temporary project directory, Markdown results record.

**Spec:** `docs/superpowers/specs/jarvis-orca-cockpit.md`, sections 5, 8, and 12.

**Execution status:** Task 1 recorded; Tasks 2–4 are pending a reachable Orca runtime. See `docs/spikes/orca-session-bridge.md`.

## Global Constraints

- Follow `orca-cli` skill instructions to select one executable and fetch its matching guide.
- Never use bare `orca` on Linux outside an Orca-managed terminal.
- Do not guess unsupported commands or inspect Orca's internal database.
- Use a disposable worktree/session for send and resume experiments; do not send probe prompts to an active project session.
- Do not authorize file edits or arbitrary shell commands in the disposable Claude session.
- Record exact command output and errors without storing credentials or private project content.

---

### Task 1: Record the installed Orca command surface

**Files:**
- Create: `docs/spikes/orca-session-bridge.md`

**Interfaces:**
- Consumes: the installed Orca executable and its version-matched `orca-cli` guide.
- Produces: a record of executable, version, documented project/worktree/terminal operations, and capability gaps.

- [x] Follow the `orca-cli` skill to resolve the executable once and fetch `skills get orca-cli --json`.
- [x] Record the installed version and the documented commands for project/worktree listing, terminal read, wait, send, and opening a stopped session.
- [x] If the CLI guide or runtime is unavailable, record its exact error and stop this spike instead of switching to an unverified executable.

**Manual acceptance:** `docs/spikes/orca-session-bridge.md` identifies the exact supported commands and clearly separates confirmed behavior from assumptions.

### Task 2: Check project and session discovery

**Files:**
- Modify: `docs/spikes/orca-session-bridge.md`

**Interfaces:**
- Consumes: the documented read-only Orca commands from Task 1.
- Produces: sample sanitized records mapping repo/worktree to terminal/session IDs.

- [ ] Run the documented read-only commands for projects, worktrees, and terminal sessions.
- [ ] Confirm whether outputs expose stable identifiers, working directories, activity, and terminal IDs needed by the inbox.
- [ ] Record fields that are missing or only inferred; do not mark a session as waiting without evidence.

**Manual acceptance:** at least one existing project/worktree can be mapped to its available session/terminal identifiers, or the report names the missing fields.

### Task 3: Check reading and message routing on a disposable session

**Files:**
- Modify: `docs/spikes/orca-session-bridge.md`

**Interfaces:**
- Consumes: a disposable Orca session and documented terminal read/send/wait commands.
- Produces: confirmed round-trip procedure and limitations for terminal output/message routing.

- [ ] Create or select an empty disposable worktree and start a Claude session with a harmless prompt that requests a fixed text response and no file/system changes.
- [ ] Read the terminal output through the documented Orca interface and save only sanitized evidence.
- [ ] Send a harmless follow-up to that same terminal, wait for completion, and confirm the response returns to the same terminal/session.
- [ ] Confirm a second disposable session remains untouched when sending to the first.

**Manual acceptance:** the report identifies the exact project, worktree, terminal, and session IDs used and confirms whether a response can be routed unambiguously.

### Task 4: Check stopped-session resume and decide the gate

**Files:**
- Modify: `docs/spikes/orca-session-bridge.md`
- Modify: `docs/superpowers/specs/jarvis-orca-cockpit.md` only if the evidence changes an approved assumption.

**Interfaces:**
- Consumes: the disposable session ID and documented Claude Code resume mechanism.
- Produces: a resume result and an explicit go/revise decision for session control.

- [ ] Stop the disposable session cleanly and resume it by its recorded session ID using the documented CLI mechanism.
- [ ] Confirm that the resumed process has the expected prior conversation and correct working directory.
- [ ] Mark the session-control gate `go` only if discovery, reading, sending, routing, and resume outcomes are recorded; otherwise record the supported subset and revise the subsystem design.

**Manual acceptance:** the spike ends with one of two concrete outcomes: `go` for the verified supported operations, or a documented revision path that does not rely on guessed/internal Orca behavior.
