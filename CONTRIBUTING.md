# Contributing

Thanks for looking. EliteLab is small on purpose: standard-library Python, no build step, modules that don't know about each other. Keep it that way and most contributions are easy.

## Set up

```
git clone https://github.com/ELITELAB_REPO.git
cd EliteLab
python -m unittest discover -s tests -v      # must pass before and after your change
python -m elitelab serve -v                  # run against your own journals
```

No virtualenv or dependencies needed. Node is only used in CI for `node --check`.

## Where things go

- A new feature is almost always a **new module** under `modules/<name>/`. Read [docs/MODULES.md](docs/MODULES.md); it's a 60-line job.
- Changes to the **core** (`elitelab/core/`) need a test in `tests/` and a note in `docs/ARCHITECTURE.md` if they change the module contract.
- The **shell** (`web/`) owns layout and the `Lab` runtime. Cards never touch layout.
- Game-data facts (internal commodity keys, star classes, Powerplay rules) go next to the code that uses them with a comment saying where they came from. The journal format is documented in Frontier's Player Journal manual.

## Rules of thumb

- Everything the server exposes should be an AI tool: register routes with `tool=` and write the description for a model.
- Don't block in bus handlers. Network calls go in a thread or in a request handler.
- Only write to your own store namespace.
- `esc()` anything from the journal or an API before putting it in HTML.
- Keep responses small; add parameters rather than returning everything.

## Tests

`tests/fixtures/journals/` is a synthetic journal. Add events there when you add parsing, and assert on the tool output rather than on internals. Tests run offline (`ELITELAB_OFFLINE=1`), so anything that needs Spansh or EDSM must degrade cleanly when the call fails.

## Pull requests

One topic per PR. Describe what you tested against a real journal if the fixture can't cover it. CI runs the tests on Linux and Windows, syntax-checks the scripts, and builds the Docker image.
