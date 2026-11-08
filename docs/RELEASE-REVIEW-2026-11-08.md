# Release integration review

Reviewed revisions were rechecked against GitHub before release integration:

| PR | Exact head | Disposition |
| --- | --- | --- |
| #108 | b3e6dd065318603197fa47174a08cfe70bb14f50 | Integrate installer profile fix; repair spawned-app smoke isolation from #116 |
| #109 | 1e0be9011b5f5fbfe0bbce65908dd53f7512c1a0 | Integrate browser/profile selection with #108; retain ordinary profile guard checks |
| #110 | 75a5689a3460128b6cecb8a3c4f7b9df84cf6fbd | Integrate material workflow/frozen requirements; add partial-quality correction from #111 and smaller default layout list |
| #112 | adbc07f95306d169a6664efe8a2775d9de4f27df | Integrate PTN/mining radius changes with fixes for contradictory scouting (#115) and long searches (#117) |
| #102 | 03533b7895d4c622bcdeb01b1127ed3e159eb4ab | Keep draft and excluded; domain prototype lacks the production enrollment/session/transport/UI boundary |
| #118 | ecd2ae913211bd7b7129abada9173f9e749fd1b4 | Preserve historical local work as a draft; do not merge older implementations over development |

The existing development blockers #113 (expired cookie streams) and #114
(authenticated MCP redirects) are fixed on the integration branch before the
feature changes. The original working checkout and running install are untouched.

Review focused on authorization/session boundaries, stale/contradictory market
evidence, background-job recovery, partial engineering, exact quantity and receipt
accounting, unknown costs, persistence failure, provider text escaping, saved
layout preservation and package allowlists. Group mining reuses the existing
authenticated party transport; it does not expose the draft hosted service.

The automated security review on #119 reported eleven findings. Each named
data flow was traced at 617c9ef: six inline reports were resolved with specific
escaping/numeric/static-template evidence; the remaining reports already have
resolved-path containment, escaped event attributes, fixed SQL column names with
bound values, or fixed commands and integer child-process arguments. The
[review disposition](https://github.com/MaverickArcane/EliteLab/pull/119#issuecomment-6724390892)
records the evidence. The generated patch deleting the HTTP server was rejected.
This is a disposition of those reports, not a claim of a complete security audit.

The new cargo search filters locally as well as at the provider, excludes mission
and stolen cargo, preserves unallocated quantities and reports heuristic scope.
Journal sales use a serialized writer outside the bus thread and retained receipt
deduplication. Credit history and shields preserve their evidence limits.

Validation results and CI links are maintained in [the execution record](NEXT-RELEASE-PLAN.md).
Real group play, reward eligibility, changing live markets, accessibility with a
screen reader and the release operator's final desktop installation checks are
not established by fixture tests. No release tag or public distribution is made
by this integration.
