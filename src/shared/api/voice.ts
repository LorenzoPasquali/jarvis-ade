import { invoke } from "@tauri-apps/api/core";

export interface LocalSpeechStatus {
  ready: boolean;
  message: string;
}

export function transcribeLocalAudio(audioBytes: number[], mimeType: string): Promise<string> {
  return invoke<string>("transcribe_local_audio", { audioBytes, mimeType });
}

export function getLocalSpeechStatus(): Promise<LocalSpeechStatus> {
  return invoke<LocalSpeechStatus>("get_local_speech_status");
}

export function prepareLocalSpeech(token?: string): Promise<LocalSpeechStatus> {
  return invoke<LocalSpeechStatus>("prepare_local_speech", { token: token || null });
}

export function speakLocalText(text: string): Promise<number[]> {
  return invoke<number[]>("speak_local_text", { text });
}
