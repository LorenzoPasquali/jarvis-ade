export interface OrcaConnection {
  connected: boolean;
  state: "runtime_available" | "runtime_unavailable" | "cli_unavailable" | "timeout" | "invalid_response" | "connection_failed";
  message: string;
}
