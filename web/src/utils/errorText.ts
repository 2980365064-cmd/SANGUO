import { ApiRequestError } from "../api";

export function errorText(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message;
  return error instanceof Error ? error.message : String(error);
}
