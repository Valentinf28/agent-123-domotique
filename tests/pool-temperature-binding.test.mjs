import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const sourceUrl = new URL("../lib/agent-home.ts", import.meta.url);

test("the portal falls back to the pool heat pump current temperature", async () => {
  const source = await readFile(sourceUrl, "utf8");

  assert.match(
    source,
    /dedicatedSensor === "—"[\s\S]*formattedAttribute\(poolClimate, "current_temperature", "°C"\)/,
  );
});
