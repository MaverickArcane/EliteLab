# Publishing an EliteLab beta

`development` holds ongoing work. `staging` is the group playtest branch. A beta
release is an immutable-by-convention numbered snapshot from staging, published
with GitHub's prerelease flag. Stable release publication stays separate.

1. Integrate the selected changes into staging. Set `elitelab.__version__` to
   `X.Y.Z-beta.N` with a new positive beta number. Never reuse or move a beta tag.
2. Add `docs/releases/X.Y.Z-beta.N.md` with exact versioned asset links, changes,
   known limitations, upgrade instructions and feedback guidance. Update the
   README and staging guide's beta links. Keep stable release links separate.
3. Run the relevant checks and push staging. Wait for its CI to pass.
4. Tag that exact reviewed commit: `git tag -a vX.Y.Z-beta.N -m "EliteLab X.Y.Z Beta N"`.
   Push the tag. This explicitly publishes a prerelease after automated checks.
5. The Beta release workflow validates version/tag/notes and staging ancestry,
   runs the complete reusable CI, downloads all five native/portable packages,
   verifies their exact file set and checksums, versions the Windows filenames,
   creates a source archive and consolidated checksums, then publishes the release.
6. Inspect the published release, download links, package identities and checksums.
   Share the release page with testers. Do not use `/releases/latest` for betas.

Publication uses a draft until all assets upload, then sets prerelease true and
latest false. A partial publication failure leaves a draft for inspection; do not
blindly rerun or overwrite existing assets. Inspect the failed step and draft,
finish only if all assets match the tested tag, or prepare a new numbered beta.
Workflow dispatch is for a matching existing beta tag, not a moving branch.

The stable release workflow excludes beta tags and continues producing drafts
for stable version tags. These workflows do not merge staging into main.

The application, health endpoint and diagnostics retain the full beta version.
Debian control metadata maps `-beta.N` to `~beta.N` so stable sorts after beta.
Windows numeric file metadata and macOS native/package metadata use the numeric
target version; visible Windows AppVersion and package filenames retain beta.
Native installers keep their existing application identity. Use the portable
staging launcher or source staging command for isolation from normal saved data.
