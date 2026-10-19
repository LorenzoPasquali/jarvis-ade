use std::collections::HashMap;
use std::io::Read;
use std::process::{Child, ChildStderr, ChildStdout, Command, Stdio};
use std::sync::mpsc::{self, Receiver};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use uuid::Uuid;

use crate::domain::command::{CommandPreview, CommandRequest, CommandResult};
use crate::error::AppError;
use crate::project_access::roots::resolve_registered_root;
use crate::store::Store;

const PREVIEW_LIFETIME_MS: u64 = 60_000;
const MAX_PENDING_PREVIEWS: usize = 100;
const MAX_COMMAND_LINE_CHARS: usize = 4_096;
const MAX_COMMAND_ARGS: usize = 128;
const MAX_ARGUMENT_CHARS: usize = 1_024;
const MAX_OUTPUT_BYTES: usize = 16 * 1024;
const COMMAND_TIMEOUT: Duration = Duration::from_secs(120);

#[derive(Default)]
pub struct PendingCommands {
    previews: Mutex<HashMap<String, CommandPreview>>,
}

pub struct PreparedCommand {
    program: String,
    args: Vec<String>,
    working_directory: std::path::PathBuf,
}

impl PendingCommands {
    fn store(&self, preview: CommandPreview) -> Result<(), AppError> {
        let mut previews = self
            .previews
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        let now = now_unix_ms();
        previews.retain(|_, pending| pending.expires_at_unix_ms > now);
        if previews.len() >= MAX_PENDING_PREVIEWS {
            return Err(AppError::PermissionRequired);
        }
        previews.insert(preview.confirmation_id.clone(), preview);
        Ok(())
    }

    fn consume(&self, confirmation_id: String) -> Result<CommandPreview, AppError> {
        let mut previews = self
            .previews
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        let preview = previews
            .remove(&confirmation_id)
            .ok_or(AppError::CommandConfirmationExpired)?;
        if preview.expires_at_unix_ms <= now_unix_ms() {
            return Err(AppError::CommandConfirmationExpired);
        }
        Ok(preview)
    }
}

fn now_unix_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis().min(u128::from(u64::MAX)) as u64)
        .unwrap_or_default()
}

fn parse_command_line(input: &str) -> Result<(String, Vec<String>), AppError> {
    if input.chars().count() > MAX_COMMAND_LINE_CHARS {
        return Err(AppError::InvalidCommand);
    }

    let mut words = Vec::new();
    let mut word = String::new();
    let mut quote: Option<char> = None;
    let mut escaped = false;
    let mut word_started = false;

    for character in input.chars() {
        if character == '\n'
            || character == '\r'
            || character == '\0'
            || character.is_control() && character != '\t'
        {
            return Err(AppError::InvalidCommand);
        }

        if escaped {
            word.push(character);
            word_started = true;
            escaped = false;
            continue;
        }

        if quote == Some('\'') {
            if character == '\'' {
                quote = None;
            } else {
                word.push(character);
            }
            word_started = true;
            continue;
        }

        if character == '\\' {
            escaped = true;
            word_started = true;
            continue;
        }
        if let Some(active_quote) = quote {
            if character == active_quote {
                quote = None;
            } else if matches!(character, '$' | '`') {
                return Err(AppError::InvalidCommand);
            } else {
                word.push(character);
            }
            word_started = true;
            continue;
        }

        match character {
            '\'' | '"' => {
                quote = Some(character);
                word_started = true;
            }
            '$' | '`' | ';' | '|' | '&' | '<' | '>' => return Err(AppError::InvalidCommand),
            value if value.is_whitespace() => {
                if word_started {
                    words.push(std::mem::take(&mut word));
                    word_started = false;
                }
            }
            value => {
                word.push(value);
                word_started = true;
            }
        }
    }

    if escaped || quote.is_some() {
        return Err(AppError::InvalidCommand);
    }
    if word_started {
        words.push(word);
    }
    if words.is_empty()
        || words.len() > MAX_COMMAND_ARGS + 1
        || words
            .iter()
            .any(|word| word.chars().count() > MAX_ARGUMENT_CHARS)
    {
        return Err(AppError::InvalidCommand);
    }

    let program = words.remove(0);
    if program.is_empty() {
        return Err(AppError::InvalidCommand);
    }
    Ok((program, words))
}

pub fn preview(
    store: &Store,
    pending: &PendingCommands,
    request: CommandRequest,
) -> Result<CommandPreview, AppError> {
    let (program, args) = parse_command_line(&request.command_line)?;
    let root = store.get_project_root(request.project_id.clone())?;
    let working_directory = resolve_registered_root(&root.path)?;

    let preview = CommandPreview {
        confirmation_id: Uuid::new_v4().to_string(),
        project_id: request.project_id,
        program,
        args,
        working_directory: working_directory
            .to_str()
            .ok_or(AppError::InvalidProjectRoot)?
            .to_owned(),
        expires_at_unix_ms: now_unix_ms().saturating_add(PREVIEW_LIFETIME_MS),
    };
    pending.store(preview.clone())?;
    Ok(preview)
}

struct CapturedOutput {
    bytes: Vec<u8>,
    truncated: bool,
}

fn drain_output<T: Read + Send + 'static>(mut reader: T) -> Receiver<CapturedOutput> {
    let (sender, receiver) = mpsc::channel();
    thread::spawn(move || {
        let mut bytes = Vec::new();
        let mut truncated = false;
        let mut buffer = [0_u8; 4 * 1024];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) | Err(_) => break,
                Ok(read) => {
                    let remaining = MAX_OUTPUT_BYTES.saturating_sub(bytes.len());
                    let stored = read.min(remaining);
                    bytes.extend_from_slice(&buffer[..stored]);
                    truncated |= stored < read;
                }
            }
        }
        let _ = sender.send(CapturedOutput { bytes, truncated });
    });
    receiver
}

fn capture_pipes(
    stdout: ChildStdout,
    stderr: ChildStderr,
) -> (Receiver<CapturedOutput>, Receiver<CapturedOutput>) {
    (drain_output(stdout), drain_output(stderr))
}

fn terminate(child: &mut Child) -> Option<std::process::ExitStatus> {
    let _ = child.kill();
    child.wait().ok()
}

fn collect_output(receiver: Receiver<CapturedOutput>) -> CapturedOutput {
    receiver
        .recv_timeout(Duration::from_secs(2))
        .unwrap_or(CapturedOutput {
            bytes: Vec::new(),
            truncated: true,
        })
}

pub fn prepare_confirmed(
    store: &Store,
    pending: &PendingCommands,
    confirmation_id: String,
) -> Result<PreparedCommand, AppError> {
    let preview = pending.consume(confirmation_id)?;
    let root = store.get_project_root(preview.project_id)?;
    let working_directory = resolve_registered_root(&root.path)?;
    if working_directory.to_str() != Some(&preview.working_directory) {
        return Err(AppError::PermissionRequired);
    }

    Ok(PreparedCommand {
        program: preview.program,
        args: preview.args,
        working_directory,
    })
}

pub fn execute(prepared: PreparedCommand) -> Result<CommandResult, AppError> {
    let mut child = Command::new(&prepared.program)
        .args(&prepared.args)
        .current_dir(prepared.working_directory)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|_| AppError::CommandStartFailed)?;
    let stdout = child.stdout.take().ok_or(AppError::OperationFailed)?;
    let stderr = child.stderr.take().ok_or(AppError::OperationFailed)?;
    let (stdout_reader, stderr_reader) = capture_pipes(stdout, stderr);

    let started = Instant::now();
    let mut timed_out = false;
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if started.elapsed() < COMMAND_TIMEOUT => {
                thread::sleep(Duration::from_millis(50));
            }
            Ok(None) => {
                timed_out = true;
                break terminate(&mut child);
            }
            Err(_) => {
                break terminate(&mut child);
            }
        }
    };

    let stdout = collect_output(stdout_reader);
    let stderr = collect_output(stderr_reader);

    Ok(CommandResult {
        exit_code: status.and_then(|status| status.code()),
        stdout_excerpt: String::from_utf8_lossy(&stdout.bytes).into_owned(),
        stderr_excerpt: String::from_utf8_lossy(&stderr.bytes).into_owned(),
        truncated: stdout.truncated || stderr.truncated,
        timed_out,
    })
}
