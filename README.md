# Ops Hub

Local-first Operations & AI Systems home-screen PWA.

## Release rule

`VERSION`, the visible version badge in `index.html`, and the service-worker cache version must always match. The automated release verifier also protects the StudyHelpAI Live shortcut and Worker Bench from accidental regression.

For an Ops Hub change:
1. Start from the current live `main/index.html` rather than an older standalone copy.
2. Make the bounded change.
3. Bump `VERSION`, the visible `vX.Y` badge, and `CACHE="ops-hub-vX.Y"`.
4. Let `scripts/verify-release.mjs` / GitHub Actions verify consistency.
5. After deployment, reopen the installed PWA and confirm the new version badge.

Keep Ops Hub lean. Add workers or automation only after real repetition justifies them.
