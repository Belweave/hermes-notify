# Phone release workspace

## Direction

Two compositions were considered: a chronological release log and a release sheet with a current decision. The sheet wins because the person opening a phone notification needs the current state and next action before history. The shared contract has a snapshot, not a trustworthy event timeline.

- Purpose: inspect one release, find its evidence, answer with context, and move to native Notify when an approval is pending.
- Character: exact (measured progress only), legible (short rows and explicit status words), calm (no decorative animation or conversational feed).
- Composition: project and version, release status and measurement, current decision, checks, notes, artifacts, reply. One continuous record with ruled sections. At 880px, the reply sits in a separate right column; the record keeps its reading order. Maximum page width 1120px. Phone gutters 20px, wide gutters 40px.
- Type: official Paper Mono variable, 100 through 800, self-hosted. Body 15px/1.65, labels 12px/1.5, section headings 17px/1.4, release heading 28px to 40px/1.15. Monospace fallback. No other font family or icon font.
- Color: ground #f1f4f2, surface #ffffff, text #1e2d27, muted #56665d, rules #cbd5ce, accent #245c43, on-accent #ffffff. Focus #124e8c. Warning text #754609 on #faf3e4. Failure text #9a302d on #fff1ee. Success uses the accent with explicit words, never color alone.
- Shape and depth: open sections, 1px rules, a 3px decision edge, 4px control radii. No shadows or floating panels.
- Motion: essential content is immediate. Only control color transitions, 120ms ease-out; reduced motion disables transitions. Progress does not pulse or pretend to advance.
- Signature: the release version and measured progress form a compact release label; the current decision is a single annotated block. Checks are evidence rows, not editable todo items.
- Exclusions: generic card grids, fake history, invented progress, log transcripts, raw request identifiers, approval buttons, and a chat feed.

## Interaction and trust

The shipped shell contains no project fixture or release data. `/projects/{project}` supplies only the validated slug. The UI checks the cookie session before fetching the matching project. Authentication is delegated to the Worker-owned `/auth.js` `connect(project)` export. No token is stored or handled by the UI.

All app requests share one serial queue. Active snapshots poll after 10 seconds, unchanged snapshots back off to at most 60 seconds, and errors back off to at most 60 seconds. Hiding the page cancels its timer; returning refreshes once. Terminal snapshots stop polling. Explicit refresh remains available. Network timeouts bound each data request. Replies never retry automatically.

An uncertain reply keeps its exact ID, run, and text for a safe explicit retry. A successful receipt means the Worker saved it, not that Hermes already consumed it. A draft bound to an older run needs explicit review before reuse. Drafts and receipts live only in memory and are cleared on sign-out or session expiry.

Approval copy points to the native Notify inbox. The contract provides no verified per-request native deep link, so the UI uses the official Notify entry point and explains where to find the pending approval. A text reply cannot grant host permission.

## Assets

Paper Mono v1.0 and its license come from the [official download](https://paper.design/mono/download), linked by [paper.design/mono](https://paper.design/mono). `fonts/webfonts/PaperMono[wght].woff2` is self-hosted unchanged as `PaperMono-Variable.woff2`; SHA-256 is `57b28aaaffc46f85ed5b5adeda22bc7bce0fcdbf3e6f84850c327765fe6fdc6b`. The archive's `OFL.txt` is included as the [SIL Open Font License](public/fonts/LICENSE.txt). The permitted Portfolio font/license were inspected, but the final files are the official archive bytes. No Portfolio source, data, or secrets are used.
