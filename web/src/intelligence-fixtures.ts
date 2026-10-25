// Local captured evidence and synthetic outcomes for tests only. Never imported by application code.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { completedOperations } from "../test-support/lifecycle";
import { operationsSchema, type Operations } from "./operations-contracts";
import { researchSchema } from "./research-contracts";
import { contextSchema } from "./context-contracts";
function read(directory:string,file?:string){
  const root=resolve(`public/data/${directory}`);
  let pointer=JSON.parse(readFileSync(resolve(root,"latest.json"),"utf8"));
  const text=readFileSync(resolve(root,file??pointer.file),"utf8");
  if(file){const data=JSON.parse(text);pointer={schema_version:1,file,sha256:file.split("-").at(-1)!.replace(".json",""),generated_at:data.generated_at,season:data.season};}
  return {pointer,text};
}
// Stable real captures exercise positive paths even after live results, expiry,
// season rollover or a no-game refresh. Browser tests inspect the current data.
export const operationsCapture=read("operations","operations-acb075e2b1bbe89e74a4bf93810f2d19e17a3540bfc8f0d0ca4368c799623217.json");
export const researchCapture=read("research");
export const contextCapture=read("context","context-9be0bd883791f34e50c498014de364cc407fc47446a04bac27061323d4f9c43b.json");
export const contextFixture=()=>contextSchema.parse(JSON.parse(contextCapture.text));
export const operationsFixture=()=>operationsSchema.parse(JSON.parse(operationsCapture.text));
export const researchFixture=()=>researchSchema.parse(JSON.parse(researchCapture.text));
export const completedFixture = (homeScore=24, awayScore=17):Operations => operationsSchema.parse(completedOperations(operationsFixture(),homeScore,awayScore));
