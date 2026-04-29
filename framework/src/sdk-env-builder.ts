import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { ExperimentRuntimeConfig } from './config-loader.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Find the .venv/bin directory by walking up from the source file.
 * Returns the bin path if found, otherwise undefined.
 */
function findVenvBin(): string | undefined {
  let dir = __dirname;
  for (let i = 0; i < 5; i++) {
    const candidate = path.join(dir, '.venv', 'bin');
    if (fs.existsSync(path.join(candidate, 'python3'))) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return undefined;
}

const venvBin = findVenvBin();

export function buildSdkEnv(
  cfg: ExperimentRuntimeConfig,
  extra?: Record<string, string>,
): Record<string, string> {
  const nodeBin = path.dirname(process.execPath);
  let currentPath = process.env['PATH'] ?? '';
  if (!currentPath.includes(nodeBin)) {
    currentPath = `${nodeBin}:${currentPath}`;
  }
  // Prepend venv bin so Agent uses venv's python3/pip
  if (venvBin) {
    currentPath = `${venvBin}:${currentPath}`;
  }

  // Start from process.env (only string values)
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (v !== undefined) env[k] = v;
  }

  // Merge extra
  if (extra) Object.assign(env, extra);

  // Set critical values (override everything)
  env['ANTHROPIC_API_KEY'] = cfg.apiKey;
  env['PATH'] = currentPath;
  if (cfg.apiBaseUrl) {
    env['ANTHROPIC_BASE_URL'] = cfg.apiBaseUrl;
  } else {
    delete env['ANTHROPIC_BASE_URL'];
  }

  // Remove CLAUDECODE to prevent nested session issues
  delete env['CLAUDECODE'];

  return env;
}
