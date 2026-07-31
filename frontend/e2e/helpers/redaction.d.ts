export declare const SENSITIVE_HEADERS: Set<string>;
export declare const REDACTED: string;
export declare const REDACTED_VALUE: string;

export declare function redactText(
  value: unknown,
  options?: { maxLength?: number }
): string;

export declare function redactUrl(rawUrl: unknown): string;

export declare function redactHeaders(
  headers: Record<string, string> | null | undefined
): Record<string, string>;

export declare function assertRedacted(payload: unknown): {
  ok: boolean;
  leaks: string[];
};
