const { spawnSync } = require("node:child_process");
const path = require("node:path");

const binary = path.join(
  __dirname,
  "node_modules", "@railway", "cli", "bin",
  process.platform === "win32" ? "railway.exe" : "railway",
);
const environment = { ...process.env };
// The SDK invokes `railway --version` during evaluation. A shell's inherited
// `_` can point to a WSL path or Node instead; resolve the pinned native CLI.
delete environment._;
const pathKey = Object.keys(environment).find((key) => key.toLowerCase() === "path");
const originalPath = pathKey ? environment[pathKey] : "";
for (const key of Object.keys(environment)) {
  if (key.toLowerCase() === "path") delete environment[key];
}
environment[process.platform === "win32" ? "Path" : "PATH"] = [
  path.dirname(process.execPath), path.dirname(binary), originalPath,
].join(path.delimiter);
const result = spawnSync(binary, process.argv.slice(2), {
  stdio: "inherit",
  env: environment,
});
if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}
process.exit(result.status ?? 1);
