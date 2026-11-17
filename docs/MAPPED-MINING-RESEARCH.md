# Mapped asteroid mining plan

Future PR scope, reviewed 2026-11-17. Build a local visual route book that helps
single-screen players reproduce a mining route: an entry picture, orientation
cues, numbered reference views, expected composition and explicit confirmation.
The shared overlay can present this alongside its existing surface navigation
mode. Mapped mining remains separate from the current overlay redesign.

## Telemetry and orientation

Frontier's [journal manual v38](https://hosting.zaonce.net/community/journal/v38/Journal_Manual_v38.pdf)
documents composition, material content, remaining percentage and optional core
material for `ProspectedAsteroid` (section 13.33). It supplies neither asteroid
identity nor position. `Status.json` supplies surface coordinates and heading
near planets, but no local ring XYZ or complete space attitude. `Screenshot`
supplies a filename, image dimensions, system and nearest body; its geographic
fields are restricted to surface or low-altitude flight (section 6.18).
These documented inputs cannot produce a trustworthy bearing to a mapped rock.
Verify the pilot's actual journal against this contract before implementation.

EliteLab already exposes the latest composition report through
`mining.last_prospect`; see [mining/module.py](../modules/mining/module.py).
Its report counter counts events, not distinct rocks. Multiple prospectors and
repeated observations make automatic screenshot-to-rock association ambiguous.
Show the report timestamp and require the player to attach it to a route step.
Preserve normalized commodity keys as well as display names in the new module;
the existing summary primarily keeps localized labels.

A route needs a reproducible starting viewpoint and roll reference. Record the
selected hotspot or RES label, the ring side, a planet/sky landmark, the visible
target-compass arrangement and any manually read distance. Identical hotspot
names need an identifying DSS-view screenshot. Preserve each cue's origin as
player-entered, image annotation or journal observation.

This approach has a practical precedent: [cold-n-sour's mapped route](https://www.reddit.com/r/EliteMiners/comments/jft5vo/psa_asteroid_map_for_painite_hotspot_in_dubuennel/)
uses a starting planet/hotspot alignment, a sky reference for up, the in-game
target compass and views taken from preceding rocks. Its author notes that the
ring's opposite side mirrors the approach. Treat that as a workflow example,
not a current yield forecast or validation of a particular route.

## First implementation

1. Add a `mapped_mining` module with its own state and persistent library.
   Create independent books even when system, body, ring and mineral match.
   Distinct routes and same-mineral hotspots must not silently merge.
2. Record an entry reference and ordered steps. Accept local screenshots,
   short instructions, target circles/arrows and optional composition reports.
   Keep originals immutable; annotations are editable normalized image
   coordinates. Include the preceding rock in the view when useful.
3. Replay a compact reference image with `Rock 3 of 5`, the next instruction,
   expected composition, and Previous, Next, Confirm and Lost actions. Provide
   an enlarged reference on demand. A basic record/next binding should work
   without shifting focus away from the game; retain visible controls too.
4. Advance only through player action. A composition agreement can suggest
   confirmation but cannot establish unique identity. Lost restores the last
   confirmed viewpoint and its orientation notes. Skipping a step must expose
   which earlier viewpoint the next picture requires.
5. Reuse the overlay's transparency, pin, move, scale and input-lock behavior.
   Show `Reference view` or `Awaiting confirmation`; surface `On course` and
   numerical steering do not apply to this mode. Keep the selected provider
   stable across automatic state updates.

Start capture with the game's screenshot event or an explicitly selected local
image. Resolve event filenames only beneath a configured screenshot directory,
wait for a complete file in a bounded worker, then copy into the library. Replayed
journal events must never trigger capture or create steps. The pilot must confirm
the actual path, image format and whether game screenshots exclude the overlay;
retain file selection if automatic association cannot be made reliably.

For a later direct-capture shortcut, EDMM demonstrates targeting the Elite
process and using Windows `PrintWindow`, with minimized/missing-window handling.
Its implementation requires windowed/borderless mode. This is a prototype to
validate against EliteLab's rendering setup, not a guarantee across renderers.
Microsoft documents `PrintWindow` as synchronous, so it must stay outside the
journal watcher and UI threads. Use bounded workers and report failures without
saving blank captures. See [EDMM capture](https://github.com/Kailoren/EDMM/blob/af5b15df96bac6294abc83e547268585fc6092af/src/capture/screenshot.ts)
and [Microsoft's API contract](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-printwindow).

## Proposed stored data

Use a versioned book plus a separate replay session. IDs below are local
document identifiers; they never claim to be game asteroid IDs.

| Record | Fields |
|---|---|
| Book | `schema_version`, `id`, `title`, `created_at`, `updated_at`, `author`, `source`, `attribution`, `steps` |
| Site | `system_name`, optional observed `system_address`, `body_name`, `ring_name`, `mineral_key`, `entry_notes`, `entry_image_id` |
| Capture profile | image width/height, crop rectangle, ship/camera description, optional player-supplied FOV, game version, display mode |
| Step | `id`, ordered position, `from_step_id`, `instruction`, image IDs, annotations, orientation cues, optional confirmed prospect observation |
| Image | generated local filename, content hash, format, dimensions, capture timestamp, original/annotated role, import provenance |
| Prospect observation | event timestamp, session identity, raw and normalized material names, proportions, remaining, content, core material, `attached_by_user` |
| Orientation cue | landmark kind/label, instruction, optional observed distance and unit, source, observation time |
| Replay session | book revision, commander/session, current and last-confirmed step, per-step confirmed/skipped status, paused/lost state |

Store annotations in the original image's normalized coordinate space and apply
the same crop/letterbox transform when displaying them. They indicate places in
the reference picture, not locations fixed in the live game world. Store
unknowns as null or absent. Do not create yaw/pitch/roll, ring coordinates or
asteroid IDs from composition, event count or screenshot pixels.

A generic overlay provider needs a title, activity/status, instruction, optional
metrics, reference image/caption, source time and available actions. Keep
`surface_bearing` and `reference_image` as distinct guidance kinds. This allows
future mining, surface, travel and checklist providers to share window controls
without claiming that all activities have directional telemetry.

## EDMM interoperability

The reviewed [EDMM source snapshot](https://github.com/Kailoren/EDMM/tree/af5b15df96bac6294abc83e547268585fc6092af)
exports `*.streamdeckbook.zip` containing `manifest.json`, `images/<number>.png`
and `index.html`. The manifest contains `starSystem`, `body`, `ring`, optional
`mineral`, `publishedAt`, and ordered `shots` with `file`, `capturedAt`, `note`.
Import that ordered list into a new EliteLab book and preserve provenance.
No Stream Deck installation is needed to read the archive format. See
[publisher](https://github.com/Kailoren/EDMM/blob/af5b15df96bac6294abc83e547268585fc6092af/src/dashboard/publish.ts)
and [published schema](https://github.com/Kailoren/EDMM/blob/af5b15df96bac6294abc83e547268585fc6092af/src/dashboard/publishedViewer.ts).

The exporter prefers an annotated image when available and writes it under the
original image filename. Shared books therefore do not preserve editable
annotation geometry or guarantee clean original images. Imported steps must
retain the flattened image and leave missing pose/prospect data unknown.
EDMM's local `book-manifest.json` is a different artifact; support published ZIPs
first. Its [local manifest](https://github.com/Kailoren/EDMM/blob/af5b15df96bac6294abc83e547268585fc6092af/src/store/bookManifest.ts)
and [importer](https://github.com/Kailoren/EDMM/blob/af5b15df96bac6294abc83e547268585fc6092af/src/store/importBook.ts)
show the distinction. Export compatibility can follow after import fixtures
establish the supported format.

Read only the validated manifest and referenced images. Never execute or serve
the archive's HTML/scripts. Use generated destination names, reject traversal,
absolute/device paths, links and ambiguous duplicate entries, and cap archive
size, entry count, decompressed bytes, image dimensions and processing time.
Validate all entries before an atomic import. Hash duplicate books for a visible
import choice; never merge solely on system/body/ring. Render notes as escaped
text and keep any source URL as provenance, without fetching it automatically.

EDMM uses the [MIT License](https://github.com/Kailoren/EDMM/blob/af5b15df96bac6294abc83e547268585fc6092af/LICENSE),
copyright 2026 Kailoren. Preserve its copyright and permission notice if copying
code or substantial portions. The repository license does not establish the
redistribution permissions of every player-authored screenshot book; preserve
author/source attribution and keep initial imports local.

## Later visual assistance

After manual replay works, experiment with user-selected landmarks, local
feature matches and short-term image tracking. OpenCV's
[feature matching example](https://docs.opencv.org/4.13.0/d1/de0/tutorial_py_feature_homography.html)
rejects insufficient matches, and its
[optical-flow documentation](https://docs.opencv.org/4.13.0/d4/dee/tutorial_optical_flow.html)
states brightness and neighboring-motion assumptions. In a mining scene,
rotation, parallax, lighting, lasers and occlusion can invalidate such matches.
This makes a persistent world marker an experimental feature, not a dependency
of route books.

Gate any marker on measurable match quality and hide it immediately on tracking
loss, camera changes or stale frames. Reacquisition requires user confirmation.
Record false matches and loss/recovery times before choosing thresholds. Full
3D mapping, numeric space bearings, automatic rock identification and automated
flight remain outside the first PR. A computer-vision package would also need a
separate dependency decision under EliteLab's standard-library policy.

## Pilot and acceptance checks

Record five nearby laser-mining rocks in one ring using the same ship, camera
and display geometry. Save a DSS entry picture, a reproducible starting view,
two orientation cues, each approach from a named prior viewpoint, and manually
confirmed fresh prospect observations. Replay after leaving and returning;
then have a second player follow the book without spoken guidance. Include a
deliberate wrong turn and recovery to the last confirmed step. Record time to
find each rock, wrong identifications, recovery time and interaction/focus
problems. Capture the actual journals and redacted screenshots as fixtures.
Do not infer replenishment timers or route availability from this pilot.

The first PR should pass:

- Replay tests for ordered views, branches/shared viewpoints, undo/skip,
  interrupted saves, resumed sessions, and zero automatic advancement.
- Evidence tests for stale/missing prospects, multiple prospectors, repeated
  identical compositions, commander changes and journal replay.
- Capture tests for partial files, path escapes, unsupported/oversized images,
  missing/minimized game, blank capture and no accidental desktop capture.
- EDMM import tests for plain and flattened annotated images, missing images,
  unversioned/unknown fields, duplicate names, malformed manifests, ZIP bombs,
  path attacks and script/HTML exclusion; existing books remain unchanged on
  failure. These apply when the importer is included.
- Overlay checks for image fitting at multiple DPI/aspect ratios, readable
  transparent text, hotkey conflicts, lock/unlock recovery, game focus, and
  lost/disconnected states that retain reference material without live claims.

Priority order: local record/replay and the five-rock pilot first; EDMM import
next (same PR only if it stays small); direct capture and richer annotations
after the pilot; visual tracking in a separate experimental proposal. Use the
existing `mining` module for production totals, keep new state in
`mapped_mining`, expose bounded tools, and run all tests on isolated data and
ports. This plan does not require changing the running installation.
