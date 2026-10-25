import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { selectDisplayForecast } from "./forecast-display";
import type { CurrentArtifact, CurrentGame } from "./current-contracts";
import type { Operations } from "./operations-contracts";

const vectors=JSON.parse(readFileSync("../tests/fixtures/freshness-policy.json","utf8"));
for (const testCase of vectors.cases) {
  it(`matches Python display policy: ${testCase.name}`,()=>{
    const values=structuredClone(vectors.base);
    for (const [path,value] of testCase.changes) {
      const keys=path.split("."); let target=values;
      for (const key of keys.slice(0,-1)) target=target[key];
      target[keys.at(-1)!]=value;
    }
    const before=JSON.stringify(values);
    const choice=selectDisplayForecast(values.current as CurrentArtifact,values.game as CurrentGame,values.operations as Operations|null,Date.parse(testCase.now));
    expect(choice.state).toBe(testCase.expected);
    expect(choice.forecast_id).toBe(testCase.expected === "unavailable" ? null : vectors.base.operations.catalog[0].id);
    expect(JSON.stringify(values)).toBe(before);
  });
}

it("uses the designated evaluation snapshot even when another eligible receipt sorts later",()=>{
  const values=structuredClone(vectors.base);
  values.operations.catalog.push({...structuredClone(values.operations.catalog[0]),id:"f".repeat(64),generated_at:"2026-10-25T01:00:00Z"});
  values.operations.games=[{id:values.game.id,final_forecast_id:values.operations.catalog[0].id}];
  const before=JSON.stringify(values);
  expect(selectDisplayForecast(values.current,values.game,values.operations,Date.parse(values.game.kickoff)).forecast_id).toBe(values.operations.catalog[0].id);
  expect(JSON.stringify(values)).toBe(before);
});
