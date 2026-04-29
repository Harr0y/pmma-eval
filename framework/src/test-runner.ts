/**
 * TestRunner — runs pytest in a workspace directory.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export interface TestResult {
  passed: boolean;
  output: string;
  layoutWarnings: string[];
}

export function checkLayoutWarnings(workspaceDir: string): string[] {
  const warnings: string[] = [];

  const starterDir = path.join(workspaceDir, 'starter');
  if (!fs.existsSync(starterDir)) {
    warnings.push('starter/ directory does not exist');
  } else {
    const pyFiles = fs.readdirSync(starterDir).filter((f) => f.endsWith('.py'));
    if (pyFiles.length === 0) {
      warnings.push('starter/ directory has no .py files');
    }
  }

  // Check for rogue .py files at workspace root (not in starter/ or tests/)
  if (fs.existsSync(workspaceDir)) {
    const rootEntries = fs.readdirSync(workspaceDir, { withFileTypes: true });
    for (const entry of rootEntries) {
      if (
        entry.isFile() &&
        entry.name.endsWith('.py') &&
        !['starter', 'tests', 'hidden_eval_run'].includes(entry.name)
      ) {
        warnings.push(`Rogue .py file at workspace root: ${entry.name}`);
      }
    }
  }

  return warnings;
}

/**
 * Resolve the Python binary to use. Prefers a project-level `.venv` if present,
 * otherwise falls back to the system `python3`.
 */
function resolvePython(): string {
  // Walk up from this file to find a .venv at the experiment root.
  let dir = __dirname;
  for (let i = 0; i < 5; i++) {
    const candidate = path.join(dir, '.venv', 'bin', 'python3');
    if (fs.existsSync(candidate)) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return 'python3';
}

const PYTHON = resolvePython();

export function runPytest(workspaceDir: string, testsSubDir = 'tests', timeoutMs = 120_000): TestResult {
  let output = '';
  const layoutWarnings = checkLayoutWarnings(workspaceDir);

  try {
    // Install deps if requirements.txt present
    const reqFile = path.join(workspaceDir, 'starter', 'requirements.txt');
    if (fs.existsSync(reqFile)) {
      output += execSync(`"${PYTHON}" -m pip install -r "${reqFile}" 2>&1`, {
        cwd: workspaceDir,
        timeout: 60_000,
      }).toString();
    }

    // Run pytest
    output += execSync(`"${PYTHON}" -m pytest "${testsSubDir}/" -v 2>&1`, {
      cwd: workspaceDir,
      timeout: timeoutMs,
    }).toString();

    return { passed: true, output, layoutWarnings };
  } catch (err) {
    const errOut = err instanceof Error && "stdout" in err
      ? String((err as { stdout: unknown }).stdout)
      : String(err);
    return { passed: false, output: output + errOut, layoutWarnings };
  }
}
