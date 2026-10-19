use tauri::State;

use crate::domain::project::ProjectRoot;
use crate::error::AppError;
use crate::project_access::roots;
use crate::store::Store;

#[tauri::command]
pub fn add_project_root(store: State<'_, Store>, path: String) -> Result<ProjectRoot, AppError> {
    roots::register_root(&store, path)
}

#[tauri::command]
pub fn list_project_roots(store: State<'_, Store>) -> Result<Vec<ProjectRoot>, AppError> {
    roots::list_roots(&store)
}

#[tauri::command]
pub fn remove_project_root(store: State<'_, Store>, project_id: String) -> Result<(), AppError> {
    roots::remove_root(&store, project_id)
}
