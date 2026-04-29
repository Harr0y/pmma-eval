/**
 * MetricsCollector — accumulates token/message statistics from SDK message stream.
 * Supports bucketing by agent origin (main vs sub-agent) for MOR calculation.
 */

export interface TokenBucket {
  input: number;
  output: number;
  total: number;
}

export interface AgentBucket extends TokenBucket {
  messageCount: number;
}

export interface Metrics {
  totalInputTokens: number;
  totalOutputTokens: number;
  totalTokens: number;
  staticInputTokens: number;
  dynamicInputTokens: number;
  totalCostCny: number;
  totalCostUsd: number;
  messageCount: number;
  mainAgentTokens: TokenBucket;
  subAgentTokens: TokenBucket;
  byAgent: Record<string, AgentBucket>;
  /** Per-model token breakdown from SDK result message */
  modelUsage?: Record<string, ModelUsageEntry>;
}

export interface ModelUsageEntry {
  inputTokens: number;
  outputTokens: number;
  cacheReadInputTokens: number;
  cacheCreationInputTokens: number;
  costUSD: number;
}

export interface RecordOptions {
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    cache_read_tokens?: number;
  };
  parentToolUseID?: string;
  agentId?: string;
  isStatic?: boolean;
}

export class MetricsCollector {
  private inTokens = 0;
  private outTokens = 0;
  private staticIn = 0;
  private cacheHits = 0;
  private count = 0;

  private mainIn = 0;
  private mainOut = 0;
  private subIn = 0;
  private subOut = 0;

  private agents: Record<string, AgentBucket> = {};
  private costUsd = 0;
  private modelUsageData: Record<string, ModelUsageEntry> = {};

  constructor(private pricing?: { input: number; output: number; cache_hit: number }) {}

  record(msg: RecordOptions): void {
    this.count += 1;
    const inp = msg.usage?.input_tokens ?? 0;
    const out = msg.usage?.output_tokens ?? 0;
    const cacheHit = msg.usage?.cache_read_tokens ?? 0;

    if (msg.usage) {
      this.inTokens += inp;
      this.outTokens += out;
      this.cacheHits += cacheHit;
      if (msg.isStatic) {
        this.staticIn += inp;
      }
    }

    const isSubAgent = !!msg.parentToolUseID;
    if (isSubAgent) {
      this.subIn += inp;
      this.subOut += out;
    } else {
      this.mainIn += inp;
      this.mainOut += out;
    }

    // byAgent breakdown
    const key = msg.agentId ?? (isSubAgent ? 'unknown-sub' : 'main');
    if (!this.agents[key]) {
      this.agents[key] = { input: 0, output: 0, total: 0, messageCount: 0 };
    }
    this.agents[key].input += inp;
    this.agents[key].output += out;
    this.agents[key].total += inp + out;
    this.agents[key].messageCount += 1;
  }

  /**
   * Record final aggregate usage from the SDK result message.
   * GLM and other non-Anthropic providers return 0 in per-message usage,
   * but the SDK's final result message contains accurate totals.
   * This overwrites the accumulated token counts with the authoritative values.
   */
  recordFinalUsage(usage: {
    input_tokens?: number;
    output_tokens?: number;
    cache_read_input_tokens?: number;
    cache_creation_input_tokens?: number;
  }, costUsd?: number, modelUsage?: Record<string, ModelUsageEntry>): void {
    const inTok = usage.input_tokens ?? 0;
    const cacheRead = usage.cache_read_input_tokens ?? 0;
    // input_tokens in the result message includes cache_read_input_tokens
    // Net new input = input_tokens - cache_read_input_tokens
    // But for total accounting we want the gross number
    this.inTokens = inTok + cacheRead;
    this.outTokens = usage.output_tokens ?? 0;
    this.cacheHits = cacheRead;

    if (costUsd !== undefined) {
      this.costUsd = costUsd;
    }
    if (modelUsage) {
      this.modelUsageData = modelUsage;
    }
  }

  private calculateCost(): number {
    if (!this.pricing) return 0;
    // Input tokens usually exclude cache hits in most pricing models, but we check cache hits separately
    // Based on Zhipu pricing, cache hits have a different rate. 
    // Usually input_tokens includes cache_hits? We need to be careful.
    // In Anthropic/Zhipu API, usage.input_tokens is total input, usage.cache_read_tokens is the portion that was cached.
    const nonCachedIn = Math.max(0, this.inTokens - this.cacheHits);
    return (
      nonCachedIn * this.pricing.input +
      this.cacheHits * this.pricing.cache_hit +
      this.outTokens * this.pricing.output
    );
  }

  get(): Metrics {
    return {
      totalInputTokens: this.inTokens,
      totalOutputTokens: this.outTokens,
      totalTokens: this.inTokens + this.outTokens,
      staticInputTokens: this.staticIn,
      dynamicInputTokens: this.inTokens - this.staticIn,
      totalCostCny: this.calculateCost(),
      totalCostUsd: this.costUsd,
      messageCount: this.count,
      mainAgentTokens: {
        input: this.mainIn,
        output: this.mainOut,
        total: this.mainIn + this.mainOut,
      },
      subAgentTokens: {
        input: this.subIn,
        output: this.subOut,
        total: this.subIn + this.subOut,
      },
      byAgent: { ...this.agents },
      modelUsage: Object.keys(this.modelUsageData).length > 0 ? this.modelUsageData : undefined,
    };
  }

  reset(): void {
    this.inTokens = 0;
    this.outTokens = 0;
    this.staticIn = 0;
    this.cacheHits = 0;
    this.count = 0;
    this.mainIn = 0;
    this.mainOut = 0;
    this.subIn = 0;
    this.subOut = 0;
    this.agents = {};
    this.costUsd = 0;
    this.modelUsageData = {};
  }
}
