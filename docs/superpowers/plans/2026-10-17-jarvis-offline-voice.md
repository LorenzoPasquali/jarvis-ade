# Offline Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan after the desktop foundation exists.

**Goal:** Add local push-to-talk input and local spoken responses, with an isolated evaluation path for the supplied Jarvis voice sample.

**Architecture:** The UI captures explicit push-to-talk audio through `MediaRecorder` and displays an editable transcript. Rust keeps the raw clip in the app cache only while converting/transcribing it through offline Whisper; the clip is deleted afterward. Pocket TTS runs in a persistent local Python worker, uses the provided Jarvis MP3 for voice conditioning, and generates Portuguese audio that the WebView plays locally. A user-triggered setup action installs the CPU package and downloads model weights once; the running app never downloads speech assets and forces offline mode during inference. Generic system speech remains removed.

**Tech Stack:** Rust process management, WebView microphone capture/playback, Python `transformers`/Whisper from the installed OmniVoice environment, Pocket TTS in an app-managed Python environment, and local TTS evaluation.

**Spec:** `docs/superpowers/specs/jarvis-orca-cockpit.md`, sections 6, 15, 16, and 17.

## Global Constraints

- Voice processing remains local; no remote STT/TTS service.
- Start with user-triggered push-to-talk; no wake word or always-listening microphone.
- Keep the user-visible transcript editable before routing it to an agent.
- Never route a response when multiple agents await and no target is selected.
- Do not store raw microphone audio; only persist text that becomes part of the Jarvis conversation.
- Existing benchmark results in `jarvis-local/benchmarks/` are references from a Windows RTX 3050 environment, not a guarantee for the target machine.
- Do not download models or contact speech services during normal app startup; the only download path is the explicit “Preparar voz Jarvis” action in Settings.
- After each task passes its manual acceptance, commit only that task's files.

---

### Task 1: Define local speech processing

**Files:**
- Create: `voice-worker/transcribe.py`
- Create: `src-tauri/src/voice/mod.rs`
- Create: `src-tauri/src/voice/worker.rs`
- Modify: `src-tauri/src/lib.rs`

**Interfaces:**
- Tauri accepts bounded audio bytes and a MIME type, returns transcript text, and deletes the source and converted files.
- The Python worker uses only the cached Whisper checkpoint and emits one JSON object on stdout.
- Rust exposes `transcribe_audio`.

- [x] Parse the local JSON transcription result; keep model logs separate from stdout.
- [x] Start model processing only after push-to-talk ends; set offline mode and do not download missing weights.
- [x] Convert the temporary clip to 16 kHz mono WAV in the app cache and delete both temporary files after processing.
- [x] Bound audio size, conversion time, and model time.

**Manual acceptance:** malformed or unavailable worker responses surface a recoverable voice error while the main app remains open.

### Task 2: Add push-to-talk and transcript review

**Files:**
- Create: `src/shared/api/voice.ts`
- Modify: `src/features/inbox/InboxPage.tsx`
- Modify: `src-tauri/src/commands/voice.rs`
- Modify: `src-tauri/src/lib.rs`

**Interfaces:**
- `transcribe_local_audio(audioBytes: number[], mimeType: string) -> Promise<string>`.
- The UI owns capture and transcript review; it only stores the transcript after the user presses Send.

- [x] Add explicit microphone control and recoverable permission errors.
- [x] Show recording/transcribing states and put the transcript in the editable conversation composer.
- [x] Keep transcription separate from Send; the user reviews and submits it explicitly.
- [ ] Confirm capture and microphone permission in the user's desktop runtime.

**Manual acceptance:** a spoken reply appears as editable text and is not sent until the user submits it.

### Task 3: Local Pocket TTS playback with the supplied reference

**Files:**
- Modify: `src-tauri/src/commands/voice.rs`
- Create: `src-tauri/src/voice/tts.rs`
- Create: `voice-worker/pocket_tts.py`
- Modify: `src/features/inbox/InboxPage.tsx`
- Modify: `src/app/App.tsx`
- Bundle: `src-tauri/resources/jarvis-reference.mp3`

**Interfaces:**
- `prepare_local_speech(token?) -> SpeechStatus` runs only when the user clicks the setup action; it installs CPU-only Pocket TTS, fetches gated Portuguese weights using an ephemeral Hugging Face read token, reads the bundled MP3 directly and exports the voice state. The token is not persisted.
- `speak_local_text(text) -> Vec<u8>` sends text to a persistent worker running with `HF_HUB_OFFLINE=1`; generated WAV bytes play in the desktop WebView.
- Every assistant response has a manual “Ouvir resposta” control. After setup, automatic reading can be toggled in the conversation composer.

- [x] Remove the generic system speech commands and playback buttons after the user reported robotic, broken audio.
- [x] Add a one-time, explicit setup flow for Pocket TTS in Portuguese and the bundled reference sample.
- [x] Add a persistent, offline-only inference worker, a test-voice button, per-message playback and automatic-speech control.
- [ ] Complete first-run model setup and let the user judge the generated sample and latency on the desktop machine.

**Manual acceptance:** prepare the local model in Settings, listen to the reference-conditioned sample, and confirm speech quality/latency before leaving automatic speech enabled.

### Task 4: Evaluate OmniVoice against the supplied reference

**Files:**
- Create: `docs/spikes/jarvis-voice-evaluation.md`
- Modify: `voice-worker/transcribe.py` only if the local speech pipeline needs adjustment.

**Interfaces:**
- Consumes: `/git/jarvis/JarvisExample.mp3` and OmniVoice under `/git/FERRAMENTAS-LOCAL/OmniVoice`.
- Produces: a local comparison of offline availability and first-generation latency, plus a generated sample for the user's perceptual review.

- [x] Inspect OmniVoice's local install/launch requirements without copying its repository into the app.
- [x] Generate a short, non-project phrase offline using the reference voice and corrected reference transcript.
- [x] Record target-machine OS/hardware and first-audio latency in `docs/spikes/jarvis-voice-evaluation.md`.
- [x] Defer OmniVoice as interactive output because CPU synthesis does not keep pace with speech; retain the sample for user review.

**Manual acceptance:** the evaluation report gives a clear `integrate` or `defer` recommendation based on measurements from the target machine.
