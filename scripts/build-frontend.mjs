import { cpSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(root, "agent", "frontend");
const output = resolve(root, "dist");

rmSync(output, { recursive: true, force: true });
mkdirSync(output, { recursive: true });
cpSync(source, output, { recursive: true });
cpSync(source, resolve(output, "static"), { recursive: true });

const publicConfig = {
  apiBaseUrl: process.env.PUBLIC_API_BASE_URL || "",
  supabaseUrl: process.env.PUBLIC_SUPABASE_URL || "",
  supabaseAnonKey: process.env.PUBLIC_SUPABASE_ANON_KEY || "",
};
writeFileSync(
  resolve(output, "runtime-config.js"),
  `window.ACADEMIC_AGENT_CONFIG = ${JSON.stringify(publicConfig)};\n`,
  "utf8",
);
writeFileSync(
  resolve(output, "static", "runtime-config.js"),
  `window.ACADEMIC_AGENT_CONFIG = ${JSON.stringify(publicConfig)};\n`,
  "utf8",
);

console.log(`Frontend built at ${output}`);
