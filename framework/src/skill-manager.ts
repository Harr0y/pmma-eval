/**
 * SkillManager - manages switching PM method skills in a workspace.
 *
 * Each experiment run needs exactly one PM method skill active in
 * `.claude/skills/`. This class handles copying the correct skill
 * template + all agent templates into the workspace.
 */
import fs from 'node:fs';
import path from 'node:path';
import { loadAgentDefinitions, type ParsedAgent } from './agent-template-parser.js';

export type PMMethod = 'evolutionary' | 'waterfall' | 'scrum' | 'kanban' | 'no-mgmt';

export class SkillManager {
  constructor(
    private skillTemplatesDir: string,
    private agentTemplatesDir: string,
  ) {}

  switchMethod(method: PMMethod, workspaceDir: string): void {
    const srcSkill = path.join(this.skillTemplatesDir, method, 'SKILL.md');
    if (!fs.existsSync(srcSkill)) {
      throw new Error(`Skill template not found: ${srcSkill}`);
    }

    const skillsDir = path.join(workspaceDir, '.claude', 'skills');
    // Clean all existing skill dirs to ensure only one active
    if (fs.existsSync(skillsDir)) {
      for (const entry of fs.readdirSync(skillsDir)) {
        fs.rmSync(path.join(skillsDir, entry), { recursive: true, force: true });
      }
    }

    // Install target skill
    const dstSkillDir = path.join(skillsDir, method);
    fs.mkdirSync(dstSkillDir, { recursive: true });
    fs.copyFileSync(srcSkill, path.join(dstSkillDir, 'SKILL.md'));

    // Copy agent templates
    const dstAgentsDir = path.join(workspaceDir, '.claude', 'agents');
    fs.mkdirSync(dstAgentsDir, { recursive: true });
    if (fs.existsSync(this.agentTemplatesDir)) {
      for (const entry of fs.readdirSync(this.agentTemplatesDir)) {
        if (entry.endsWith('.md')) {
          fs.copyFileSync(
            path.join(this.agentTemplatesDir, entry),
            path.join(dstAgentsDir, entry),
          );
        }
      }
    }
  }

  /**
   * Parse agent template files into SDK-ready AgentDefinition records.
   * This ensures sub-agents receive proper system prompts and tool restrictions
   * when invoked via the Task tool, instead of falling back to generic agents.
   */
  getAgentDefinitions(): Record<string, ParsedAgent> {
    return loadAgentDefinitions(this.agentTemplatesDir);
  }
}
