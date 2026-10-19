use crate::error::AppError;
use crate::voice::tts::{SpeechRuntime, SpeechStatus};
use crate::voice::{tts, worker};
use std::sync::Arc;
use tauri::{AppHandle, State};

#[tauri::command]
pub fn transcribe_local_audio(
    app: AppHandle,
    audio_bytes: Vec<u8>,
    mime_type: String,
) -> Result<String, AppError> {
    worker::transcribe_audio(&app, audio_bytes, mime_type)
}

#[tauri::command]
pub fn get_local_speech_status(app: AppHandle) -> SpeechStatus {
    tts::local_speech_status(&app)
}

#[tauri::command]
pub async fn prepare_local_speech(
    app: AppHandle,
    token: Option<String>,
) -> Result<SpeechStatus, AppError> {
    tauri::async_runtime::spawn_blocking(move || tts::prepare_local_speech(&app, token))
        .await
        .map_err(|_| AppError::VoiceSetupFailed)
}

#[tauri::command]
pub async fn speak_local_text(
    app: AppHandle,
    runtime: State<'_, Arc<SpeechRuntime>>,
    text: String,
) -> Result<Vec<u8>, AppError> {
    let runtime = runtime.inner().clone();
    tauri::async_runtime::spawn_blocking(move || tts::speak_local_text(&app, &runtime, text))
        .await
        .map_err(|_| AppError::VoiceOutputFailed)?
}
