use serde::Serialize;
use serde_json::Value;
use std::env;
use std::io::{Read, Result as IoResult};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OrcaConnection {
    pub connected: bool,
    pub state: &'static str,
    pub message: &'static str,
}

impl OrcaConnection {
    fn unavailable(state: &'static str, message: &'static str) -> Self {
        Self {
            connected: false,
            state,
            message,
        }
    }
}

/// Checks documented, read-only repo discovery. This proves CLI/runtime access
/// only; it does not claim that session reading or message routing is ready.
pub fn check_connection() -> OrcaConnection {
    let program = match resolve_program() {
        Ok(program) => program,
        Err(()) => return OrcaConnection::unavailable(
            "cli_unavailable",
            "Não encontrei o CLI do Orca nesta sessão. Confira se o Orca está instalado e tente novamente.",
        ),
    };

    let mut child = match Command::new(program)
        .args(["repo", "list", "--json"])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(child) => child,
        Err(_) => return OrcaConnection::unavailable(
            "cli_unavailable",
            "Não consegui iniciar o CLI do Orca. Confira o caminho configurado e tente novamente.",
        ),
    };

    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let stdout_reader = thread::spawn(move || read_limited(stdout));
    let stderr_reader = thread::spawn(move || read_limited(stderr));
    let deadline = Instant::now() + Duration::from_secs(5);

    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(80)),
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                let _ = stdout_reader.join();
                let _ = stderr_reader.join();
                return OrcaConnection::unavailable(
                    "timeout",
                    "O CLI do Orca demorou demais para responder. Verifique se o app está aberto e tente novamente.",
                );
            }
            Err(_) => break None,
        }
    };

    let output = stdout_reader
        .join()
        .ok()
        .and_then(Result::ok)
        .unwrap_or_default();
    let _diagnostic = stderr_reader
        .join()
        .ok()
        .and_then(Result::ok)
        .unwrap_or_default();
    let response = match serde_json::from_slice::<Value>(&output) {
        Ok(response) => response,
        Err(_) => {
            return OrcaConnection::unavailable(
                "invalid_response",
                "O CLI respondeu em um formato que o Jarvis ainda não reconhece.",
            )
        }
    };

    if response.get("ok").and_then(Value::as_bool) == Some(true)
        && status.is_some_and(|status| status.success())
    {
        return OrcaConnection {
            connected: true,
            state: "runtime_available",
            message: "O comando repo list do CLI respondeu. Este Jarvis ainda não consulta sessões ou terminais.",
        };
    }

    let error_code = response
        .pointer("/error/code")
        .and_then(Value::as_str)
        .unwrap_or_default();
    match error_code {
        "runtime_unavailable" | "runtime_open_timeout" => OrcaConnection::unavailable(
            "runtime_unavailable",
            "Este processo do Jarvis não conseguiu alcançar um runtime do Orca pelo CLI. O app estar aberto em outra sessão não garante acesso por este processo.",
        ),
        "cli_unavailable" | "command_not_found" => OrcaConnection::unavailable(
            "cli_unavailable",
            "O CLI do Orca não está disponível no ambiente em que o Jarvis foi iniciado.",
        ),
        _ => OrcaConnection::unavailable(
            "connection_failed",
            "O CLI do Orca respondeu com erro. Confira o app do Orca e tente novamente.",
        ),
    }
}

fn resolve_program() -> Result<String, ()> {
    if let Some(configured) = env::var_os("ORCA_CLI_COMMAND") {
        let configured = configured.to_string_lossy().trim().to_owned();
        return if configured.is_empty() {
            Err(())
        } else {
            Ok(configured)
        };
    }
    if env::var_os("ORCA_DEV_REPO_ROOT").is_some() {
        return Ok("orca-dev".to_owned());
    }
    let running_in_orca = [
        "ORCA_PANE_KEY",
        "ORCA_TERMINAL_HANDLE",
        "ORCA_WORKTREE_ID",
        "ORCA_AGENT_HOOK_ENDPOINT",
    ]
    .iter()
    .any(|name| env::var_os(name).is_some());
    if running_in_orca {
        return Ok("orca".to_owned());
    }
    #[cfg(target_os = "linux")]
    {
        Ok("orca-ide".to_owned())
    }
    #[cfg(not(target_os = "linux"))]
    {
        Ok("orca".to_owned())
    }
}

fn read_limited(reader: Option<impl Read>) -> IoResult<Vec<u8>> {
    let Some(reader) = reader else {
        return Ok(Vec::new());
    };
    let mut bytes = Vec::new();
    reader.take(1024 * 1024).read_to_end(&mut bytes)?;
    Ok(bytes)
}
