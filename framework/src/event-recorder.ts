/**
 * EventRecorder — appends events to state.json with framework-generated timestamps.
 * Writes atomically via temp file + rename to prevent corruption.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

export const VALID_EVENT_TYPES = [
  'atu_start',
  'atu_end',
  'sample_start',
  'sample_end',
  'best_selected',
  'state_reset',
  'gen_start',
  'gen_variation',
  'gen_selection',
  'gen_retention',
  'gen_end',
  'evolution_complete',
  'extinct',
  'task_start',
  'task_end',
  'method_switch',
  'replan',
  'test_run',
  'blocker',
  'note',
] as const;

export type EventType = (typeof VALID_EVENT_TYPES)[number];

export interface EventInput {
  type: string;
  atu_id?: string;
  description: string;
  actor?: string;
}

export interface StateEvent extends EventInput {
  timestamp: string;
}

interface StateJson {
  events: StateEvent[];
  [key: string]: unknown;
}

export function validateEvent(event: EventInput): void {
  if (!event.description || event.description.trim() === '') {
    throw new Error('Event description must not be empty');
  }
  if (!(VALID_EVENT_TYPES as readonly string[]).includes(event.type)) {
    throw new Error(
      `Invalid event type "${event.type}". Valid types: ${VALID_EVENT_TYPES.join(', ')}`,
    );
  }
  const needsAtuId = ['atu_start', 'atu_end', 'sample_start', 'sample_end', 'best_selected', 'state_reset', 'gen_start', 'gen_variation', 'gen_selection', 'gen_retention', 'gen_end', 'evolution_complete', 'extinct'];
  if (needsAtuId.includes(event.type) && !event.atu_id) {
    throw new Error(`atu_id is required for event type "${event.type}"`);
  }
}

export function recordEvent(
  workspaceDir: string,
  event: EventInput,
): void {
  validateEvent(event);

  const stateJsonPath = path.join(workspaceDir, 'state.json');

  let state: StateJson;
  if (fs.existsSync(stateJsonPath)) {
    state = JSON.parse(fs.readFileSync(stateJsonPath, 'utf-8')) as StateJson;
    if (!Array.isArray(state.events)) {
      state.events = [];
    }
  } else {
    state = { events: [] };
  }

  const stateEvent: StateEvent = {
    ...event,
    timestamp: new Date().toISOString(),
  };

  state.events.push(stateEvent);

  // Atomic write: write to temp file then rename
  const tmpPath = path.join(
    workspaceDir,
    `.state.json.tmp.${crypto.randomBytes(4).toString('hex')}`,
  );
  fs.writeFileSync(tmpPath, JSON.stringify(state, null, 2));
  fs.renameSync(tmpPath, stateJsonPath);
}
