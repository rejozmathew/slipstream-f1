# Tools

This directory is reserved for one-off inspection, migration, and validation helpers that are not part of the installed `slipstream` command.

Runtime acquisition belongs in `src/slipstream` and should be exposed through the CLI. Keep downloaded recordings under the ignored `recordings/` directory. Never place credentials, cookies, `.env` files, authenticated captures, or protected provider payloads in `tools/`.

A helper promoted into a supported workflow should move into the package, gain tests, and be documented through `slipstream --help` rather than remaining an undocumented script.
