use crate::error::AppError;
use serde_json::Value;
use std::env;
use std::ffi::OsString;
use std::fs;
use std::io::{Read, Result as IoResult};
use std::path::PathBuf;
use std::process::{Command, ExitStatus, Stdio};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager};
use uuid::Uuid;

const MAX_AUDIO_BYTES: usize = 12 * 1024 * 1024;
const TRANSCRIPTION_TIMEOUT: Duration = Duration::from_secs(90);
const TRANSCRIPTION_SCRIPT: &str = include_str!("../../../voice-worker/transcribe.py");

struct ProcessOutput {
    status: ExitStatus,
    stdout: Vec<u8>,
}

struct TemporaryFiles(Vec<PathBuf>);

impl Drop for TemporaryFiles {
    fn drop(&mut self) {
        for path in &self.0 {
            let _ = fs::remove_file(path);
        }
    }
}

pub fn transcribe_audio(
    app: &AppHandle,
    audio_bytes: Vec<u8>,
    mime_type: String,
) -> Result<String, AppError> {
    if audio_bytes.len() < 128 || audio_bytes.len() > MAX_AUDIO_BYTES {
        return Err(AppError::VoiceTranscriptionFailed);
    }

    let extension = match mime_type.to_ascii_lowercase().as_str() {
        value if value.contains("webm") => "webm",
        value if value.contains("ogg") => "ogg",
        value if value.contains("wav") => "wav",
        value if value.contains("mp4") => "m4a",
        _ => return Err(AppError::VoiceTranscriptionFailed),
    };

    let cache_dir = app
        .path()
        .app_cache_dir()
        .map_err(|_| AppError::OperationFailed)?;
    fs::create_dir_all(&cache_dir).map_err(|_| AppError::OperationFailed)?;
    let id = Uuid::new_v4();
    let input_path = cache_dir.join(format!("voice-input-{id}.{extension}"));
    let wav_path = cache_dir.join(format!("voice-input-{id}.wav"));
    let _temporary_files = TemporaryFiles(vec![input_path.clone(), wav_path.clone()]);
    fs::write(&input_path, audio_bytes).map_err(|_| AppError::OperationFailed)?;

    let mut ffmpeg = Command::new("ffmpeg");
    ffmpeg
        .args(["-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i"])
        .arg(&input_path)
        .args(["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le"])
        .arg(&wav_path)
        .stdin(Stdio::null());
    let converted = run_process(ffmpeg, Duration::from_secs(20)).map_err(|error| match error {
        ProcessFailure::Timeout => AppError::VoiceOperationTimeout,
        ProcessFailure::Start => AppError::VoiceUnavailable,
    })?;
    if !converted.status.success() || !wav_path.is_file() {
        return Err(AppError::VoiceUnavailable);
    }

    let python = resolve_python();
    let mut transcriber = Command::new(python);
    transcriber
        .arg("-c")
        .arg(TRANSCRIPTION_SCRIPT)
        .arg(&wav_path)
        .env("HF_HUB_OFFLINE", "1")
        .env("TRANSFORMERS_OFFLINE", "1")
        .env("TOKENIZERS_PARALLELISM", "false")
        .stdin(Stdio::null());

    let output = run_process(transcriber, TRANSCRIPTION_TIMEOUT).map_err(|error| match error {
        ProcessFailure::Timeout => AppError::VoiceOperationTimeout,
        ProcessFailure::Start => AppError::VoiceUnavailable,
    })?;
    if !output.status.success() {
        return Err(AppError::VoiceUnavailable);
    }

    let response: Value =
        serde_json::from_slice(&output.stdout).map_err(|_| AppError::VoiceTranscriptionFailed)?;
    let text = response
        .get("text")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_owned();
    if text.is_empty() {
        return Err(AppError::VoiceTranscriptionFailed);
    }
    Ok(text)
}

enum ProcessFailure {
    Start,
    Timeout,
}

fn run_process(mut command: Command, timeout: Duration) -> Result<ProcessOutput, ProcessFailure> {
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = command.spawn().map_err(|_| ProcessFailure::Start)?;
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let stdout_reader = thread::spawn(move || read_limited(stdout));
    let stderr_reader = thread::spawn(move || read_limited(stderr));
    let deadline = Instant::now() + timeout;

    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(80)),
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                let _ = stdout_reader.join();
                let _ = stderr_reader.join();
                return Err(ProcessFailure::Timeout);
            }
            Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                let _ = stdout_reader.join();
                let _ = stderr_reader.join();
                return Err(ProcessFailure::Start);
            }
        }
    };

    let stdout = stdout_reader
        .join()
        .ok()
        .and_then(Result::ok)
        .unwrap_or_default();
    let _stderr = stderr_reader
        .join()
        .ok()
        .and_then(Result::ok)
        .unwrap_or_default();
    Ok(ProcessOutput { status, stdout })
}

fn read_limited(reader: Option<impl Read>) -> IoResult<Vec<u8>> {
    let Some(reader) = reader else {
        return Ok(Vec::new());
    };
    let mut bytes = Vec::new();
    reader.take(1024 * 1024).read_to_end(&mut bytes)?;
    Ok(bytes)
}

fn resolve_python() -> OsString {
    if let Some(configured) = env::var_os("JARVIS_VOICE_PYTHON") {
        return configured;
    }

    let candidates = [
        PathBuf::from("/git/FERRAMENTAS-LOCAL/OmniVoice/.venv/bin/python"),
        env::var_os("HOME")
            .map(PathBuf::from)
            .map(|home| home.join("FERRAMENTAS-LOCAL/OmniVoice/.venv/bin/python"))
            .unwrap_or_default(),
    ];
    candidates
        .iter()
        .find(|path| path.is_file())
        .map(|path| path.as_os_str().to_owned())
        .unwrap_or_else(|| OsString::from("python3"))
}
