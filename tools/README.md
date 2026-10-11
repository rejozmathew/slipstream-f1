# Tools

This directory is reserved for one-off inspection, migration, and validation helpers that are not part of the installed `slipstream` command.

Runtime acquisition belongs in `src/slipstream` and should be exposed through the CLI. Keep downloaded recordings under the ignored `recordings/` directory. Never place credentials, cookies, `.env` files, authenticated captures, or protected provider payloads in `tools/`.

A helper promoted into a supported workflow should move into the package, gain tests, and be documented through `slipstream --help` rather than remaining an undocumented script.

## Story and analytics prefix validation

`validate_story_recording.py` compares the canonical state, complete Story ledger at the cursor, and analytics built from a full recording with the same outputs built from a physically truncated event prefix. It is read-only and writes no recording data or report files.

```powershell
$env:PYTHONPATH = "src"
python tools/validate_story_recording.py output/recordings/f1-static-11342.json
```

The default nine offsets target the Hungarian review checkpoints. The origin is the first observed RUNNING session event at or after the declared start. Use `--start` for an explicit ISO timestamp and `--offsets` for other recordings; see `--help`. Each line reports a cursor verdict, followed by an aggregate result. Any mismatch raises an assertion and produces a failing exit code. A pass proves the tested prefix comparisons; it does not certify every story interpretation. See [Story](../docs/story.md) for the model and its limits.
