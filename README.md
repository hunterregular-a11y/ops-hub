# Ops Hub v1.5

Local-first Operations & AI Systems home-screen PWA. The new Home includes the reviewed OpsHub Guard v0.2 project, review, handoff and recovery workflows.

The existing installation identity is retained: `manifest.webmanifest` name `Ops Hub`, start URL `./`, and scope `./`.

## Data and original tools

On the first open without an existing Guard workspace, valid Ops Saver records, chronological archive entries, and workers are copied into a separate Guard workspace. Original `ops-saver-*` data and the saved Brainstorm Chat link remain unchanged. Failed or malformed migrations preserve the original bytes and display a warning.

Home → Open tools opens the preserved Ops Saver, Worker Bench, Brainstorm shortcut, and authenticated StudyHelpAI Live shortcut. The original tools page links back to the new Home.

## Release rule

`VERSION`, the Home version badge, and `CACHE="ops-hub-vX.Y"` must match. Run `node scripts/verify-release.mjs` before publication. It protects the original tools and ensures they are reachable from Home.

The service worker caches both Home and the original tools for offline use. It retires only Ops Hub caches. Home has a Check app update action and a reload notice when a newer installed cache is detected.

## Deployment

Publish all changed files together: `index.html`, `ops-saver.html`, `service-worker.js`, `VERSION`, `manifest.webmanifest`, `scripts/verify-release.mjs`, and this README. Existing icons and the verification workflow remain in place. Publishing updates the public app, so owner approval is required.

After publication, close and reopen the existing home-screen app and check the v1.5 badge. Do not clear site data or uninstall the app to force an update.
