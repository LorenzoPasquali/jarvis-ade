use tauri::State;

use crate::error::AppError;
use crate::store::{ChatMessage, ChatMessageRole, Store};

#[tauri::command]
pub fn save_chat_message(
    store: State<'_, Store>,
    role: ChatMessageRole,
    body: String,
    created_at: String,
) -> Result<ChatMessage, AppError> {
    store.save_chat_message(role, body, created_at)
}

#[tauri::command]
pub fn list_chat_messages(
    store: State<'_, Store>,
    limit: Option<u32>,
) -> Result<Vec<ChatMessage>, AppError> {
    store.list_chat_messages(limit.unwrap_or(100))
}

#[tauri::command]
pub fn clear_chat_history(store: State<'_, Store>) -> Result<(), AppError> {
    store.clear_chat_history()
}

#[tauri::command]
pub fn set_preference(
    store: State<'_, Store>,
    key: String,
    value: String,
    updated_at: String,
) -> Result<(), AppError> {
    store.set_preference(key, value, updated_at)
}

#[tauri::command]
pub fn get_preference(store: State<'_, Store>, key: String) -> Result<Option<String>, AppError> {
    store.get_preference(key)
}
