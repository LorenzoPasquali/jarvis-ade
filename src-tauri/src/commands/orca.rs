use crate::orca::cli::{self, OrcaConnection};

#[tauri::command]
pub fn check_orca_connection() -> OrcaConnection {
    cli::check_connection()
}
