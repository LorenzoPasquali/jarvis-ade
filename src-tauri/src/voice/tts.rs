use crate::error::AppError;
use serde::Serialize;
use serde_json::{json, Value};
use std::env;
use std::ffi::OsString;
use std::fs;
use std::io::{BufRead, BufReader, Read, Result as IoResult, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, ExitStatus, Stdio};
use std::sync::mpsc::{self, Receiver};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager};
use uuid::Uuid;

const MAX_TEXT_CHARS: usize = 3_000;
const MAX_AUDIO_BYTES: u64 = 12 * 1024 * 1024;
const INSTALL_TIMEOUT: Duration = Duration::from_secs(20 * 60);
const PREPARE_TIMEOUT: Duration = Duration::from_secs(10 * 60);
const MODEL_START_TIMEOUT: Duration = Duration::from_secs(5 * 60);
const SPEECH_TIMEOUT: Duration = Duration::from_secs(5 * 60);
const TTS_SCRIPT: &str = include_str!("../../../voice-worker/pocket_tts.py");
const JARVIS_REFERENCE_MP3: &[u8] = include_bytes!("../../resources/jarvis-reference.mp3");

#[derive(Debug, Clone, Serialize)]
pub struct SpeechStatus {
    pub ready: bool,
    pub message: String,
}

#[derive(Default)]
pub struct SpeechRuntime {
    worker: Mutex<Option<PocketTtsWorker>>,
}

struct PocketTtsWorker {
    child: Child,
    stdin: ChildStdin,
    responses: Receiver<String>,
}

struct TemporaryFile(PathBuf);

struct ProcessOutput {
    status: ExitStatus,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
}

impl Drop for TemporaryFile {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}

impl Drop for PocketTtsWorker {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

pub fn local_speech_status(app: &AppHandle) -> SpeechStatus {
    let Some(paths) = SpeechPaths::new(app) else {
        return SpeechStatus {
            ready: false,
            message: "O Jarvis não conseguiu localizar a pasta local de voz.".into(),
        };
    };

    if paths.is_ready() {
        SpeechStatus {
            ready: true,
            message: "Voz Jarvis pronta. As respostas podem ser sintetizadas localmente.".into(),
        }
    } else {
        SpeechStatus {
            ready: false,
            message: "A voz ainda precisa de uma preparação única. Ela baixa o Pocket TTS e os pesos; depois a síntese funciona offline.".into(),
        }
    }
}

pub fn prepare_local_speech(app: &AppHandle, token: Option<String>) -> SpeechStatus {
    let Some(paths) = SpeechPaths::new(app) else {
        return SpeechStatus {
            ready: false,
            message: "Não consegui abrir a pasta de cache local do Jarvis.".into(),
        };
    };

    match prepare_speech(&paths, token.as_deref()) {
        Ok(()) => SpeechStatus {
            ready: true,
            message: "Voz Jarvis pronta. O modelo e a amostra ficam neste dispositivo; a síntese usa o modo offline.".into(),
        },
        Err(message) => SpeechStatus {
            ready: false,
            message,
        },
    }
}

pub fn speak_local_text(
    app: &AppHandle,
    runtime: &SpeechRuntime,
    text: String,
) -> Result<Vec<u8>, AppError> {
    let text = text.trim();
    if text.is_empty() || text.chars().count() > MAX_TEXT_CHARS {
        return Err(AppError::VoiceOutputFailed);
    }

    let cache_dir = app
        .path()
        .app_cache_dir()
        .map_err(|_| AppError::OperationFailed)?;
    let paths = SpeechPaths::from_cache(cache_dir);
    if !paths.is_ready() {
        return Err(AppError::VoiceOutputUnavailable);
    }

    let id = Uuid::new_v4().to_string();
    let output_path = paths.root.join(format!("speech-{id}.wav"));
    let _temporary_output = TemporaryFile(output_path.clone());
    let audio = runtime.speak(&paths, &id, text, &output_path)?;
    if audio.is_empty() || audio.len() as u64 > MAX_AUDIO_BYTES {
        return Err(AppError::VoiceOutputFailed);
    }
    Ok(audio)
}

impl SpeechRuntime {
    fn speak(
        &self,
        paths: &SpeechPaths,
        id: &str,
        text: &str,
        output_path: &Path,
    ) -> Result<Vec<u8>, AppError> {
        let mut slot = self
            .worker
            .lock()
            .map_err(|_| AppError::VoiceOutputFailed)?;
        if slot
            .as_mut()
            .and_then(|worker| worker.child.try_wait().ok())
            .flatten()
            .is_some()
        {
            slot.take();
        }
        if slot.is_none() {
            *slot = Some(PocketTtsWorker::start(paths)?);
        }

        let result = slot
            .as_mut()
            .ok_or(AppError::VoiceOutputFailed)?
            .speak(id, text, output_path);
        if result.is_err() {
            slot.take();
        }
        result
    }
}

impl PocketTtsWorker {
    fn speak(&mut self, id: &str, text: &str, output_path: &Path) -> Result<Vec<u8>, AppError> {
        let request = json!({
            "id": id,
            "text": text,
            "output_path": output_path,
        });
        serde_json::to_writer(&mut self.stdin, &request)
            .map_err(|_| AppError::VoiceOutputFailed)?;
        self.stdin
            .write_all(b"\n")
            .map_err(|_| AppError::VoiceOutputFailed)?;
        self.stdin
            .flush()
            .map_err(|_| AppError::VoiceOutputFailed)?;

        let response =
            self.responses
                .recv_timeout(SPEECH_TIMEOUT)
                .map_err(|error| match error {
                    mpsc::RecvTimeoutError::Timeout => AppError::VoiceOperationTimeout,
                    mpsc::RecvTimeoutError::Disconnected => AppError::VoiceOutputFailed,
                })?;
        let response: Value =
            serde_json::from_str(&response).map_err(|_| AppError::VoiceOutputFailed)?;
        if response.get("id").and_then(Value::as_str) != Some(id) {
            return Err(AppError::VoiceOutputFailed);
        }
        if response.get("type").and_then(Value::as_str) != Some("done") {
            return Err(AppError::VoiceOutputFailed);
        }

        let metadata = fs::metadata(output_path).map_err(|_| AppError::VoiceOutputFailed)?;
        if metadata.len() == 0 || metadata.len() > MAX_AUDIO_BYTES {
            return Err(AppError::VoiceOutputFailed);
        }
        fs::read(output_path).map_err(|_| AppError::VoiceOutputFailed)
    }

    fn start(paths: &SpeechPaths) -> Result<Self, AppError> {
        let mut command = Command::new(&paths.python);
        command
            .arg(&paths.script)
            .arg("--serve")
            .arg(&paths.voice_state)
            .env("HF_HOME", &paths.models)
            .env("HF_HUB_CACHE", paths.models.join("hub"))
            .env("HF_HUB_OFFLINE", "1")
            .env("TRANSFORMERS_OFFLINE", "1")
            .env("HF_HUB_DISABLE_TELEMETRY", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        let mut child = command
            .spawn()
            .map_err(|_| AppError::VoiceOutputUnavailable)?;
        let stdin = child.stdin.take().ok_or(AppError::VoiceOutputFailed)?;
        let stdout = child.stdout.take().ok_or(AppError::VoiceOutputFailed)?;
        let (sender, responses) = mpsc::channel();
        thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                match line {
                    Ok(line) => {
                        if sender.send(line).is_err() {
                            break;
                        }
                    }
                    Err(_) => break,
                }
            }
        });

        let worker = Self {
            child,
            stdin,
            responses,
        };
        let ready = worker
            .responses
            .recv_timeout(MODEL_START_TIMEOUT)
            .map_err(|_| AppError::VoiceOutputUnavailable)?;
        let ready: Value =
            serde_json::from_str(&ready).map_err(|_| AppError::VoiceOutputUnavailable)?;
        if ready.get("type").and_then(Value::as_str) != Some("ready") {
            return Err(AppError::VoiceOutputUnavailable);
        }
        Ok(worker)
    }
}

struct SpeechPaths {
    root: PathBuf,
    venv: PathBuf,
    python: PathBuf,
    models: PathBuf,
    script: PathBuf,
    reference_mp3: PathBuf,
    voice_state: PathBuf,
    ready_marker: PathBuf,
}

impl SpeechPaths {
    fn new(app: &AppHandle) -> Option<Self> {
        app.path().app_cache_dir().ok().map(Self::from_cache)
    }

    fn from_cache(cache_dir: PathBuf) -> Self {
        let root = cache_dir.join("jarvis-voice");
        let venv = root.join("venv");
        let python = if cfg!(windows) {
            venv.join("Scripts/python.exe")
        } else {
            venv.join("bin/python")
        };
        let models = root.join("models");
        Self {
            script: root.join("pocket_tts.py"),
            reference_mp3: root.join("jarvis-reference.mp3"),
            voice_state: root.join("jarvis-voice.safetensors"),
            ready_marker: root.join("ready.json"),
            root,
            venv,
            python,
            models,
        }
    }

    fn is_ready(&self) -> bool {
        self.python.is_file()
            && self.voice_state.is_file()
            && self.ready_marker.is_file()
            && self.script.is_file()
    }
}

fn prepare_speech(paths: &SpeechPaths, token: Option<&str>) -> Result<(), String> {
    let token = token.map(str::trim).filter(|token| !token.is_empty());
    fs::create_dir_all(&paths.root)
        .map_err(|_| "Não consegui criar a pasta local da voz.".to_owned())?;
    fs::create_dir_all(&paths.models)
        .map_err(|_| "Não consegui criar o cache local do modelo.".to_owned())?;
    fs::write(&paths.script, TTS_SCRIPT)
        .map_err(|_| "Não consegui preparar o worker local de voz.".to_owned())?;
    fs::write(&paths.reference_mp3, JARVIS_REFERENCE_MP3)
        .map_err(|_| "Não consegui copiar a amostra Jarvis para o cache local.".to_owned())?;

    if !paths.python.is_file() {
        let mut venv = Command::new(resolve_base_python());
        venv.arg("-m")
            .arg("venv")
            .arg(&paths.venv)
            .stdin(Stdio::null());
        let output = run_command(venv, Duration::from_secs(90))
            .map_err(|_| "Não consegui criar o ambiente Python local. Instale Python 3 com venv e tente novamente.".to_owned())?;
        if !output.status.success() {
            return Err(format_process_error(
                "Não consegui criar o ambiente Python local. Instale Python 3 com venv e tente novamente.",
                &output,
                None,
            ));
        }
    }

    let mut check_import = python_command(&paths.python);
    check_import
        .args(["-c", "import pocket_tts"])
        .stdin(Stdio::null());
    let import_check = run_command(check_import, Duration::from_secs(45));
    if !matches!(import_check, Ok(ref output) if output.status.success()) {
        let mut install_package = python_command(&paths.python);
        install_package
            .args([
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--quiet",
                "--extra-index-url",
                "https://download.pytorch.org/whl/cpu",
                "pocket-tts==3.3.0",
            ])
            .stdin(Stdio::null());
        let install = run_command(install_package, INSTALL_TIMEOUT)
            .map_err(|_| "A instalação do Pocket TTS expirou. Confira a conexão e tente preparar a voz novamente.".to_owned())?;
        if !install.status.success() {
            return Err(format_process_error(
                "Não consegui instalar o Pocket TTS. Confira a conexão com a internet e tente novamente.",
                &install,
                None,
            ));
        }
    }

    let mut prepare = python_command(&paths.python);
    prepare
        .arg(&paths.script)
        .arg("--prepare")
        .arg(&paths.reference_mp3)
        .arg(&paths.voice_state)
        .env("HF_HOME", &paths.models)
        .env("HF_HUB_CACHE", paths.models.join("hub"))
        .env("HF_HUB_OFFLINE", "0")
        .env("TRANSFORMERS_OFFLINE", "0")
        .env("HF_HUB_DISABLE_TELEMETRY", "1")
        .stdin(Stdio::null());
    if let Some(token) = token {
        prepare.env("HF_TOKEN", token);
    }
    let prepared = run_command(prepare, PREPARE_TIMEOUT)
        .map_err(|_| "A preparação do modelo expirou. Tente novamente; os downloads concluídos foram mantidos no cache.".to_owned())?;
    if !prepared.status.success() || !paths.voice_state.is_file() {
        return Err(format_process_error(
            "Não consegui baixar/preparar o modelo Pocket TTS. Confira a conexão com a internet e tente novamente.",
            &prepared,
            token,
        ));
    }

    fs::write(
        &paths.ready_marker,
        "{\"engine\":\"pocket-tts\",\"version\":\"3.3.0\",\"language\":\"portuguese\"}",
    )
    .map_err(|_| "A voz foi preparada, mas não consegui salvar o estado local.".to_owned())?;
    Ok(())
}

fn resolve_base_python() -> OsString {
    env::var_os("JARVIS_TTS_BASE_PYTHON")
        .or_else(|| env::var_os("JARVIS_VOICE_PYTHON"))
        .unwrap_or_else(|| OsString::from(if cfg!(windows) { "python" } else { "python3" }))
}

fn python_command(python: &Path) -> Command {
    let mut command = Command::new(python);
    command
        .env("HF_HUB_DISABLE_TELEMETRY", "1")
        .env("PIP_DISABLE_PIP_VERSION_CHECK", "1");
    command
}

fn format_process_error(prefix: &str, output: &ProcessOutput, token: Option<&str>) -> String {
    let mut diagnostic = String::from_utf8_lossy(&output.stderr).into_owned();
    if diagnostic.trim().is_empty() {
        diagnostic = String::from_utf8_lossy(&output.stdout).into_owned();
    }
    let normalized = diagnostic.to_lowercase();
    if [
        "gatedrepo",
        "gated repo",
        "401 client error",
        "403 client error",
        "unauthorized",
        "not authorized",
        "access to model",
    ]
    .iter()
    .any(|marker| normalized.contains(marker))
    {
        return "O modelo de clonagem exige acesso aprovado na Hugging Face. Entre em huggingface.co/kyutai/pocket-tts, aceite as condições do modelo e tente novamente com um token de leitura. Cole o token no campo desta tela; o Jarvis só o usa durante o download e não o salva.".into();
    }

    let mut details = diagnostic
        .lines()
        .rev()
        .take(10)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect::<Vec<_>>()
        .join("\n");
    let mut secrets = vec![token.map(str::to_owned)];
    secrets.push(env::var("HF_TOKEN").ok());
    secrets.push(env::var("HUGGING_FACE_HUB_TOKEN").ok());
    for secret in secrets
        .into_iter()
        .flatten()
        .filter(|secret| secret.len() >= 8)
    {
        details = details.replace(&secret, "[token ocultado]");
    }
    if details.trim().is_empty() {
        prefix.to_owned()
    } else {
        format!(
            "{prefix}\n\nDetalhe técnico:\n{}",
            truncate_diagnostic(&details, 1800)
        )
    }
}

fn truncate_diagnostic(value: &str, limit: usize) -> String {
    let mut chars = value.chars();
    let mut result = chars.by_ref().take(limit).collect::<String>();
    if chars.next().is_some() {
        result.push_str("…");
    }
    result
}

fn run_command(mut command: Command, timeout: Duration) -> Result<ProcessOutput, ProcessFailure> {
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
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(100)),
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
    let stderr = stderr_reader
        .join()
        .ok()
        .and_then(Result::ok)
        .unwrap_or_default();
    Ok(ProcessOutput {
        status,
        stdout,
        stderr,
    })
}

enum ProcessFailure {
    Start,
    Timeout,
}

fn read_limited(reader: Option<impl Read>) -> IoResult<Vec<u8>> {
    let Some(reader) = reader else {
        return Ok(Vec::new());
    };
    let mut bytes = Vec::new();
    reader.take(1024 * 1024).read_to_end(&mut bytes)?;
    Ok(bytes)
}
