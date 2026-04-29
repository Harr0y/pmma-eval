#!/usr/bin/env node
/**
 * CLI entry — runs one experiment.
 *   npm run experiment -- --method evolutionary --task t2_blog --run 1
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadConfig } from './config-loader.js';
import { ExperimentRunner } from './experiment-runner.js';
import type { PMMethod } from './skill-manager.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');

export const VALID_METHODS = ['evolutionary', 'scrum', 'waterfall', 'kanban', 'no-mgmt'] as const;

export function validateArgs(
  parsed: { method: string; task: string; run: number; injectChange?: boolean },
  tasksDir: string,
): { method: PMMethod; task: string; run: number; injectChange?: boolean } {
  if (!(VALID_METHODS as readonly string[]).includes(parsed.method)) {
    throw new Error(
      `Invalid method "${parsed.method}". Valid methods: ${VALID_METHODS.join(', ')}`,
    );
  }

  const taskDir = path.join(tasksDir, parsed.task);
  if (!fs.existsSync(taskDir) || !fs.statSync(taskDir).isDirectory()) {
    throw new Error(
      `Invalid task "${parsed.task}". Must be a directory under tasks/`,
    );
  }

  return {
    method: parsed.method as PMMethod,
    task: parsed.task,
    run: parsed.run,
    injectChange: parsed.injectChange,
  };
}

const BOOLEAN_FLAGS = new Set(['inject-change']);

export function parseArgs(argv: string[]): { method: string; task: string; run: number; injectChange: boolean } {
  const args = new Map<string, string>();
  const flags = new Set<string>();

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const key = a.slice(2);
      if (BOOLEAN_FLAGS.has(key)) {
        flags.add(key);
      } else {
        const val = argv[i + 1];
        if (!val || val.startsWith('--')) {
          throw new Error(`Missing value for --${key}`);
        }
        args.set(key, val);
        i++;
      }
    }
  }

  const method = args.get('method');
  const task = args.get('task');
  const runStr = args.get('run') ?? '1';

  if (!method) throw new Error('--method required');
  if (!task) throw new Error('--task required');

  return { method, task, run: parseInt(runStr, 10), injectChange: flags.has('inject-change') };
}

async function main(): Promise<void> {
  const tasksDir = path.join(projectRoot, 'tasks');
  const parsed = parseArgs(process.argv.slice(2));
  const { method, task, run, injectChange } = validateArgs(parsed, tasksDir);
  const cfg = loadConfig();

  console.log(`\n[experiment] ${method} × ${task} × run=${run} (injectChange=${!!injectChange})`);
  console.log(`[model] ${cfg.model}`);
  console.log(`[endpoint] ${cfg.apiBaseUrl ?? '(default Anthropic)'}\n`);

  const runner = new ExperimentRunner(
    {
      skillTemplates: path.join(projectRoot, 'skill-templates'),
      agentTemplates: path.join(projectRoot, 'agent-templates'),
      tasks: tasksDir,
      results: path.join(projectRoot, 'results'),
    },
    cfg,
  );

  const result = await runner.run({ method, task, run, injectChange });

  console.log('\n======================================');
  console.log('  Experiment Complete');
  console.log(`  Duration: ${(result.durationMs / 1000).toFixed(1)}s`);
  console.log(`  Tests Passed: ${result.testsPassed}`);
  console.log(`  Total Tokens: ${result.metrics.totalTokens}`);
  console.log(`  Messages: ${result.metrics.messageCount}`);
  console.log('======================================\n');
}

// Only auto-run when executed as the entry script, not when imported by tests.
const isEntry =
  import.meta.url === `file://${process.argv[1]}` ||
  import.meta.url.endsWith(process.argv[1] ?? '');

if (isEntry) {
  main().catch((err) => {
    console.error('[error]', err);
    process.exit(1);
  });
}
