import fs from "node:fs";

const version = fs.readFileSync("VERSION", "utf8").trim();
const index = fs.readFileSync("index.html", "utf8");
const sw = fs.readFileSync("service-worker.js", "utf8");
const manifest = JSON.parse(fs.readFileSync("manifest.webmanifest", "utf8"));

const failures = [];
const expect = (condition, message) => { if (!condition) failures.push(message); };

expect(/^\d+\.\d+$/.test(version), `VERSION must look like 1.4; got "${version}"`);
expect(index.includes(`Local-first • v${version}`), "index.html version badge does not match VERSION");
expect(sw.includes(`const CACHE="ops-hub-v${version}"`), "service-worker cache name does not match VERSION");
expect(index.includes('rel="manifest" href="manifest.webmanifest"'), "index.html is missing the PWA manifest link");
expect(index.includes('serviceWorker.register("service-worker.js")'), "index.html is missing service-worker registration");
expect(manifest.name === "Ops Hub", 'manifest name must remain "Ops Hub"');
expect(manifest.start_url === "./" && manifest.scope === "./", "manifest start_url/scope must remain ./");
expect(index.includes('id="openStudyHelpLiveBtn"'), "protected StudyHelpAI Live tile is missing");
expect(index.includes("Worker Bench"), "protected Worker Bench UI is missing");
expect(index.includes("ensureProvenWorkerSeeds"), "Worker Bench seed migration is missing");

const badgeVersions = [...index.matchAll(/Local-first\s*•\s*v(\d+\.\d+)/g)].map(m => m[1]);
expect(badgeVersions.length === 1, `expected exactly one visible version badge, found ${badgeVersions.length}`);
if (badgeVersions.length === 1) expect(badgeVersions[0] === version, "visible version badge is stale");

const cacheVersions = [...sw.matchAll(/ops-hub-v(\d+\.\d+)/g)].map(m => m[1]);
expect(cacheVersions.length >= 1, "service-worker cache version is missing");
expect(cacheVersions.every(v => v === version), `service-worker contains stale cache version(s): ${[...new Set(cacheVersions)].join(", ")}`);

if (failures.length) {
  console.error("Ops Hub release verification failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`Ops Hub v${version} release verification passed.`);
