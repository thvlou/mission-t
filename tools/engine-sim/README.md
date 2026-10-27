# Engine recordings

The car engines in `assets/audio/engines/` are recorded from [engine-sim](https://github.com/Engine-Simulator/engine-sim-community-edition)
by AngeTheGreat, a physical combustion-engine simulator, held on its dynamometer at fixed RPMs.

| Car | Engine script |
|---|---|
| GT | `engines/gt.mr` (stock F136 V8; + turbo whoosh in the game) |
| Arc | `engines/flat6.mr` (4.0 flat-six, generated) |
| Apex | `engines/v12.mr` (6.5 high-revving V12 from the 412 T2 script, generated) |
| Grand | `engines/grand.mr` (6.0 heavy, low-revving V12 from the 412 T2 script, generated; + twin-turbo whoosh in the game) |
| Terra | `engines/terra.mr` (stock GM LS V8; + supercharger whine in the game) |
| R | `engines/r.mr` (stock LFA V10) |

## Redo the recordings (Windows)

1. Unzip `engine-sim-v0.1.14a.zip` from the community edition's releases into `tools/engine-sim/engine-sim-v0.1.14a/`.
   The older 0.1.11a build crashes a few seconds after start on some PCs and only reads raw keyboard input.
2. `node tools/engine-sim/gen-engines.mjs` writes the six engines into it. Each runs at a simulation rate
   this PC keeps up with: when engine-sim falls behind real time (RT/DT over 100%) the recording repeats
   or stutters. A W16 (`engines/w16.mr`) is also written but needs more than this PC can simulate live.
3. Build the loopback recorder: `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe -out:tools\engine-sim\rec.exe tools\engine-sim\rec.cs`
4. Turn every other sound off (the recorder captures the whole playback device), then from PowerShell:
   `python tools/engine-sim/record_all.py takes` (about 15 minutes, all six cars; add car ids to redo some).
   engine-sim windows open and close by themselves, small and on top in the corner (a covered window gets
   throttled); keys go to them by window message, so the PC stays usable.
5. `node tools/build-engine-audio.mjs tools/engine-sim/takes` cuts the loops and writes `engines.json`.
