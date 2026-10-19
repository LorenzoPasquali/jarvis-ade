use serde::ser::SerializeStruct;
use serde::{Serialize, Serializer};
use std::fmt;

#[derive(Debug, Clone, Copy)]
pub enum AppError {
    OrcaUnavailable,
    ProjectNotFound,
    ProjectRootAlreadyRegistered,
    InvalidProjectRoot,
    PathOutsideProject,
    ProjectFileTooLarge,
    InvalidSearchQuery,
    SearchUnavailable,
    InvalidCommand,
    CommandConfirmationExpired,
    CommandStartFailed,
    PermissionRequired,
    VoiceUnavailable,
    VoiceTranscriptionFailed,
    VoiceOutputUnavailable,
    VoiceOutputFailed,
    VoiceSetupFailed,
    VoiceOperationTimeout,
    OperationFailed,
}

impl AppError {
    fn code(self) -> &'static str {
        match self {
            Self::OrcaUnavailable => "orca_unavailable",
            Self::ProjectNotFound => "project_not_found",
            Self::ProjectRootAlreadyRegistered => "project_root_already_registered",
            Self::InvalidProjectRoot => "invalid_project_root",
            Self::PathOutsideProject => "path_outside_project",
            Self::ProjectFileTooLarge => "project_file_too_large",
            Self::InvalidSearchQuery => "invalid_search_query",
            Self::SearchUnavailable => "search_unavailable",
            Self::InvalidCommand => "invalid_command",
            Self::CommandConfirmationExpired => "command_confirmation_expired",
            Self::CommandStartFailed => "command_start_failed",
            Self::PermissionRequired => "permission_required",
            Self::VoiceUnavailable => "voice_unavailable",
            Self::VoiceTranscriptionFailed => "voice_transcription_failed",
            Self::VoiceOutputUnavailable => "voice_output_unavailable",
            Self::VoiceOutputFailed => "voice_output_failed",
            Self::VoiceSetupFailed => "voice_setup_failed",
            Self::VoiceOperationTimeout => "voice_operation_timeout",
            Self::OperationFailed => "operation_failed",
        }
    }

    fn public_message(self) -> &'static str {
        match self {
            Self::OrcaUnavailable => "Não foi possível conectar ao Orca.",
            Self::ProjectNotFound => "O projeto solicitado não foi encontrado.",
            Self::ProjectRootAlreadyRegistered => "Esta pasta já está na lista de projetos.",
            Self::InvalidProjectRoot => "Escolha uma pasta existente e acessível.",
            Self::PathOutsideProject => "O caminho está fora das pastas permitidas.",
            Self::ProjectFileTooLarge => "Este arquivo é grande demais para abrir por aqui.",
            Self::InvalidSearchQuery => "Digite uma busca com até 512 caracteres.",
            Self::SearchUnavailable => "A busca local não está disponível nesta máquina.",
            Self::InvalidCommand => {
                "Comando vazio ou sintaxe não suportada. Use programa e argumentos simples."
            }
            Self::CommandConfirmationExpired => {
                "A prévia expirou. Gere uma nova antes de executar."
            }
            Self::CommandStartFailed => "Não foi possível iniciar este programa neste dispositivo.",
            Self::PermissionRequired => "Esta ação precisa da sua confirmação.",
            Self::VoiceUnavailable => {
                "O modelo local de transcrição não está disponível nesta máquina."
            }
            Self::VoiceTranscriptionFailed => {
                "Não foi possível transcrever o áudio local. Tente gravar novamente."
            }
            Self::VoiceOutputUnavailable => {
                "A fala local ainda não está preparada. Abra Configurações e toque em Preparar voz Jarvis."
            }
            Self::VoiceOutputFailed => {
                "Não consegui gerar o áudio local. Tente ouvir a resposta novamente."
            }
            Self::VoiceSetupFailed => {
                "Não consegui preparar a voz local. Confira Python 3 e acesso à internet para o primeiro download."
            }
            Self::VoiceOperationTimeout => {
                "O processamento de voz demorou mais do que o esperado. Tente novamente."
            }
            Self::OperationFailed => "Não foi possível concluir a operação. Tente novamente.",
        }
    }
}

impl Serialize for AppError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let mut state = serializer.serialize_struct("AppError", 2)?;
        state.serialize_field("code", self.code())?;
        state.serialize_field("message", self.public_message())?;
        state.end()
    }
}

impl fmt::Display for AppError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.public_message())
    }
}

impl std::error::Error for AppError {}
