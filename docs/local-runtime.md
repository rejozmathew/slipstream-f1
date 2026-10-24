# Local runtime and source selection

Start both development servers from the repository you intend to edit:

```powershell
./tools/start-local.ps1 -DataRoot 'C:\GitClone\slipstream-f1\recordings' -PythonExecutable 'C:\Python314\python.exe'
```

Choose the existing recording directory for your device. The launcher derives
the Python source and Vite working directory from its own repository, verifies
the imported Python module, and records the directory, branch, commit and PIDs
in `.codex-tmp/local-runtime/processes.json`. It refuses occupied ports instead
of silently connecting a new frontend to an older backend. Inspect the existing
process before stopping it, especially during a live recording. Logs share that
runtime directory. Install Python dependencies and run `npm ci` in `web` first.

On October 24, 2026, US qualifying was served from an older copied checkout with
a dangling Git worktree pointer. It lacked the Singapore motion and whole-session
completion changes already merged into main. Q1 was prematurely finalized; the
journal was recovered and the patched process remained live after Q2 finished.
Consolidation restored the latest main, preserved the calendar feature and capture
tools, and added unequal mini-sector inventory and qualifying recovery regressions.
Historical source snapshots and experimental branch refs were preserved locally.

Track motion follows received progress along the actual circuit geometry, using
each car's observed cadence. Mini-sector recolouring is not movement. Long source
gaps can still make cars slow or stop: the display does not invent future positions.
Car circles stay at those path positions and use a uniform radius. When symbols
overlap, connected driver labels move for readability; car circles do not move
sideways off the track. Only explicitly followed drivers receive a distinct
outline; neighbours are not automatically highlighted and other cars are not dimmed.
Regression checks cover corners, hairpins, chicanes, irregular shapes, rotations,
lap crossings and unequal mini-sector inventories without circuit-specific code.
