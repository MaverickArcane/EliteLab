# Contributing

This is a hobby project, built with AI assistance, and you are welcome to do whatever you like with it. The notes below are only there so changes keep working with each other. EliteLab is small on purpose: standard-library Python, no build step, modules that do not know about each other. Keep it that way and most contributions are easy.

## Set up

```
git clone https://github.com/MaverickArcane/EliteLab.git
cd EliteLab
python -m unittest discover -s tests -v      # should pass before and after your change
python -m elitelab serve -v                  # run against your own journals
```

No virtualenv or dependencies needed. Node is only used in CI for `node --check`.

## Where things go

- A new feature is almost always a new module under `modules/<name>/`. Read docs/MODULES.md; it is a short job.
- Changes to the core (`elitelab/core/`) need a test in `tests/` and a note in docs/ARCHITECTURE.md if they change the module contract.
- The shell (`web/`) owns layout and the `Lab` runtime. Cards never touch layout.
- Game-data facts (internal commodity keys, star classes, Powerplay rules) go next to the code that uses them with a comment saying where they came from. The journal format is documented in Frontier's Player Journal manual.

## Rules of thumb

- Everything the server exposes should be an AI tool: register routes with `tool=` and write the description for a model.
- Do not block in bus handlers. Network calls go in a thread or in a request handler.
- Only write to your own store namespace.
- `esc()` anything from the journal or an API before putting it in HTML.
- Keep responses small; add parameters rather than returning everything.
- Plain text in docs and UI. No emojis.

## Tests

`tests/fixtures/journals/` is a synthetic journal. Add events there when you add parsing, and assert on the tool output rather than on internals. Tests run offline (`ELITELAB_OFFLINE=1`), so anything that needs Spansh or EDSM must degrade cleanly when the call fails.

## Branches

- `main` is what people run. It only changes through a pull request from `development` with green CI; no direct pushes, no force pushes, no deleting it.
- `development` is where work lands first. Branch from it (`git checkout -b my-change development`), open your PR against it, and it goes to `main` in the next release PR.
- CI runs on pushes to `main` and `development` and on every pull request.

## Pull requests

One topic per PR. Say what you tested against a real journal if the fixture cannot cover it. CI runs the tests on Linux and Windows, syntax-checks the scripts, and builds the Docker image.
