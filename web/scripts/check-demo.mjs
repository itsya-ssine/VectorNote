// Checks that `npm run build` produced a demo that works on a static host, with no backend.
// Run after the build: `npm run check:demo`.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const problems = [];
const dist = "dist";

if (!existsSync(join(dist, "index.html"))) {
  console.error("dist/index.html is missing: run `npm run build` first.");
  process.exit(1);
}
const html = readFileSync(join(dist, "index.html"), "utf8");

// Every asset the page loads must exist.
for (const [, path] of html.matchAll(/(?:src|href)="(\/[^"]+)"/g)) {
  if (!existsSync(join(dist, path))) problems.push(`index.html points to ${path}, which is not in dist/`);
}

// The production build must be a demo: the code that talks to the backend is removed from the
// bundle when VITE_DEMO_MODE is "true". If these strings are back, the page would call an API.
const assets = readdirSync(join(dist, "assets")).filter((f) => f.endsWith(".js"));
if (assets.length === 0) problems.push("no JavaScript bundle in dist/assets");
for (const file of assets) {
  const js = readFileSync(join(dist, "assets", file), "utf8");
  for (const forbidden of ["vectornote serve", "localhost:8000", "/ask/stream"]) {
    if (js.includes(forbidden)) problems.push(`${file} contains "${forbidden}": not built in demo mode`);
  }
  if (!js.includes("operating-systems-lecture-05.pdf")) problems.push(`${file} has no demo documents`);
}

// The deployment config must be valid and keep the build output where Vercel looks for it.
try {
  const config = JSON.parse(readFileSync("vercel.json", "utf8"));
  if (config.outputDirectory !== "dist") problems.push('vercel.json: outputDirectory must be "dist"');
  const csp = JSON.stringify(config.headers ?? []);
  if (!csp.includes("Content-Security-Policy")) problems.push("vercel.json: no Content-Security-Policy header");
} catch (err) {
  problems.push(`vercel.json is not valid JSON: ${err.message}`);
}

if (problems.length > 0) {
  console.error("Demo check failed:\n- " + problems.join("\n- "));
  process.exit(1);
}
console.log("Demo check passed: static build, no backend code, deployment config valid.");
