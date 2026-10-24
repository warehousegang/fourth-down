// Test helper only; never imported by application modules.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { currentSchema } from "./current-contracts";
const directory = resolve("public/data/current");
export const currentPointer = JSON.parse(readFileSync(resolve(directory, "latest.json"), "utf8"));
export const currentText = readFileSync(resolve(directory, currentPointer.file), "utf8");
// Immutable real capture keeps positive-path tests independent of later no-game/expired refreshes.
const representative = readFileSync(resolve(directory, "forecast-2026-3449f56cda00dca8e4f4c253458d471b8924cc3ec9a25fd4a5821d356d7737cb.json"), "utf8");
export const currentFixture = () => currentSchema.parse(JSON.parse(representative));
