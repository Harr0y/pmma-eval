/**
 * AgentRunner — invokes the Claude Agent SDK with proper env and collects results.
 */
import { query } from '@anthropic-ai/claude-agent-sdk';
import type { SDKMessage } from '@anthropic-ai/claude-agent-sdk';
import { buildSdkEnv } from './sdk-env-builder.js';
import { MetricsCollector, type Metrics, type ModelUsageEntry } from './metrics-collector.js';
import { recordEvent } from './event-recorder.js';
import type { ExperimentRuntimeConfig } from './config-loader.js';
import type { ParsedAgent } from './agent-template-parser.js';

export interface AgentRunOptions {
  prompt: string;
  cwd: string;
  config: ExperimentRuntimeConfig;
  permissionMode?: 'default' | 'bypassPermissions';
  onMessage?: (msg: SDKMessage) => void;
  workspaceDir?: string;
  pricing?: { input: number; output: number; cache_hit: number };
  /** Parsed agent definitions to inject into SDK session */
  agents?: Record<string, ParsedAgent>;
}

export interface AgentRunResult {
  messages: SDKMessage[];
  metrics: Metrics;
}

/**
 * Dependency-injectable query function type — enables mocking in tests.
 */
export type QueryFn = typeof query;

/**
 * Type guard: checks if an SDK message is an assistant turn with usage info.
 */
export function hasUsage(msg: unknown): msg is { 
  type: 'assistant'; 
  message: { 
    usage: { 
      input_tokens?: number; 
      output_tokens?: number; 
      cache_read_tokens?: number 
    } 
  }; 
  parentToolUseID?: string; 
  agentId?: string 
} {
  if (typeof msg !== 'object' || msg === null) return false;
  const obj = msg as Record<string, unknown>;
  if (obj.type !== 'assistant') return false;
  if (typeof obj.message !== 'object' || obj.message === null) return false;
  const inner = obj.message as Record<string, unknown>;
  return typeof inner.usage === 'object' && inner.usage !== null;
}

const RECORD_EVENT_RE = /\[RECORD_EVENT\]\s*(\{.*\})/;

/**
 * Extract text content from an assistant SDK message.
 */
function extractTextContent(msg: unknown): string[] {
  const texts: string[] = [];
  if (typeof msg !== 'object' || msg === null) return texts;
  const obj = msg as Record<string, unknown>;
  if (obj.type !== 'assistant') return texts;
  const inner = obj.message;
  if (typeof inner !== 'object' || inner === null) return texts;
  const content = (inner as Record<string, unknown>).content;
  if (!Array.isArray(content)) return texts;
  for (const block of content) {
    if (typeof block === 'object' && block !== null && (block as Record<string, unknown>).type === 'text') {
      const text = (block as Record<string, unknown>).text;
      if (typeof text === 'string') texts.push(text);
    }
  }
  return texts;
}

export type RecordEventFn = typeof recordEvent;

export async function runAgent(
  opts: AgentRunOptions,
  queryImpl: QueryFn = query,
  recordEventImpl: RecordEventFn = recordEvent,
): Promise<AgentRunResult> {
  const messages: SDKMessage[] = [];
  const collector = new MetricsCollector(opts.pricing);

  const env = buildSdkEnv(opts.config);

  const q = queryImpl({
    prompt: opts.prompt,
    options: {
      cwd: opts.cwd,
      model: opts.config.model,
      permissionMode: opts.permissionMode ?? 'bypassPermissions',
      env,
      settingSources: ['project'],
      agents: opts.agents,
    },
  });

  const workspaceDir = opts.workspaceDir ?? opts.cwd;

  let isFirstAssistant = true;
  for await (const msg of q) {
    messages.push(msg);

    if (hasUsage(msg)) {
      const usage = msg.message.usage;
      const parentToolUseID = (msg as Record<string, unknown>).parentToolUseID as string | undefined;
      const agentId = (msg as Record<string, unknown>).agentId as string | undefined;
      
      collector.record({
        usage: { 
          input_tokens: usage.input_tokens, 
          output_tokens: usage.output_tokens,
          cache_read_tokens: usage.cache_read_tokens ?? (usage as unknown as Record<string, unknown>).cache_read_input_tokens as number | undefined
        },
        parentToolUseID,
        agentId,
        isStatic: isFirstAssistant, // The first assistant message usage includes the initial system prompt and skill
      });
      isFirstAssistant = false;
    }

    // Scan assistant text for [RECORD_EVENT] markers
    for (const text of extractTextContent(msg)) {
      for (const line of text.split('\n')) {
        const match = RECORD_EVENT_RE.exec(line);
        if (match) {
          try {
            const eventData = JSON.parse(match[1]) as { type: string; atu_id?: string; description: string; actor?: string };
            recordEventImpl(workspaceDir, eventData);
          } catch {
            // Ignore malformed event JSON
          }
        }
      }
    }

    opts.onMessage?.(msg);
  }

  // After the stream ends, check for a 'result' message with final aggregate usage.
  // GLM and other non-Anthropic providers return 0 in per-message usage,
  // but the SDK's final result message contains accurate totals.
  const resultMsg = messages.find(m =>
    m != null && (m as Record<string, unknown>).type === 'result'
  ) as Record<string, unknown> | undefined;

  if (resultMsg) {
    const finalUsage = resultMsg.usage as {
      input_tokens?: number;
      output_tokens?: number;
      cache_read_input_tokens?: number;
      cache_creation_input_tokens?: number;
    } | undefined;

    const costUsd = resultMsg.total_cost_usd as number | undefined;

    // Extract per-model usage if available
    const rawModelUsage = resultMsg.modelUsage as Record<string, {
      inputTokens?: number;
      outputTokens?: number;
      cacheReadInputTokens?: number;
      cacheCreationInputTokens?: number;
      costUSD?: number;
    }> | undefined;

    let modelUsage: Record<string, ModelUsageEntry> | undefined;
    if (rawModelUsage) {
      modelUsage = {};
      for (const [model, mu] of Object.entries(rawModelUsage)) {
        modelUsage[model] = {
          inputTokens: mu.inputTokens ?? 0,
          outputTokens: mu.outputTokens ?? 0,
          cacheReadInputTokens: mu.cacheReadInputTokens ?? 0,
          cacheCreationInputTokens: mu.cacheCreationInputTokens ?? 0,
          costUSD: mu.costUSD ?? 0,
        };
      }
    }

    if (finalUsage) {
      collector.recordFinalUsage(finalUsage, costUsd, modelUsage);
    }
  }

  return { messages, metrics: collector.get() };
}
