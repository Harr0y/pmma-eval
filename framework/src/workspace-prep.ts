/**
 * Workspace preparation — copies task starter contents into a fresh workspace.
 */
import fs from 'node:fs';
import path from 'node:path';

const SKIP_NAMES = new Set(['.git', '__pycache__', '.pytest_cache', '.DS_Store', 'node_modules']);
const SKIP_EXTENSIONS = new Set(['.pyc', '.pyo']);

export function prepareWorkspace(taskDir: string, workspaceDir: string): void {
  if (!fs.existsSync(taskDir)) {
    throw new Error(`Task directory not found: ${taskDir}`);
  }

  if (fs.existsSync(workspaceDir)) {
    fs.rmSync(workspaceDir, { recursive: true, force: true });
  }
  fs.mkdirSync(workspaceDir, { recursive: true });

  // 1. Copy everything except hidden-tests
  copyDirRecursive(taskDir, workspaceDir, (name) => name !== 'hidden-tests');

  // 2. Hidden tests are NOT copied to the result tree to prevent agent from
  //    discovering them via absolute paths. The experiment-runner will copy
  //    them directly from the source taskDir to a temp dir during evaluation.

  // 3. Write CLAUDE.md with workspace layout instructions
  writeCLAUDEmd(workspaceDir);
}

/**
 * Generate a CLAUDE.md in the workspace to guide the agent's file layout awareness.
 */
function writeCLAUDEmd(workspaceDir: string): void {
  const lines: string[] = [
    '# Workspace Layout',
    '',
    'Code goes in `starter/` only.',
    'Do NOT create new top-level Python files.',
    'Tests live under `tests/`.',
    '',
  ];

  // Scan actual directories to add dynamic context
  const entries = fs.readdirSync(workspaceDir, { withFileTypes: true });
  const dirs = entries.filter(e => e.isDirectory()).map(e => e.name);
  const files = entries.filter(e => e.isFile()).map(e => e.name);

  if (dirs.length > 0 || files.length > 0) {
    lines.push('## Current workspace contents');
    lines.push('');
    if (files.length > 0) {
      lines.push(`Files: ${files.join(', ')}`);
    }
    if (dirs.length > 0) {
      lines.push(`Directories: ${dirs.join(', ')}`);
    }
    lines.push('');
  }

  fs.writeFileSync(path.join(workspaceDir, 'CLAUDE.md'), lines.join('\n'));
}

export function copyDirRecursive(src: string, dest: string, filter: (name: string) => boolean = () => true): void {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    if (!filter(entry.name)) continue;
    if (SKIP_NAMES.has(entry.name)) continue;
    if (SKIP_EXTENSIONS.has(path.extname(entry.name))) continue;

    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDirRecursive(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}
