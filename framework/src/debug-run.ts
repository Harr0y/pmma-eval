#!/usr/bin/env node
/**
 * Debug wrapper: runs the experiment and captures full output.
 * Writes all messages to a debug file for inspection.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadConfig } from './config-loader.js';
import { ExperimentRunner } from './experiment-runner.js';
import type { QueryFn } from './agent-runner.js';
import { query } from '@anthropic-ai/claude-agent-sdk';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');

const resultDir = path.join(projectRoot, 'results', 'scrum_t2_blog_debug');
fs.rmSync(resultDir, { recursive: true, force: true });
fs.mkdirSync(resultDir, { recursive: true });

const debugLog = path.join(resultDir, 'debug.log');
function dbg(msg: string) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  fs.appendFileSync(debugLog, line);
  process.stderr.write(line);
}

async function main() {
  const cfg = loadConfig();
  dbg(`Model: ${cfg.model}`);
  dbg(`Endpoint: ${cfg.apiBaseUrl}`);

  const runner = new ExperimentRunner(
    {
      skillTemplates: path.join(projectRoot, 'skill-templates'),
      agentTemplates: path.join(projectRoot, 'agent-templates'),
      tasks: path.join(projectRoot, 'tasks'),
      results: resultDir,
    },
    cfg,
  );

  dbg('Starting experiment: scrum × t2_blog × run=debug');

  const result = await runner.run({
    method: 'scrum',
    task: 't2_blog',
    run: 99,
  });

  dbg(`Done! passed=${result.testsPassed} duration=${(result.durationMs / 1000).toFixed(1)}s`);
  dbg(`Tokens: in=${result.metrics.totalInputTokens} out=${result.metrics.totalOutputTokens}`);
  dbg(`Messages: ${result.messageCount}`);
  dbg(`Test output: ${result.testOutput?.slice(0, 500)}`);

  // Print summary of byAgent
  dbg(`Agent breakdown:`);
  for (const [name, bucket] of Object.entries(result.metrics.byAgent)) {
    dbg(`  ${name}: in=${bucket.input} out=${bucket.output} msgs=${bucket.messageCount}`);
  }

  // Check workspace for code changes
  const starterDir = path.join(resultDir, 'scrum_t2_blog_99', 'workspace', 'starter');
  if (fs.existsSync(starterDir)) {
    const files = fs.readdirSync(starterDir);
    dbg(`Workspace starter/ files: ${files.join(', ')}`);
  }

  // Print state.json if exists
  const statePath = path.join(resultDir, 'scrum_t2_blog_99', 'workspace', 'state.json');
  if (fs.existsSync(statePath)) {
    const state = JSON.parse(fs.readFileSync(statePath, 'utf-8'));
    dbg(`State: method=${state.method}, ATUs=${state.atus?.length}, events=${state.events?.length}`);
    if (state.atus) {
      for (const atu of state.atus) {
        dbg(`  ATU ${atu.id}: "${atu.title}" status=${atu.status}`);
      }
    }
  } else {
    dbg('No state.json found');
  }
}

main().catch((err) => {
  dbg(`FATAL: ${err.message}\n${err.stack}`);
  process.exit(1);
});
