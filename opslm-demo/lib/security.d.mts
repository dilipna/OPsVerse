export const SUSPICION_THRESHOLD: number;
export const DEFAULT_ALLOWED_HOSTS: string[];
export function normalizeForScan(text: string): string;
export function scanInjection(
  text: string,
  options?: { normalize?: boolean },
): { score: number; matched: string[]; suspicious: boolean };
export function redactSecrets(text: string): { text: string; findings: Record<string, number> };
export function sanitizeOutput(
  text: string,
  allowedHosts?: string[],
): { text: string; findings: Record<string, number> };
export function checkKubectl(command: unknown): { allowed: boolean; reason: string };
