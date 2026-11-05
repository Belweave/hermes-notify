# Official Notify SDK

`vendor/` contains the complete, unchanged `sdk/` directory from the public Notify Tools 0.14.2 release, plus its original root license, third-party notices, and dependency licenses. The initial read-only Portfolio copy supplied the microAuth pattern; all SDK files and notices in this tree were subsequently compared with the official release.

- Release: https://notify.belweave.ai/downloads/notify-tools/v0.14.2/notify-tools-0.14.2.tar.gz
- Archive SHA-256: `36f0b4bc7e5cc42d2463463ab3dc1e042560bbc63673743981bedbb5ab7eee71`
- Published checksums: https://notify.belweave.ai/downloads/notify-tools/v0.14.2/SHA256SUMS
- File hashes and source layout: [sdk-provenance.json](sdk-provenance.json)
- SDK license: [Apache-2.0](vendor/LICENSE)
- Included dependency licenses: [third-party notices](vendor/THIRD-PARTY-NOTICES.txt), including the bundled `jose` verifier's MIT license.

Production imports `createMicroAuthServer` and `createMicroAuthBinding` from the official `server.mjs`. The fixed official JWKS resolver comes from the release's bundled `jose` chunk, also used by `server.mjs`, so its cache is shared across sign-in attempts. This chunk filename is pinned with the release and must be reviewed during an SDK update.

The browser imports the official, standalone `browser.mjs` through `/vendor/notify/browser.mjs`. Only that browser entry and licensing material become public assets. Server code, connector code, and declarations remain in the source tree. No Notify CLI is executed.

To update, replace the whole SDK from a verified public release, retain all notices, update the file hashes, inspect any changed bundled imports, and rerun the isolated authentication and runtime tests. Do not edit generated upstream files. Upstream spelling and punctuation are preserved verbatim in vendored material.
