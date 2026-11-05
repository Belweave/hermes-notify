# Milestones to November 11

All dates are Eastern Time. Plan to **Wednesday, November 11, 2026 at 4 PM ET**, as Preetham requested, one hour before the brief's official 5 PM deadline. The public form's thank-you copy independently gives 1 PM PST, also 4 PM ET; the conflicting public text is documented in [RESEARCH.md](RESEARCH.md#marketplace-lessons-and-the-hackathon). Finish any authorized submission by 3 PM ET and reserve the final hour for verification and recovery. This phase authorizes local work only; publishing, remote pushes, a catalog PR, the entry form, and social posts need a later instruction.

| Date | Milestone | Exit condition |
| --- | --- | --- |
| Nov 4 | Research and working approval spike | Real Hermes loader and approval gate; mocked Notify HTTP round trip; denial and timeout tests; research, design, and source pins committed locally. Record mobile UI evidence: Desktop/Webapp supported, official native mobile UI contract unverified. |
| Nov 5 | One authorized phone test; settle App hosting | One real prompt answered and correlated in Hermes. Choose a public HTTPS hosting adapter and a concrete demo project. Confirm target phone capabilities and minimum Hermes build. |
| Nov 6 | Publish an App from Hermes | One tool deploys a versioned web app, verifies its URL, registers it in Notify, and pushes a deep link. Repeating the call updates the same App. Failures cannot announce an unavailable app. |
| Nov 7 | App becomes a useful project workspace | Add task progress, a project inbox, a persistent App screen, and a working reply path. Verify microAuth with the public SDK and a server-bound challenge if identity is needed. |
| Nov 8 | Native progress and event delivery | Live Activity start/update/end, correct fallback on unsupported phones, authenticated reply webhook receipt with polling reconciliation. Duplicate and late events cause no repeated action. |
| Nov 9 | Desktop and install polish | Minimal Desktop/Webapp panel for Apps, runs, and pending decisions; configuration and disconnect flow; CLI-independent install; optional official Notify MCP and CLI setup documented. Test with CLI absent. No dependency on native Hermes mobile plugin rendering. |
| Nov 10 | Freeze and rehearse | Run reliability matrix and catalog validator on the exact candidate tree. Document all network/storage behavior. Capture an 80 to 85 second demo and leave room for trimming. Rehearse a fresh install and a failed-network recovery. |
| Nov 11, by noon | Final candidate | Clean-install check, README, screenshots, license, pinned dependencies, video under 90 seconds, no secrets in the archive, all entry fields prepared locally. |
| Nov 11, 1 to 3 PM | Submission window, only if authorized | Publish the chosen repository and pinned candidate; open the catalog PR; publish the under-90-second demo post; submit the form with both links. Verify receipts before the 4 PM planning cutoff. |
| Nov 11, 3 to 4 PM | Final verification buffer | Confirm the video plays, links resolve, the form receipt exists, and the exact catalog pin is available. Use this hour for recovery, not first uploads. |

## Critical path and cuts

The critical path is an authorized phone test, reachable HTTPS App hosting, deterministic App publication, and a complete short demo. A pretty panel cannot compensate for a failed phone round trip.

If hosting is unresolved on November 5, use a pre-provisioned HTTPS demo site and demonstrate registering and updating that real App. Label this accurately; do not call registration hosting. If microAuth blocks the schedule, demonstrate an App with non-sensitive sample data and leave sign-in as an explicitly unfinished integration. If the target phone cannot show a Live Activity, use an ordinary progress notification and state the limitation.

Cut first: team administration, on-call flows, connector setup, offline Mini Apps, and a second hosting provider. Keep their supported Notify interface paths in documentation. Keep the App publish path, one exact approval, replies, project routing, and graceful failures. The entry should make one complete workflow look effortless.

## Three decisions for Preetham

1. Can the next session send one real approval to the selected phone, using an existing scoped Notify token from env or the OS keychain?
2. Which HTTPS host should Hermes publish Apps to, and should the first version support existing sites as well as newly generated ones? Recommendation: one existing hosting account plus a bring-your-own-URL path.
3. Is a release workspace the right flagship demo, or would a personal workflow better represent the product? Recommendation: a release workspace with a useful interactive App, live progress, and one approval that visibly changes its state.
