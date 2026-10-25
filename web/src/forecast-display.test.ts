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
