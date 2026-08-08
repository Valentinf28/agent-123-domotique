import assert from 'node:assert/strict';
import test from 'node:test';

import { agentConnectionHealth } from '../lib/connection-health.js';

const now = Date.parse('2026-08-02T12:00:00.000Z');

test('considère une remontée récente comme connectée', () => {
  const result = agentConnectionHealth('2026-08-02T11:59:45.000Z', now);
  assert.equal(result.state, 'online');
  assert.equal(result.connected, true);
  assert.equal(result.ageSeconds, 15);
});

test('signale un retard avant de déclarer la box hors ligne', () => {
  const result = agentConnectionHealth('2026-08-02T11:58:45.000Z', now);
  assert.equal(result.state, 'delayed');
  assert.equal(result.connected, true);
});

test('fournit une action claire lorsque la box est hors ligne', () => {
  const result = agentConnectionHealth('2026-08-02T11:55:00.000Z', now);
  assert.equal(result.state, 'offline');
  assert.equal(result.connected, false);
  assert.match(result.action, /Internet/);
});
