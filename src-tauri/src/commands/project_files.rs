use tauri::State;

use crate::domain::project::FileExcerpt;
use crate::error::AppError;
use crate::project_access::files;
use crate::store::Store;

#[tauri::command]
pub async fn read_project_file(
    store: State<'_, Store>,
    project_id: String,
    relative_path: String,
) -> Result<FileExcerpt, AppError> {
    let root = store.get_project_root(project_id)?;
    tauri::async_runtime::spawn_blocking(move || files::read_file(root, relative_path))
        .await
        .map_err(|_| AppError::OperationFailed)?
}

#[tauri::command]
pub async fn search_project(
    store: State<'_, Store>,
    project_id: String,
    query: String,
    limit: u32,
) -> Result<Vec<FileExcerpt>, AppError> {
    let root = store.get_project_root(project_id)?;
    tauri::async_runtime::spawn_blocking(move || files::search(root, query, limit))
        .await
        .map_err(|_| AppError::OperationFailed)?
}
