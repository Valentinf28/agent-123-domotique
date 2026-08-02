import assert from "node:assert/strict";
import test from "node:test";

import {
  ASSISTANT_MONTHLY_LIMIT,
  assistantQuotaAllows,
  assistantQuotaBucket,
} from "../lib/assistant-quota";
import { houseAccessAllows } from "../lib/portal-api-auth";

const access = JSON.stringify({
  "maison-a": ["client-a@example.com"],
  "maison-b": ["client-b@example.com"],
});

test("un client ne peut pas accéder à la maison d’un autre client", () => {
  assert.equal(houseAccessAllows(access, "CLIENT-A@example.com", "maison-a"), true);
  assert.equal(houseAccessAllows(access, "client-a@example.com", "maison-b"), false);
  assert.equal(houseAccessAllows("{invalide", "client-a@example.com", "maison-a"), false);
});

test("un installateur déclaré conserve l’accès aux maisons", () => {
  assert.equal(
    houseAccessAllows(access, "tech@example.com", "maison-b", "tech@example.com"),
    true,
  );
});

test("les quotas sont séparés par assistant et suivent le mois français", () => {
  const justBeforeMidnightUtc = new Date("2026-08-31T22:30:00.000Z");
  assert.equal(
    assistantQuotaBucket("automation", justBeforeMidnightUtc),
    "automation:2026-09",
  );
  assert.equal(
    assistantQuotaBucket("energy", justBeforeMidnightUtc),
    "energy:2026-09",
  );
  assert.equal(assistantQuotaAllows(ASSISTANT_MONTHLY_LIMIT - 1), true);
  assert.equal(assistantQuotaAllows(ASSISTANT_MONTHLY_LIMIT), false);
});
