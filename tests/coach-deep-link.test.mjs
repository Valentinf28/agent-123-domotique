import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(new URL('../app/portal.tsx', import.meta.url), 'utf8');

test('le lien profond ouvre la vue du Coach', () => {
  assert.match(source, /params\.get\("view"\) === "coach"/);
  assert.match(source, /setView\("Automatisations"\)/);
  assert.match(source, /setCoachOpen\(true\)/);
});

test('la question est préremplie sans être envoyée automatiquement', () => {
  assert.match(source, /params\.get\("coachQuestion"\).*slice\(0, 600\)/);
  assert.match(source, /if \(question\) setCoachQuestion\(question\)/);
});
