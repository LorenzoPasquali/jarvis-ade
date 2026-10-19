# Orca Session Bridge Spike

**Status:** blocked at runtime discovery from the agent command context  
**Date:** 2026-10-17

## Scope

Check whether supported Orca interfaces can discover projects and sessions, read and route messages, and resume a stopped Claude Code session. This spike uses only the selected Orca CLI and its matching guide. No project or session content was read.

## CLI and documented command surface

- Selected executable for this Orca-managed terminal: `orca`, per the `orca-cli` skill. The installed `orca` shim delegates to the same `orca-ide` AppImage launcher.
- Version: `1.4.229` (`orca --version`).
- Matching guide: `orca skills get orca-cli --json` succeeded.
- Documented discovery commands:
  - `orca repo list --json`
  - `orca worktree list --repo id:<repoId> --json`
  - `orca worktree ps --json`
  - `orca worktree current --json`
  - `orca terminal list --worktree <selector> --json`
- Documented terminal commands:
  - `orca terminal show --terminal <handle> --json`
  - `orca terminal read --terminal <handle> --json`
  - `orca terminal send --terminal <handle> --text <text> --enter --json`
  - `orca terminal wait --terminal <handle> --for tui-idle --timeout-ms <ms> --json`
  - `orca terminal close --terminal <handle> --json`

These commands are documented by the installed guide; their behavior against a running Orca runtime has not been confirmed in this spike.

The guide documents creating a terminal and reading, sending to, waiting on, or closing live terminals. It does not document an Orca command for reopening a stopped terminal/session. Resuming Claude Code with `claude --resume <session-id>` remains an unverified candidate and was not attempted.

## Runtime check

From this agent command context, `orca repo list --json`, `orca worktree ps --json`, and `orca worktree current --json` exited with code `1`. Each returned:

```json
{"ok":false,"id":"local","error":{"code":"runtime_unavailable","message":"Could not connect to the running Orca app. Restart Orca and try again."}}
```

An earlier attempt with `orca-ide` returned the same `runtime_unavailable` error. `orca open --json` had also returned `runtime_open_timeout`. The user confirmed the Orca interface is open and is the current conversation surface; these failures only establish that this agent command context cannot connect to it. They do not prove that Orca is closed or that the user's desktop process has the same restriction.

After Jarvis was launched locally, a read-only GUI inspection attempt with `orca-ide computer list-apps --json` returned the same `runtime_unavailable` error. No app/window contents could be inspected through the supported computer interface from this context. Jarvis uses `orca` when launched with Orca-managed environment variables and `orca-ide` otherwise; the result in the user's desktop process is still pending.

## Results and gate

- Project, worktree, and terminal/session records: **not discovered**; no identifiers or project paths were collected.
- Terminal read, message routing, second-session isolation, and stopped-session resume: **not exercised**.
- Session-control gate: **blocked on the supported CLI-to-runtime connection**. The Orca interface is open, but the selected CLI cannot connect from this command context. The evidence is insufficient for a `go` decision or for revising the adapter design.

Resume this spike only after the CLI-to-runtime connection path is resolved. Continue with documented read-only discovery first, then use only a disposable worktree/session for send and resume checks.
