/**
 * AgentTemplateParser — parses .md agent definition files into SDK AgentDefinition objects.
 *
 * Each agent template is a Markdown file with YAML frontmatter:
 *
 *   ---
 *   name: developer
 *   description: Developer 子 Agent — 负责代码实现
 *   allowed-tools: Read, Write, Edit, Bash, Glob, Grep
 *   ---
 *   # Developer 子 Agent
 *   ...
 */

import fs from 'node:fs';
import path from 'node:path';

export interface ParsedAgent {
  /** Matches the `name` key in the frontmatter — used as the Record key */
  name: string;
  /** Matches AgentDefinition.description */
  description: string;
  /** Matches AgentDefinition.tools */
  tools?: string[];
  /** Matches AgentDefinition.prompt */
  prompt: string;
}

const FRONTMATTER_DELIMITER = '---';

/**
 * Parse a single agent template file.
 */
export function parseAgentTemplate(filePath: string): ParsedAgent {
  const raw = fs.readFileSync(filePath, 'utf-8');

  const lines = raw.split('\n');

  // If the file does not start with frontmatter delimiter, treat the entire file as body
  // and derive name from the filename.
  const hasFrontmatter = lines[0]?.trim() === FRONTMATTER_DELIMITER;

  let bodyStartIndex = 0;
  const meta: Record<string, string> = {};

  if (hasFrontmatter) {
    let inFrontmatter = false;
    let frontmatterStarted = false;
    const frontmatterLines: string[] = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line === FRONTMATTER_DELIMITER) {
        if (!frontmatterStarted) {
          inFrontmatter = true;
          frontmatterStarted = true;
          continue;
        } else {
          inFrontmatter = false;
          bodyStartIndex = i + 1;
          break;
        }
      }
      if (inFrontmatter) {
        frontmatterLines.push(lines[i]);
      }
    }

    for (const line of frontmatterLines) {
      const colonIndex = line.indexOf(':');
      if (colonIndex === -1) continue;
      const key = line.slice(0, colonIndex).trim();
      const value = line.slice(colonIndex + 1).trim();
      meta[key] = value;
    }
  }

  const basename = path.basename(filePath, '.md');
  const name = meta['name'] || basename;
  const description = meta['description'] || '';
  const allowedToolsRaw = meta['allowed-tools'];

  const tools = allowedToolsRaw
    ? allowedToolsRaw.split(',').map((t) => t.trim()).filter(Boolean)
    : undefined;

  const body = lines.slice(bodyStartIndex).join('\n').trim();

  return { name, description, tools, prompt: body };
}

/**
 * Load all agent definitions from a directory.
 * Returns a Record keyed by agent name, suitable for SDK `agents` option.
 */
export function loadAgentDefinitions(agentTemplatesDir: string): Record<string, ParsedAgent> {
  const result: Record<string, ParsedAgent> = {};

  if (!fs.existsSync(agentTemplatesDir)) {
    return result;
  }

  for (const entry of fs.readdirSync(agentTemplatesDir)) {
    if (!entry.endsWith('.md')) continue;
    const filePath = path.join(agentTemplatesDir, entry);
    const parsed = parseAgentTemplate(filePath);
    result[parsed.name] = parsed;
  }

  return result;
}
