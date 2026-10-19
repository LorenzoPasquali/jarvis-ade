use std::path::{Path, PathBuf};

use uuid::Uuid;

use crate::domain::project::ProjectRoot;
use crate::error::AppError;
use crate::store::Store;

pub fn resolve_registered_root(path: &str) -> Result<PathBuf, AppError> {
    let canonical_path = Path::new(path)
        .canonicalize()
        .map_err(|_| AppError::InvalidProjectRoot)?;
    if canonical_path.to_str() != Some(path) || !canonical_path.is_dir() {
        return Err(AppError::InvalidProjectRoot);
    }
    Ok(canonical_path)
}

pub fn register_root(store: &Store, selected_path: String) -> Result<ProjectRoot, AppError> {
    let canonical_path = PathBuf::from(selected_path)
        .canonicalize()
        .map_err(|_| AppError::InvalidProjectRoot)?;
    if !canonical_path.is_dir() {
        return Err(AppError::InvalidProjectRoot);
    }
    let path = canonical_path
        .to_str()
        .ok_or(AppError::InvalidProjectRoot)?
        .to_owned();

    let name = canonical_path
        .file_name()
        .and_then(|file_name| file_name.to_str())
        .filter(|name| !name.is_empty())
        .map(str::to_owned)
        .unwrap_or_else(|| path.clone());
    let root = ProjectRoot {
        id: Uuid::new_v4().to_string(),
        name,
        path,
    };

    store.add_project_root(root)
}
pub fn list_roots(store: &Store) -> Result<Vec<ProjectRoot>, AppError> {
    store.list_project_roots()
}

pub fn remove_root(store: &Store, project_id: String) -> Result<(), AppError> {
    store.remove_project_root(project_id)
}
