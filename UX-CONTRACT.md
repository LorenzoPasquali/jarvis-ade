# Jarvis UI Behavior Contract

This contract covers the local desktop app and its conversation-first workflow. Visual tokens and rationale live in [DESIGN.md](DESIGN.md).

## Locale and document titles

- Owned interface copy is Brazilian Portuguese (`pt-BR`).
- The initial route is `Conversa`. The main view title and document title follow the selected route: `Projetos — Jarvis`, `Conversa — Jarvis`, or `Configurações — Jarvis`.
- Dates and times use `America/Sao_Paulo` once timestamps are shown. Agent IDs, branch names, and paths are preserved verbatim.

## Navigation

- The persistent navigation exposes Conversa, Projetos, and Configurações.
- Each item is a semantic button with a visible name; the selected item exposes `aria-current="page"`.
- Changing routes keeps the application shell mounted and updates the page and document title.
- A route stays usable when Orca or voice services are unavailable.

## Projects and inbox empty states

- Do not show sample projects, sessions, activity counts, unread badges, or agent replies.
- Until an adapter is connected, state plainly that the Orca catalog or sessions are not connected.
- Project reading is limited to paths the user will configure in a later task; the shell never scans the disk.
- If agent state is unavailable, do not label an agent as working or waiting.

## Central conversation

- The conversation is the initial route and is the place where local project answers and future agent replies appear.
- The Jarvis can answer deterministic questions using configured project roots and Git status. It must explain that Git activity does not prove that an agent is working.
- Free-form messages are stored locally. Until a verified Orca session target is selected and the routing adapter is implemented, the UI must say that no agent received the message.
- The Orca status check uses the documented read-only `repo list --json` command. A successful check means only that the CLI can reach the Orca runtime; it does not mean sessions are being read or messages can be routed.
- The composer accepts text offline. Push-to-talk records only after an explicit click, sends the temporary clip to local Whisper, and fills an editable transcript; it never submits automatically.
- Raw recording data is deleted after transcription. Do not offer response playback through the generic system voice. Pocket TTS setup is a user-triggered, one-time download in Configurações; because cloning weights are gated, explain the Hugging Face approval and accept a read token only in memory for setup, never persist it. Show subprocess diagnostics on failure. The voice is tested there before automatic reading is enabled. The app uses offline mode for speech generation and also provides a manual “Ouvir resposta” action.
- If microphone permission or local model files are unavailable, keep text mode usable and show a recoverable local error. Do not fall back to remote speech services.

## Local history

- Jarvis-owned text messages are stored locally. Raw microphone audio and terminal scrollback are not stored.
- Clearing history requires an app-owned confirmation that names the action and offers a clear cancel path.
- If clearing fails, retain the current UI state and show a recoverable, sanitized error.

## Errors and accessibility

- Rust commands return `{ code, message }` with user-safe messages; raw filesystem, database, or environment details stay out of UI errors.
- Interactive controls use native buttons and inputs, visible keyboard focus, and localized accessible names.
- Motion respects `prefers-reduced-motion`.
- Empty, unavailable, and error states remain distinct.
