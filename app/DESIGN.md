# Phone release workspace

## Direction

Two compositions were considered: a chronological release log and a release sheet with a current decision. The sheet wins because the person opening a phone notification needs the current state and next action before history. The shared contract has a snapshot, not a trustworthy event timeline.

- Purpose: inspect one release, find its evidence, answer with context, and move to native Notify when an approval is pending.
- Character: exact (measured progress only), legible (short rows and explicit status words), calm (no decorative animation or conversational feed).
- Composition: project and version, release status and measurement, current decision, checks, notes, artifacts, reply. One continuous record with ruled sections. At 880px, the reply sits in a separate right column; the record keeps its reading order. Maximum page width 1120px. Phone gutters 20px, wide gutters 40px.
- Type: official Paper Mono variable, 100 through 800, self-hosted. Body 15px/1.65, labels 12px/1.5, section headings 17px/1.4, release heading 28px to 40px/1.15. Monospace fallback. No other font family or icon font.
- Color: ground #f7f8f5, surface #ffffff, text #242923, muted #586252, rules #cdd3c9, accent #245c43, on-accent #ffffff. Focus uses the same accent. Status and error words carry meaning on the neutral ground; success can use the accent. Every text and placeholder color meets at least 4.5:1 contrast.
- Shape and depth: open sections, 1px rules, no filled callout panels, 4px control radii. No shadows or floating panels.
- Motion: essential content is immediate. Only control color transitions, 120ms ease-out; reduced motion disables transitions. Progress does not pulse or pretend to advance.
- Signature: the release version and measured progress form a compact release label; the current decision leads the evidence column, separated by a hairline rule. Checks are evidence rows, not editable todo items.
- Exclusions: generic card grids, fake history, invented progress, log transcripts, raw request identifiers, approval buttons, and a chat feed.

## Interaction and trust

The shipped shell contains no project fixture or release data. `/projects/{project}` supplies only the validated slug. The UI checks the cookie session before fetching the matching project. Authentication is delegated to the Worker-owned `/auth.js` `connect(project)` export. No token is stored or handled by the UI.

All app requests share one serial queue. Active snapshots poll after 10 seconds, unchanged snapshots back off to at most 60 seconds, and errors back off to at most 60 seconds. Hiding the page cancels its timer; returning refreshes once. Terminal snapshots stop polling. Explicit refresh remains available. Network timeouts bound each data request. Replies never retry automatically.

An uncertain reply keeps its exact ID, run, and text for a safe explicit retry. A successful receipt means the Worker saved it, not that Hermes already consumed it. A draft bound to an older run needs explicit review before reuse. Drafts and receipts live only in memory and are cleared on sign-out or session expiry.

Approval copy points to the native Notify inbox. The contract provides no verified per-request native deep link, so the UI uses the official Notify entry point and explains where to find the pending approval. A text reply cannot grant host permission.

## Assets

Paper Mono v1.0 and its license come from the [official download](https://paper.design/mono/download), linked by [paper.design/mono](https://paper.design/mono). `fonts/webfonts/PaperMono[wght].woff2` is self-hosted unchanged as `PaperMono-Variable.woff2`; SHA-256 is `57b28aaaffc46f85ed5b5adeda22bc7bce0fcdbf3e6f84850c327765fe6fdc6b`. The archive's `OFL.txt` is included as the [SIL Open Font License](public/fonts/LICENSE.txt). The permitted Portfolio font/license were inspected, but the final files are the official archive bytes. No Portfolio source, data, or secrets are used.


## Paper reference refinement

Reviewed [Paper](https://paper.design/) and [Paper Mono](https://paper.design/mono) on November 4, 2026 ET. This is an operation surface: opening a release and acting on its evidence. Keep the release sheet, deliberate type sizes, open space and aligned columns. Use the references' clear alignment and restrained controls; do not copy their promotional text or decorative effects.

- Removed repeated labels above headings, decorative section numbers, symbol substitutes and the footer slogan. Section titles and real state words provide the hierarchy. The project path remains a functional location label.
- Relaxed heading tracking to -0.03em and version tracking to -0.02em. All controls, including native inputs, selects, options and placeholders, explicitly inherit Paper Mono. Font weight stays within the official 100-800 variable range.
- Replaced thick colored decision/receipt edges and warm status panels with 1px rules and neutral surfaces. The single green accent handles actions, progress, focus and success. Carets, selection and scrollbars use the same palette.
- Kept 20px phone gutters, the 880px column change and 1120px maximum width. At a 900px iPhone Duo inner width, evidence and reply occupy separate aligned columns. At 320-430px they read as one column, with at least 44px action targets.
- Replaced the invented header mark and favicon with the official Nous Research woman mark. Notify uses its official mark beside connection and action labels. Both are self-hosted, with original bytes and aspect ratios; see [logo provenance](public/logos/PROVENANCE.md).
- Empty sections explain which evidence is missing and ask the user to have Hermes publish it. A project with no snapshot has a distinct empty state. Root, unknown routes and server errors share the same stylesheet, official font, marks and concrete recovery actions.

## Worker-owned surfaces

The production Worker serves the root shell explicitly. Browser document requests that fail receive a fixed-copy HTML recovery page; API and authentication requests retain JSON even when they advertise HTML. No request path, exception detail, identity or project data is interpolated into a recovery page. HEAD responses have no body.

Four inert assets (the stylesheet, font and two marks) remain public even if canonical-origin configuration is invalid, so that its error page can still render. Executable scripts, SDK assets, HTML documents and private routes still require the original origin check. The same no-store, no-referrer, content-type and content-security headers apply to every public HTML response.

The auth connector has no independent UI. Its fixed, sanitized messages render in the app's normal gate. The browser tests exercise the actual built `/auth.js` and official browser SDK in an unsupported browser, alongside the mocked session exchanges needed to cover private states without credentials.
