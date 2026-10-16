# S4 stop runbook

**For the owner, at the end of the S4 live run (M5m P123, R-DB).** It is a procedure and it asserts no result:
`docs/S4_PREREGISTRATION.md` (which this file does not edit and does not restate) says what is computed and what each
figure is held against, and `scripts/s4_compare.py` prints figures and no verdict. Everything here uses T0
`2026-10-10T06:05:20Z` (`docs/RUN_LEDGER.md` section 43, corrected at section 57) and only procedures already measured
on this machine, **and where a command has not been, it is marked N below and listed in the table at the end.**

R-DB, verbatim: *"The S4 stop is done from docs/S4_STOP_RUNBOOK.md: stopping the bot, the final freeze and recorder run,
the store frozen from the recorder clone by hash, the backtest clone built outside deploy\ with no .env, the backtest of
[W, M) through config.s4.yaml, and the frozen comparison, each step with its CHECK, using T0 2026-10-10T06:05:20Z and
only procedures already measured on this machine."*

## How to read a step

- **Measured:** the earlier run on this machine that executed the procedure, by `docs/RUN_LEDGER.md` section (the
  ledger is an observation log, so the section is the evidence). A procedure measured in a *related* form says so.
- **Never executed:** the commands of the step that no run has executed in the form written. A step with such a
  command is not blocked by it; it is the place to look first if the step's CHECK fails.
- **CHECK:** what the step prints or what a command returns when the step is right. Each CHECK is its own command,
  and none is piped into a verdict (`CLAUDE.md`, the pipe rule). **Stop and report if a CHECK does not hold.**
- Every PowerShell line below is ONE line, complete on its own: paste it as it stands.
- Everything the steps write goes under `F:\trading bot\scratch\s4stop\<M>\` or the frozen store named in step 5,
  never into a clone. **Nothing in the S4 clone `F:\trading bot\deploy\45547f107715` is opened for writing, and no
  step runs any program of it** (its log is read only through `scripts\s4_daily.py`'s share-mode copy).
- No step writes to the venue. Step 2's account check reads it.

## The facts every step uses

| name | value | where it comes from |
|---|---|---|
| `T0` | `2026-10-10T06:05:20Z`, the `run` boot of pid 16076 | RUN_LEDGER sections 43 and 57 |
| `W` | `2026-10-11`, the first UTC midnight at or after `T0` | S4 pre-registration section 4 |
| `M` | the stop midnight, a UTC date, **set by the owner** in step 1 | S4 pre-registration section 3 (R-AY) |
| earliest `M` | `2026-11-01` (the first UTC midnight at or after `T0` + 21 days) | derived, RUN_LEDGER section 43 |
| cap | `2026-11-14T06:05:20Z` (`T0` + 35 days); at the cap `M` is `2026-11-14T00:00:00Z` (R-DD) | derived; ruled at P124, see step 1 |
| S4 commit | `45547f10771543b41db42e1cbcb8b5a0a9cf1776` | the run's `boot_provenance` line |
| frozen scripts | `s4_compare.py` `b8afa603...af08`, `trade_census.py` `926bdd46...d9bb`, `config.s4.yaml` `0f170bae...2594` | pre-registration section 9; the same bytes at `HEAD` and at `45547f1` (P123) |

## Step 0. The variables (once per PowerShell window)

Set `$M` to the stop midnight's date. Everything below reads these names.

```powershell
$M = '2026-11-01'
$W = '2026-10-11'
$DEV = 'F:\trading bot\files\binance-trading-bot\binance-trading-bot'
$DEVPY = "$DEV\.venv\Scripts\python.exe"
$RCLONE = 'F:\trading bot\recorder\45547f107715'
$RPY = "$RCLONE\.venv\Scripts\python.exe"
$RSTORE = "$RCLONE\data\historical_testnet"
$SHA = '45547f10771543b41db42e1cbcb8b5a0a9cf1776'
$S = $SHA.Substring(0, 12)
$BT = "F:\trading bot\backtest\$S"
$PY = "$BT\.venv\Scripts\python.exe"
$FROZEN = "F:\trading bot\store\testnet-s4-$M"
$OUT = "F:\trading bot\scratch\s4stop\$M"
New-Item -ItemType Directory -Force $OUT
```

Never executed: the assignments and `New-Item` as a block (each is a single trivial statement; `$S` and the
paths are the ones RUN_LEDGER sections 43 and 52 to 54 name). CHECK: `"$M $W $S"` prints your date, `2026-10-11` and
`45547f107715`.

## Step 1. Decide the stop (before `M`)

**Measured:** `scripts\s4_daily.py`, section 58 (run once against the live run, exit 0).

```powershell
Set-Location $DEV
& $DEVPY scripts\s4_daily.py
```

The stop rule (R-AY) stops the run at the FIRST UTC midnight `M` at which BOTH hold: `M` is at least `T0` + 21 days
(`2026-11-01T00:00:00Z` or later) and at least 150 bookings have been made since `T0`. The report's last section
states each condition as a fact. CHECK, on the evening before: `both conditions met at the next UTC midnight on the
bookings so far : yes` and `next UTC midnight` is the date you set in `$M`. If it reads `no`, the run goes on and you
repeat this step the next day; `bookings >= 150 now` can turn from `no` to `yes` during the day, and bookings only
increase, so a `yes` at the evening stands at the midnight.

**THE CAP, AS R-DD RULES IT.** R-AY caps the run at `2026-11-14T06:05:20Z`, "evaluated if at least 100 bookings exist
and otherwise NOT MEASURED", and the comparison window is `[W, M)` with `M` a whole UTC midnight (pre-registration
section 4). R-DD, verbatim: *"If S4 reaches its cap, M is 2026-11-14T00:00:00Z, the last UTC midnight at or before the
cap. Bookings after M are outside the comparison window. This is ruled before any S4 result exists (M5m-538)."* So if
the cap is reached before step 1 reads `yes`, set `$M = '2026-11-14'`, stop the bot AT THE CAP
(`2026-11-14T06:05:20Z`, not at `M`), and run the steps with that `$M`: the bookings made between `M` and the stop are
in the log and outside the window, and the backtest ends at `M`. S4 is then evaluated only if at least 100 bookings
exist, and is otherwise NOT MEASURED (R-AY); step 9's arithmetic says which.

## Step 2. Stop the bot, gracefully, at `M`

**Measured:** the bot's graceful stop by `SIGINT` (Ctrl+C in the window its `run` is in): RUN_LEDGER section 46 (pid
16076, `Received SIGINT; shutting down gracefully` at `2026-10-12T04:17:41Z`, `engine_stopped clean_shutdown=True` at
`04:17:43Z`), and sections 21, 25 and 26 for earlier ones. The process check is the `Win32_Process` filter of
`CLAUDE.md` (the "no bot is running" check, P87) and the one `scripts\s4_daily.py` makes. The account check:
`scripts\check_testnet.py`, section 40 (before and after the clearing) and section 46 (after the 10-12 shutdown).

At `00:00:00Z` of `$M` (or as soon after as you can; the window cuts the entries and a few minutes decide nothing),
press **Ctrl+C once** in the window the S4 `run` is in. Do not close the window and do not kill the process.

```powershell
[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' } | Select-Object ProcessId,CommandLine | Format-List
Set-Location $DEV
& $DEVPY scripts\check_testnet.py --symbol BTCUSDT --candidates BTCUSDT,ETHUSDT > "$OUT\check_testnet_after_stop.txt"
"exit $LASTEXITCODE"
```

Never executed: the `UtcNow` line (it only records the instant you pressed Ctrl+C: write it in the ledger).
CHECK: the process list shows **no** `-m trading_bot run` for `F:\trading bot\deploy\45547f107715` (the development
tree's own `python.exe` lines may remain); `check_testnet_after_stop.txt` exists and `exit 0`. A position open at the
stop is left to its protective legs and is excluded from both sides (R-AY): note in the ledger whether `check_testnet`
shows one (the unmanaged-holding lines and the order lists are its words). **A Ctrl+C that does not stop the bot
within a minute is not followed by `taskkill` without asking:** an ungraceful end leaves no `engine_stopped` and the
capture is then a power-cut-shaped one (RUN_LEDGER section 55).

## Step 3. The final freeze of the log

**Measured:** `scripts\s4_daily.py`, section 58: it copies every `trading_bot.log*` file (R-BM), hashes each copy, and
writes the capture (the rotated files oldest first, then the active file) with its SHA-256, under
`F:\trading bot\scratch\s4\<UTC date>\`. No run has frozen a *stopped* bot's log, or a rotated one (`M5m-534`).

```powershell
Set-Location $DEV
& $DEVPY scripts\s4_daily.py > "$OUT\s4_daily_final.txt"
"exit $LASTEXITCODE"
Get-Content "$OUT\s4_daily_final.txt" | Select-String -Pattern 'capture|alive|last line'
```

Read the freeze directory and the capture's file name from the report's `directory` and `capture` lines, then set it:

```powershell
$CAPTURE = 'F:\trading bot\scratch\s4\<the UTC date>\<HHMMSS>Z-capture.log'
```

CHECKs, each its own command: `exit 0` from the freeze; the report says `that pid alive as a '-m trading_bot run'
process : no`; `(Get-FileHash $CAPTURE -Algorithm SHA256).Hash` equals the report's `capture sha256` (case aside);

```powershell
Select-String -Path $CAPTURE -Pattern 'event=engine_stopped clean_shutdown=True' | Select-Object -Last 1
```

prints one line, written by the pid the report calls the last. **If there is no such line the stop was not graceful:
record it and go on only with the owner's say-so.** Write the capture path, its digest and the stop instant in
`docs/RUN_LEDGER.md` before anything else is read (the rule T0 was recorded under).

Never executed: the redirect form with `Select-String` over the report (the report's content is the one section 58
printed); the `$CAPTURE` assignment.

## Step 4. The final recorder run

**Measured:** the recorder's run and its `--verify-only`: RUN_LEDGER sections 37 and 40 (exit 0, 0 problems); the owner's
first run in its own clone, section 43; the scheduled runs, section 58 (`LastTaskResult` 0). Its exit codes are in the
script's docstring (0 extended or current, 1 a transient request fault, 2 the venue's history was discarded or rewritten
and NOTHING was written, 3 a bar with no class, 4 the store does not verify, 5 another recorder holds the lock).

Wait until **at least two minutes after `M`** (the bars opening `M` minus 1 minute and `M` minus 5 minutes close at `M`,
and the recorder skips the forming bar). If the scheduled task is running, wait for it: it holds the recorder's lock
(exit 5 otherwise).

```powershell
(Get-ScheduledTask -TaskName tb-recorder).State
Set-Location $RCLONE
& $RPY scripts\record_testnet_klines.py --root data\historical_testnet
"exit $LASTEXITCODE"
& $RPY scripts\record_testnet_klines.py --root data\historical_testnet --verify-only
"exit $LASTEXITCODE"
```

CHECK: the first state line reads `Ready`; both exits are `0`. **An exit 2 is a Testnet reset (R-AZ): stop, the run
ends at the reset, and this runbook does not apply.** Then look at the newest stored bars with the daily tool, which
also re-freezes the (unchanging) log:

```powershell
Set-Location $DEV
& $DEVPY scripts\s4_daily.py > "$OUT\s4_daily_after_recorder.txt"
"exit $LASTEXITCODE"
Get-Content "$OUT\s4_daily_after_recorder.txt" | Select-String -Pattern 'newest bar|capture sha256'
```

CHECK: every `1m` series reads `newest bar opens <M minus 1 day>T23:59:00Z` and every `5m` series
`<M minus 1 day>T23:55:00Z` (for `M` = `2026-11-01`: `2026-10-31T23:59:00Z` and `2026-10-31T23:55:00Z`); the
`capture sha256` is **identical** to step 3's, because the bot is stopped and its log cannot have grown. A different
digest means the log changed after the stop: investigate before going on.

Never executed: the recorder run by hand *after* a stop (the owner's section 43 run was by hand; the scheduled ones are
the same command); the `Select-String` over the report; reading `.State`.

## Step 5. Freeze the store from the recorder clone, by hash

**Measured:** the copy and verification of a store: RUN_LEDGER section 48 (`robocopy /E /COPY:DAT`, then the P113 checker,
run on the source and on the copy; its two inventory digests equal), on the MAINNET store. The checker is now
`scripts\store_check.py`, tracked and tested (R-DE), SHA-256 `fbba98e583362058b732df05e2d77343f29a945f30006b47d0ca920e21a18241`, with the behaviour of the P113 scratch script
(SHA-256 `2a5b5530f525b69485f13141db1d73692760cb418203d1be4c7defa581827592`): RUN_LEDGER section 61 shows the two outputs
and inventory files byte-equal on the mainnet store and on a copy of the recorder's Testnet store, where it exits 0 and
prints `NO MANIFEST` for the `1h`, `4h` and `1d` series it does not hold. Nothing in this step runs from scratch.

```powershell
(Get-FileHash "$DEV\scripts\store_check.py" -Algorithm SHA256).Hash
robocopy $RSTORE $FROZEN /E /COPY:DAT
"exit $LASTEXITCODE"
& $DEVPY "$DEV\scripts\store_check.py" $RSTORE "$OUT\inventory_recorder.jsonl" > "$OUT\store_check_recorder.txt"
"exit $LASTEXITCODE"
& $DEVPY "$DEV\scripts\store_check.py" $FROZEN "$OUT\inventory_frozen.jsonl" > "$OUT\store_check_frozen.txt"
"exit $LASTEXITCODE"
(Get-FileHash "$OUT\inventory_recorder.jsonl" -Algorithm SHA256).Hash -eq (Get-FileHash "$OUT\inventory_frozen.jsonl" -Algorithm SHA256).Hash
Select-String -Path "$OUT\store_check_recorder.txt","$OUT\store_check_frozen.txt" -Pattern 'inventory sha256|verify problems|mismatched|missing / extra|snapshots checked'
```

CHECK: the first line prints `FBBA98E583362058B732DF05E2D77343F29A945F30006B47D0CA920E21A18241` (the digest above, any case);
`robocopy` prints an exit code below 8 (0 or 1 are the clean ones; Microsoft's own table, not measured here); both
`store_check` runs print `exit 0`; the comparison prints `True`; the `Select-String` shows, for the two files, equal
`inventory sha256` lines, `verify problems      : 0`, `mismatched vs manifest: 0`, `missing / extra csv  : 0 / 0`
and `snapshots checked    : 2, mismatched 0`. Then the recorder's own check on the copy:

```powershell
Set-Location $RCLONE
& $RPY scripts\record_testnet_klines.py --root $FROZEN --verify-only
"exit $LASTEXITCODE"
```

CHECK: `exit 0` (the script's docstring: with `--verify-only` it checks the store and makes no network request). Then, optionally and by the owner (R-BQ's ACL for the mainnet store is not part of R-DB and is not
given here), the copy can be made write-protected the way section 48 did for the mainnet store.

Never executed: `robocopy` of the FINAL store (the same switches as section 48 and as P124's copy of the recorder's
store, section 61); the `Select-String` over the two outputs; `--verify-only` with `--root` pointing outside a clone.

## Step 6. The backtest clone, outside `deploy\`, with no `.env`

**Measured:** the build of a backtest clone from GitHub at a pushed commit, its own venv, a non-editable install by
commit with the constraints of an existing venv, and a junction to a frozen store: the S6 sweep clone
`F:\trading bot\backtest\cf474214a539` (`docs/NEXT_MILESTONE.md`, the P117 C8 block, O1, executed by the owner;
RUN_LEDGER sections 52 to 54 read its records), the earlier deployment builds of sections 21 and 26 (the same
`pip install -c` form, `M5l-172`), and the junction through `cmd /c mklink /J`, section 48. **That was at other SHAs. At
`45547f1` this build has never been executed.** The clone is at the S4 commit because R-AO runs the backtest from the
same commit as the live run: the code of `45547f1` has no research-protocol guard and a different run-record schema
from `HEAD`, and `scripts\s4_compare.py` and `scripts\trade_census.py` are byte-identical at both.

**Step 6a can be done now, before the stop** (about 10 to 20 minutes; the network is needed for `pip` only):

```powershell
$PYTHON = "$env:LOCALAPPDATA\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe"
$SWEEPPY = 'F:\trading bot\backtest\cf474214a539\.venv\Scripts\python.exe'
Test-Path $BT
git clone https://github.com/atul-biswash/trading-bot.git $BT
git -C $BT checkout --detach $SHA
& $PYTHON -m venv "$BT\.venv"
& $SWEEPPY -B -m pip freeze | Where-Object { $_ -notmatch '^binance-trading-bot' } | Set-Content "$env:TEMP\s4_constraints.txt" -Encoding ascii
& $PY -m pip install -c "$env:TEMP\s4_constraints.txt" "binance-trading-bot @ git+file:///F:/trading%20bot/backtest/$S@$SHA"
```

The `Test-Path` line must print `False` before the clone (a directory that exists is not overwritten). The
`pip freeze` line is piped into a file, not into a verdict: it is the constraints and nothing reads its exit status.
CHECKs, each its own command: `git -C $BT rev-parse HEAD` prints `$SHA`; `git -C $BT status --porcelain` prints
nothing; `& $PY --version` prints `Python 3.12.10`; `Test-Path "$BT\.env"` prints `False` (no key, no secret: the
backtest needs none); `(Get-FileHash "$BT\config.s4.yaml" -Algorithm SHA256).Hash` is `0F170BAEFB7B41C87D9F3BC5220A484CE9FA20B0A62758E15CB485E9B0712594`
(the digest in the pre-registration, section 6, any case); and

```powershell
& $PY -m trading_bot strategies 2>&1 | Select-String boot_provenance
```

shows one line with `verdict=accepted`, `install_kind=vcs`, `code_intact=true`, `code_commit=<$SHA>`,
`checkout_dirty=false`, `commits_agree=true` and `config_tracked=true`.

**Step 6b, after step 5** (the junction's target must exist and be the frozen copy):

```powershell
cmd /c mklink /J "$BT\data\historical_testnet" $FROZEN
(Get-Item "$BT\data\historical_testnet").LinkType
Test-Path "$BT\data\historical_testnet\BTCUSDT\1m"
git -C $BT status --porcelain
```

CHECK: `Junction`; `True`; and the last prints nothing (`data/` is ignored by git, so the junction leaves the checkout
clean, which the run record's eligibility requires). Do not copy anything else into the clone.

Never executed: every command of 6a at `45547f1` (executed at other SHAs); `& $SWEEPPY -B -m pip freeze` against the sweep
clone's venv as the constraints source for this build (O1 used the S5 clone's, `67b7563de683`); the `LinkType` read
(section 48 checked the junction with Python's `is_junction`); `git -C <clone> status --porcelain` is the P118 rehearsal's
form.

## Step 7. The backtest of `[W, M)` through `config.s4.yaml`

**Measured:** a backtest of `config.s4.yaml` over one day (`2026-10-08`) from the DEVELOPMENT tree, RUN_LEDGER section 40:
19 trades, 1,440 BTCUSDT 1m bars and 288 ETHUSDT 5m bars served, `exchange_info` environment `testnet`, no problem,
and `evidence_eligible` **false** (an editable install). Eligible backtests from a clone were measured for the
mainnet store and `config.yaml`: sections 50 to 54 (a vcs install, `evidence_eligible: true`). **An eligible backtest of
`config.s4.yaml` over the recorded Testnet store has never been executed.** The speed, DERIVED from P116's 2.5 ms a bar
for `sma_crossover`: about 30,000 1m bars and 6,000 5m bars for 21 days, so about 90 seconds plus the boot.

```powershell
Set-Location $BT
& $PY -m trading_bot --config config.s4.yaml backtest --start $W --end $M
"exit $LASTEXITCODE"
```

`--end` is the day the replay stops BEFORE, so `[W, M)` is exactly the window of pre-registration section 4.

```powershell
$RUN = (Get-ChildItem "$BT\data\backtests" | Sort-Object Name | Select-Object -Last 1).FullName
$RUN
Get-ChildItem $RUN
Select-String -Path "$RUN\run.json" -Pattern '"evidence_eligible": true'
git -C $BT status --porcelain
```

CHECK: `exit 0`; the directory holds `backtest.log`, `run.json` and `trades.csv`; the `Select-String` prints one line
(the compare REFUSES a record whose `evidence_eligible` is not exactly `true`: do not edit one); `git status` prints
nothing. If `evidence_eligible` is `false`, read `provenance` in `run.json` for the reason; the usual ones are a dirty
checkout, a commit that does not agree with the install, or a config outside the checkout. **Exactly one run directory
may exist in `data\backtests` at the time**: a second backtest (an exploratory arm, a retry) is a second directory, and
the `-Last 1` above then picks the wrong one; check `(Get-ChildItem "$BT\data\backtests").Count` prints `1`.

Never executed: the whole step, in this form (the closest are section 40's smoke run and the S5/S6 runs of sections 50 to
54, which differ in the config, the store and the clone). `--config` before the subcommand is the pre-registration's
form (section 6) and `tests/unit/test_config_s4.py` pins the config, not the invocation. `$RUN` and the listing.

## Step 8. The frozen comparison

**Measured:** `scripts\trade_census.py` over a frozen capture: section 58 (84 bookings) and section 27; the frozen
`down_intervals` over a log copy: sections 43, 46, 49, 55. **`scripts\s4_compare.py` has never been run end to end on
real inputs**: its 75 tests (section 39) and the mutation survey are its only runs, and no eligible backtest of the
Testnet store existed to give it.

```powershell
Set-Location $BT
& $PY scripts\trade_census.py $CAPTURE > "$OUT\trade_census.txt"
"exit $LASTEXITCODE"
& $PY scripts\s4_compare.py --run $RUN --capture $CAPTURE --window-start "${W}T00:00:00Z" --window-end "${M}T00:00:00Z" --store $FROZEN > "$OUT\s4_compare.txt"
"exit $LASTEXITCODE"
```

CHECK: the census exits `0` (`1` means an anomaly line it could not read; read them); `s4_compare` exits `0` (`2` is a
refusal, a path under `logs\`, an ineligible record or a capture with no `boot_provenance` line; `3` is an input error).
`s4_compare.txt` carries the capture's digest (`capture sha256`), `run.json sha256`, `trades.csv sha256` and
`recorded series`, which must name `$FROZEN`: compare the first with step 3's. It prints **figures and no verdict**.

The acceptance tests are the pre-registration's section 7 (A gross mean, B count, C reproduction) and are applied by the
owner to those figures; this runbook does not apply them. **Do not edit `scripts\s4_compare.py` or the pre-registration**
(R-BN): any other reading of the downtime is exploratory under the ratified CHOSEN line 5, and step 9 is where it lives.

## Step 9. Record, and the exploratory downtime analysis

**Record in `docs/RUN_LEDGER.md`** (a new section, nothing above it edited): the stop instant, the capture and its
digest, the recorder's final bars, the frozen store's inventory digest, the backtest clone's boot line, the run
directory, `run.json`'s and `trades.csv`'s digests, the two output files' digests, and the arithmetic below.

**The comparable-count arithmetic (R-AZ's 100).** From `s4_compare.txt`: `N_live` is the live bookings with an entry in
`[W, M)` after the downtime exclusions, listed apart in its diagnosis. Compute: *the census's bookings with an entry in
`[W, M)`, minus the entries the frozen rule excludes, against 100.* Pre-registration section 7 holds the thresholds; R-AZ's
100 is the floor under which S4 is NOT MEASURED when a reset ended the run, and the same floor is the cap's. The runbook
reports the arithmetic and the owner reads it against the section.

**The exploratory downtime analysis (R-DC).** `scripts\s4_explore.py` (built in the same P123; first run in RUN_LEDGER
section 60) reports, for the frozen capture, the excluded intervals under the frozen `down_intervals` and under a
corrected rule (from each process's last record to the next process's first closed candle) and the entries each would
exclude. It reads the capture and writes nothing but its output. It is exploratory and never replaces step 8's result.

```powershell
Set-Location $DEV
& $DEVPY scripts\s4_explore.py $CAPTURE --window-start "${W}T00:00:00Z" --window-end "${M}T00:00:00Z" > "$OUT\s4_explore.txt"
"exit $LASTEXITCODE"
```

CHECK: `exit 0`; the header's `capture sha256` equals step 3's. Never executed on the final capture; its one run is the
P123 C3 copy.

## Appendix A. A rehearsal, before the stop (the owner's choice)

Steps 3 to 8 can be rehearsed now over a past window, to find a broken command while there is time. Set
`$M = '2026-10-12'` (the window `[2026-10-11, 2026-10-12)`), skip steps 1 and 2, take step 3's freeze of the LIVE
log, step 4's recorder run (the real clone's store is only appended to), and then steps 5 to 8 with `$OUT` and `$FROZEN`
carrying that date. **It prints the S4 comparison's figures for one day of the live run.** The pre-registration's tests and
the stop rule are fixed in advance, so seeing them changes neither; whether to look is the owner's. Its outputs are not S4's
result and are never written into the ledger as such. The rehearsal executes every step marked N in the table below except
the stop itself, and is the only way to execute step 7 and step 8 before the evidence exists.

## Which commands have never been executed

E = executed on this machine in this form; R = executed in a related form (another SHA, store, config or tool); N = never.

| Step | Commands | Status | Evidence or what is missing |
|---|---|---|---|
| 0 | the assignments, `New-Item` | N (trivial) | |
| 1 | `s4_daily.py` | E | section 58 |
| 2 | Ctrl+C; the process list; `check_testnet.py` | E / E / E | sections 46, 25 to 26; `CLAUDE.md` C38; sections 40, 46 |
| 2 | `[DateTime]::UtcNow` | N | |
| 3 | `s4_daily.py` with a redirect | E | section 58 |
| 3 | freezing a stopped bot's log, or a rotated one | N | `M5m-534` |
| 3 | `Select-String -Pattern 'event=engine_stopped ...'` over a capture | R | section 21 (`Select-String` for the same line) |
| 4 | the recorder run by hand, `--verify-only` | E | sections 37, 40, 43 |
| 4 | the recorder run *after* a stop, `(Get-ScheduledTask).State` | N | |
| 5 | `robocopy /E /COPY:DAT` | R | section 48 (mainnet store) |
| 5 | `scripts\store_check.py` on a Testnet store | E | section 61 (a copy of the recorder's store: exit 0, equal to the P113 script's output) |
| 5 | `--verify-only --root <frozen copy>` | R | section 40 (the recorder's own root) |
| 5 | the digest comparison and the `Select-String` over the two outputs | N | |
| 6a | `git clone`, `checkout --detach`, `venv`, `pip install -c`, the boot check, at `45547f1` | R | the sweep clone's build (other SHA); sections 21, 26, 52 |
| 6a | `pip freeze` from the sweep clone as constraints | R | O1 used the S5 clone's |
| 6b | `mklink /J` to the frozen Testnet store; `LinkType` | R | section 48 |
| 7 | `trading_bot --config config.s4.yaml backtest --start --end` from a clone with a vcs install | N | section 40 (dev tree, ineligible); sections 50 to 54 (other config and store) |
| 8 | `trade_census.py` over a capture | E | section 58 |
| 8 | `s4_compare.py` on real inputs | N | tests only (section 39) |
| 9 | `s4_explore.py` on the final capture | N | one run on a copy, section 60 |

**Not executed anywhere: step 7's eligible backtest of the Testnet store and step 8's `s4_compare.py` on real inputs.**
They are the two places the stop can first fail. Appendix A exists to run them while there is still time to correct
a command, not a result.
