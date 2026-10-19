mod commands;
mod domain;
mod error;
mod orca;
mod project_access;
mod store;
mod voice;

use std::fs;
use tauri::Manager;

use crate::commands::{
    app::get_app_version,
    command_runner::{preview_command, run_confirmed_command},
    orca::check_orca_connection,
    project_activity::get_git_activity,
    project_files::{read_project_file, search_project},
    project_roots::{add_project_root, list_project_roots, remove_project_root},
    projects::{save_project_summary, save_session_summary},
    settings::{
        clear_chat_history, get_preference, list_chat_messages, save_chat_message, set_preference,
    },
    voice::{
        get_local_speech_status, prepare_local_speech, speak_local_text, transcribe_local_audio,
    },
};
use crate::project_access::command_runner::PendingCommands;
use crate::store::Store;
use crate::voice::tts::SpeechRuntime;
use std::sync::Arc;

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let app_data_dir = app.path().app_data_dir()?;
            fs::create_dir_all(&app_data_dir)?;

            let database_path = app_data_dir.join("jarvis.sqlite3");
            let store = Store::open(&database_path)?;
            app.manage(store);
            app.manage(PendingCommands::default());
            app.manage(Arc::new(SpeechRuntime::default()));

            Ok(())
        })
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            get_app_version,
            check_orca_connection,
            preview_command,
            run_confirmed_command,
            save_chat_message,
            list_chat_messages,
            clear_chat_history,
            save_project_summary,
            save_session_summary,
            get_git_activity,
            read_project_file,
            search_project,
            add_project_root,
            list_project_roots,
            remove_project_root,
            get_preference,
            set_preference,
            transcribe_local_audio,
            get_local_speech_status,
            prepare_local_speech,
            speak_local_text
        ])
        .run(tauri::generate_context!())
        .expect("Jarvis desktop runtime failed to start");
}
