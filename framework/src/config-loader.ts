import { config as dotenvConfig } from 'dotenv';

export interface ExperimentRuntimeConfig {
  apiKey: string;
  apiBaseUrl?: string;
  model: string;
}

const DEFAULT_MODEL = 'glm-5-turbo';

export function loadConfig(envPath?: string): ExperimentRuntimeConfig {
  // Auto-load .env from CWD if no explicit path given
  dotenvConfig(envPath ? { path: envPath, override: false } : { override: false });

  const apiKey =
    process.env['ANTHROPIC_API_KEY'] || process.env['ANTHROPIC_AUTH_TOKEN'];
  if (!apiKey) {
    throw new Error(
      'ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) is required. Set it in .env or as an environment variable.',
    );
  }

  return {
    apiKey,
    apiBaseUrl: process.env['ANTHROPIC_BASE_URL'] || undefined,
    model: process.env['EXPERIMENT_MODEL'] || DEFAULT_MODEL,
  };
}
