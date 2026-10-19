use tauri::State;

use crate::domain::command::{CommandPreview, CommandRequest, CommandResult};
use crate::error::AppError;
use crate::project_access::command_runner::{self, PendingCommands};
use crate::store::Store;

#[tauri::command]
pub fn preview_command(
    store: State<'_, Store>,
    pending: State<'_, PendingCommands>,
    request: CommandRequest,
) -> Result<CommandPreview, AppError> {
    command_runner::preview(&store, &pending, request)
}

#[tauri::command]
pub async fn run_confirmed_command(
    store: State<'_, Store>,
    pending: State<'_, PendingCommands>,
    confirmation_id: String,
) -> Result<CommandResult, AppError> {
    let prepared = command_runner::prepare_confirmed(&store, &pending, confirmation_id)?;
    tauri::async_runtime::spawn_blocking(move || command_runner::execute(prepared))
        .await
        .map_err(|_| AppError::OperationFailed)?
}
