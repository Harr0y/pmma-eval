/**
 * ExperimentRunner — orchestrates one complete experiment run.
 *
 * Evolutionary PM (进化式项目管理) execution model:
 *   To ensure true physical isolation and statistical independence, the framework
 *   runs the entire task execution N times from scratch for the Evolutionary PM method.
 *   Each run uses a fresh workspace and a clean Agent session.
 *
 * Flow:
 *   1. Prepare workspace
 *   2. Install skill + agent templates
 *   3. If Evolutionary PM: run N independent Single-Shot executions
 *      Else: run 1 Single-Shot execution
 *   4. For Evolutionary PM: Aggregate metrics and select the best outcome
 *   5. Persist results
 */
import fs from 'node:fs';
import path from 'node:path';
import { SkillManager, type PMMethod } from './skill-manager.js';
import { prepareWorkspace } from './workspace-prep.js';
import { runAgent, type QueryFn } from './agent-runner.js';
import { runPytest } from './test-runner.js';
import type { Metrics } from './metrics-collector.js';
import type { ExperimentRuntimeConfig } from './config-loader.js';

export interface PathConfig {
  skillTemplates: string;
  agentTemplates: string;
  tasks: string;
  results: string;
}

export interface ExperimentConfig {
  method: PMMethod;
  task: string;
  run: number;
  injectChange?: boolean;
  /** Number of independent samples for Evolutionary PM method. Default: 3 */
  sampleCount?: number;
}

/** Result of a single independent sample run */
export interface SampleResult {
  sampleIndex: number;
  messagesFile: string;
  metrics: Metrics;
  messageCount: number;
  durationMs: number;
  passed: boolean;
  workspaceDir: string;
}

export interface EvoSelection {
  /** Maximum number of samples configured */
  sampleCount: number;
  /** Number of samples actually run (may be lower due to early-stop) */
  samplesRun: number;
  /** Whether the loop stopped early because a sample passed */
  earlyStopped: boolean;
  sampleResults: SampleResult[];
  selectedSampleIndex: number;
  selectionReason: string;
}

export interface ExperimentResult {
  config: ExperimentConfig;
  startTime: string;
  endTime: string;
  durationMs: number;
  testsPassed: boolean;
  testOutput: string;
  metrics: Metrics;
  stateJson: unknown | null;
  messageCount: number;
  messagesFile: string;
  /** Evolutionary PM-specific: structured multi-sample info */
  evolutionary?: EvoSelection;
}

export interface RunnerDeps {
  queryImpl?: QueryFn;
  runPytestImpl?: typeof runPytest;
}

const DEFAULT_EVO_SAMPLE_COUNT = 3;

export class ExperimentRunner {
  private skillManager: SkillManager;
  private pricingData: Record<string, { input: number; output: number; cache_hit: number }> = {};

  constructor(
    private paths: PathConfig,
    private runtimeConfig: ExperimentRuntimeConfig,
    private deps: RunnerDeps = {},
  ) {
    this.skillManager = new SkillManager(paths.skillTemplates, paths.agentTemplates);
    this.loadPricing();
  }

  private loadPricing() {
    const pricingPath = path.join(path.dirname(this.paths.skillTemplates), 'pricing.json');
    if (fs.existsSync(pricingPath)) {
      this.pricingData = JSON.parse(fs.readFileSync(pricingPath, "utf-8"));
    }
  }

  private getPricing() {
    return this.pricingData[this.runtimeConfig.model] || { input: 0, output: 0, cache_hit: 0 };
  }

  async run(cfg: ExperimentConfig): Promise<ExperimentResult> {
    const runId = `${cfg.method}_${cfg.task}_${cfg.run}`;
    const resultDir = path.join(this.paths.results, runId);
    const logPath = path.join(resultDir, 'experiment.jsonl');

    fs.mkdirSync(resultDir, { recursive: true });

    const startTime = new Date();
    this.logEvent(logPath, 'experiment_start', { config: cfg });

    const isEvolutionary = cfg.method === 'evolutionary';
    const sampleCount = isEvolutionary ? (cfg.sampleCount ?? DEFAULT_EVO_SAMPLE_COUNT) : 1;

    if (isEvolutionary && sampleCount > 1) {
      return this.runEvolutionaryMultiSample(cfg, resultDir, logPath, startTime, sampleCount);
    }

    // Default Single-Shot
    const workspaceDir = path.join(resultDir, 'workspace');
    return this.runSingleShot(cfg, resultDir, workspaceDir, logPath, startTime);
  }

  private async runEvolutionaryMultiSample(
    cfg: ExperimentConfig,
    resultDir: string,
    logPath: string,
    startTime: Date,
    sampleCount: number,
  ): Promise<ExperimentResult> {
    // Run samples sequentially with early-stop: stop at first pass.
    // This mirrors the adaptive-consistency strategy (refs #47):
    // don't waste redundant samples when the task is solvable in one shot.
    const sampleResults: SampleResult[] = [];
    let earlyStopped = false;
    for (let k = 0; k < sampleCount; k++) {
      this.logEvent(logPath, 'sample_start', { sampleIndex: k, sampleCount });
      const sampleWorkspace = path.join(resultDir, `sample_${k}`, 'workspace');

      const singleResult = await this.runSingleShot(
        cfg,
        path.join(resultDir, `sample_${k}`),
        sampleWorkspace,
        path.join(resultDir, `sample_${k}`, 'experiment.jsonl'),
        new Date()
      );

      this.logEvent(logPath, 'sample_end', { sampleIndex: k, passed: singleResult.testsPassed });
      sampleResults.push({
        sampleIndex: k,
        messagesFile: `sample_${k}/messages.jsonl`,
        metrics: singleResult.metrics,
        messageCount: singleResult.messageCount,
        durationMs: singleResult.durationMs,
        passed: singleResult.testsPassed,
        workspaceDir: sampleWorkspace,
      });

      // Early-stop: if this sample passes all tests, don't run the rest
      if (singleResult.testsPassed) {
        earlyStopped = true;
        this.logEvent(logPath, 'early_stop', {
          sampleIndex: k,
          reason: `Sample ${k} passed all tests; skipping remaining ${sampleCount - k - 1} samples`,
        });
        break;
      }
    }

    const anyPassed = sampleResults.some(s => s.passed);

    // Select best: first passing sample (since we early-stop on first pass,
    // there should be at most one passing sample — the last one run)
    let bestIndex = 0;
    let minTokens = Infinity;
    for (let i = 0; i < sampleResults.length; i++) {
      const s = sampleResults[i];
      if (s.passed && s.metrics.totalTokens < minTokens) {
        minTokens = s.metrics.totalTokens;
        bestIndex = i;
      }
    }

    // Fallback: when no sample passes, select by lowest token usage
    if (!anyPassed) {
      minTokens = Infinity;
      for (let i = 0; i < sampleResults.length; i++) {
        if (sampleResults[i].metrics.totalTokens < minTokens) {
          minTokens = sampleResults[i].metrics.totalTokens;
          bestIndex = i;
        }
      }
    }

    const selectionReason = anyPassed
      ? `Sample ${bestIndex} selected: passed all tests (${earlyStopped ? 'early-stop after first pass' : 'selected from passed samples'}); ${sampleResults[bestIndex].metrics.totalTokens} tokens`
      : `No sample passed all tests; sample ${bestIndex} selected with lowest token usage (${sampleResults[bestIndex].metrics.totalTokens} tokens) as best attempt`;

    this.logEvent(logPath, 'best_selected', { selectedSampleIndex: bestIndex, reason: selectionReason });

    const aggregatedMetrics = this.aggregateMetrics(sampleResults);
    const endTime = new Date();

    const evoInfo: EvoSelection = {
      sampleCount,
      samplesRun: sampleResults.length,
      earlyStopped,
      sampleResults,
      selectedSampleIndex: bestIndex,
      selectionReason,
    };

    const finalResult: ExperimentResult = {
      config: cfg,
      startTime: startTime.toISOString(),
      endTime: endTime.toISOString(),
      durationMs: endTime.getTime() - startTime.getTime(),
      testsPassed: anyPassed,
      testOutput: `Best sample: ${bestIndex}`,
      metrics: aggregatedMetrics,
      stateJson: null,
      messageCount: sampleResults.reduce((sum, s) => sum + s.messageCount, 0),
      messagesFile: `sample_${bestIndex}/messages.jsonl`,
      evolutionary: evoInfo,
    };

    this.logEvent(logPath, 'experiment_end', { durationMs: finalResult.durationMs, testsPassed: finalResult.testsPassed });

    fs.writeFileSync(path.join(resultDir, 'result.json'), JSON.stringify(finalResult, null, 2));
    return finalResult;
  }

  private async runSingleShot(
    cfg: ExperimentConfig,
    resultDir: string,
    workspaceDir: string,
    logPath: string,
    startTime: Date,
  ): Promise<ExperimentResult> {
    const taskDir = path.join(this.paths.tasks, cfg.task);
    prepareWorkspace(taskDir, workspaceDir);
    this.skillManager.switchMethod(cfg.method, workspaceDir);

    const prompt = this.buildPrompt(cfg);

    let changeInjected = false;
    let messageCount = 0;

    const { messages, metrics } = await runAgent({
      prompt,
      cwd: workspaceDir,
      workspaceDir,
      config: this.runtimeConfig,
      pricing: this.getPricing(),
      agents: this.skillManager.getAgentDefinitions(),
      onMessage: (m) => {
        const msg = m as Record<string, unknown>;
        const summary: Record<string, unknown> = { type: msg.type };
        messageCount++;

        // Enrich system init with registered agents & tools
        if (msg.type === 'system' && (msg as any).subtype === 'init') {
          const init = msg as any;
          summary['agents_registered'] = init.agents;
          summary['tools_available'] = init.tools;
          summary['model'] = init.model;
          console.log(`[experiment] SDK init: model=${init.model}, agents=${JSON.stringify(init.agents)}, tools=${JSON.stringify(init.tools?.slice(0, 10))}...`);
        }

        this.logEvent(logPath, 'agent_message', summary);

        if (cfg.injectChange && !changeInjected) {
          let shouldInject = false;
          let trigger = '';

          // Strategy 1: Check state.json for ATU progress (managed methods)
          const stateJsonPath = path.join(workspaceDir, 'state.json');
          if (fs.existsSync(stateJsonPath)) {
            try {
              const state = JSON.parse(fs.readFileSync(stateJsonPath, 'utf-8'));
              const atus = state.atus || [];
              const doneCount = atus.filter((atu: any) => atu.status === 'Done').length;
              // Inject change when at least 2 ATUs are done (agent has made real progress)
              if (doneCount >= 2) {
                shouldInject = true;
                trigger = `atus_done=${doneCount}`;
              }
            } catch {
              // Ignore partial JSON parse errors during agent atomic writes
            }
          }

          // Strategy 2: Fallback for no-mgmt (no state.json) — inject after enough messages
          if (!shouldInject && messageCount >= 10) {
            shouldInject = true;
            trigger = `message_count=${messageCount}`;
          }

          if (shouldInject) {
            changeInjected = true;
            const changeFileSrc = path.join(taskDir, 'change.md');
            if (fs.existsSync(changeFileSrc)) {
              fs.copyFileSync(changeFileSrc, path.join(workspaceDir, 'change.md'));
              this.logEvent(logPath, 'change_injected', { trigger });
              console.log(`[experiment] 📋 Change injected (trigger: ${trigger})`);
            }
          }
        }
      },
    }, this.deps.queryImpl);

    // Security check: detect if agent accessed files outside workspace (e.g. hidden tests)
    const leaked = detectLeak(messages, workspaceDir);
    if (leaked) {
      console.warn(`[experiment] ⚠️ Agent accessed files outside workspace — result may be tainted`);
    }

    const pytestImpl = this.deps.runPytestImpl ?? runPytest;

    // Final evaluation on HIDDEN tests (preferred) or visible tests (fallback)
    // Read hidden tests directly from source taskDir (not from result tree) to prevent
    // the agent from discovering them via absolute paths during execution.
    const hiddenEvalDir = path.join(taskDir, 'hidden-tests');
    const tempEvalDir = path.join(workspaceDir, 'hidden_eval_run');
    let evalTarget = 'tests';  // fallback to visible tests

    if (fs.existsSync(hiddenEvalDir)) {
      fs.cpSync(hiddenEvalDir, tempEvalDir, { recursive: true });
      evalTarget = 'hidden_eval_run';
    }

    const { passed, output } = pytestImpl(workspaceDir, evalTarget);

    if (fs.existsSync(tempEvalDir)) {
      fs.rmSync(tempEvalDir, { recursive: true, force: true });
    }

    let stateJson: unknown = null;
    const stateJsonPath = path.join(workspaceDir, 'state.json');
    if (fs.existsSync(stateJsonPath)) {
      try {
        stateJson = JSON.parse(fs.readFileSync(stateJsonPath, 'utf-8'));
      } catch {
        // Ignore JSON parse errors for state.json at the end
      }
    }

    const messagesLines = messages.map((m) => JSON.stringify(m)).join('\n');
    fs.writeFileSync(path.join(resultDir, 'messages.jsonl'), messages.length > 0 ? messagesLines + '\n' : '');

    const endTime = new Date();
    const result: ExperimentResult = {
      config: cfg,
      startTime: startTime.toISOString(),
      endTime: endTime.toISOString(),
      durationMs: endTime.getTime() - startTime.getTime(),
      testsPassed: passed,
      testOutput: output,
      metrics,
      stateJson,
      messageCount: messages.length,
      messagesFile: 'messages.jsonl',
    };

    this.logEvent(logPath, 'experiment_end', { durationMs: result.durationMs, testsPassed: result.testsPassed });
    fs.writeFileSync(path.join(resultDir, 'result.json'), JSON.stringify(result, null, 2));

    return result;
  }

  private aggregateMetrics(sampleResults: SampleResult[]): Metrics {
    let tIn = 0, tOut = 0, sIn = 0, mCount = 0, tCost = 0, tCostUsd = 0;
    let mainIn = 0, mainOut = 0, subIn = 0, subOut = 0;
    const agents: Record<string, { input: number; output: number; total: number; messageCount: number }> = {};

    for (const s of sampleResults) {
      tIn += s.metrics.totalInputTokens;
      tOut += s.metrics.totalOutputTokens;
      sIn += s.metrics.staticInputTokens;
      mCount += s.messageCount;
      tCost += s.metrics.totalCostCny;
      tCostUsd += s.metrics.totalCostUsd;

      mainIn += s.metrics.mainAgentTokens.input;
      mainOut += s.metrics.mainAgentTokens.output;
      subIn += s.metrics.subAgentTokens.input;
      subOut += s.metrics.subAgentTokens.output;

      for (const [key, bucket] of Object.entries(s.metrics.byAgent)) {
        if (!agents[key]) agents[key] = { input: 0, output: 0, total: 0, messageCount: 0 };
        agents[key].input += bucket.input;
        agents[key].output += bucket.output;
        agents[key].total += bucket.total;
        agents[key].messageCount += bucket.messageCount;
      }
    }
    return {
      totalInputTokens: tIn,
      totalOutputTokens: tOut,
      totalTokens: tIn + tOut,
      staticInputTokens: sIn,
      dynamicInputTokens: tIn - sIn,
      totalCostCny: tCost,
      totalCostUsd: tCostUsd,
      messageCount: mCount,
      mainAgentTokens: { input: mainIn, output: mainOut, total: mainIn + mainOut },
      subAgentTokens: { input: subIn, output: subOut, total: subIn + subOut },
      byAgent: agents,
    };
  }

  private buildPrompt(cfg: ExperimentConfig): string {
    const methodNames: Record<string, string> = {
      evolutionary: 'Evolutionary PM（进化式项目管理）',
      evolutionary: 'Evolutionary PM（进化式项目管理）',
      scrum: 'Scrum',
      waterfall: 'Waterfall',
      kanban: 'Kanban',
      'no-mgmt': 'No-Mgmt (Solo)',
    };
    return `请根据 README.md 完成这个任务。你正在使用 ${methodNames[cfg.method] || cfg.method} 方法。请严格按照 SKILL 指令中的要求执行。`;
  }

  private logEvent(logPath: string, event: string, data: unknown): void {
    const line = JSON.stringify({ timestamp: new Date().toISOString(), event, data }) + '\n';
    if (!fs.existsSync(path.dirname(logPath))) fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.appendFileSync(logPath, line);
  }
}

/**
 * Detect if the agent accessed files outside its workspace (security check).
 * Checks for references to hidden-tests, hidden-eval-tests, or absolute paths
 * that point outside the workspace directory.
 */
function detectLeak(messages: unknown[], workspaceDir: string): boolean {
  const workspacePrefix = workspaceDir + path.sep;
  const suspiciousKeywords = ['hidden-eval-tests', 'hidden_tests', 'test_todo_eval', 'test_rbac_eval', 'test_security_eval', 'test_tags_eval', 'test_orders_eval'];

  for (const msg of messages) {
    const m = msg as Record<string, unknown>;
    if (m.type !== 'assistant') continue;
    const message = m.message as Record<string, unknown> | undefined;
    if (!message) continue;
    const content = message.content;
    if (!Array.isArray(content)) continue;

    for (const block of content) {
      if (typeof block !== 'object' || block === null) continue;
      if (block.type !== 'tool_use') continue;
      const input = (block as Record<string, unknown>).input as Record<string, unknown> | undefined;
      if (!input) continue;

      const filePath = String(input.file_path ?? '');
      const command = String(input.command ?? '');

      for (const src of [filePath, command]) {
        // Check for direct references to hidden evaluation content
        for (const kw of suspiciousKeywords) {
          if (src.includes(kw)) return true;
        }
      }
    }
  }
  return false;
}
