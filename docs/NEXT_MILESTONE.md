# Next milestone — M5l

## M5l's SCOPE — ruled by the project owner

The ruling, verbatim:

> "Verdict: Approved. Directives: The architectural live-trading block remains
> strictly active. No live execution will be scheduled until a non-zero fee
> capture is empirically established on a live-quoted venue and base-asset
> quantity netting is fully implemented in the entry sizing pipeline. M5l
> priorities: Startup VCS commit/dirty-state enforcement, configuration
> validation alignment (`max_position_staleness_s` vs. timeframe dedup
> intervals), and eliminating the unhedged/silent failure modes cataloged
> across M5k."

Where the bot may be run from is already ruled, by `CLAUDE.md`'s locked
bullet *"THE BOT IS NEVER LAUNCHED FROM A DEVELOPMENT WORKING TREE"*, landed at
`ae8c914`. It is pointed to here, not restated.

**The milestone's shape is EVIDENCE-FIRST.** M5k's code is not shown to have
run as committed -- see THE CENTRAL FACT below. So M5l's first run on known
code executes from a deployment checkout of a pushed commit, per that
doctrine. `docs/RUN_LEDGER.md` records its start -- the commit, the config's
digest and the UTC instant -- before its evidence is read. Its census then
answers, against the unobserved-surface table below, which of the 22 log
events and the 8 `RefusalStage` members never observed at M5k's close it
exercises. No such run has started as this is written.

> **ANNOTATED AT M5l (P63): *"No such run has started as this is written"* IS
> NO LONGER TRUE.** It was true when `583e480` wrote it. The run started at
> `2026-09-27T13:30:56Z`: pid 21520, from `F:\trading bot\deploy\06089d5e01cb`
> at `06089d5`, and `docs/RUN_LEDGER.md` section 21 records its start. Two
> earlier runs, pids 20112 and 12808, came from a deployment clone at
> `9f364dd`, before C4, with no start record (`M5l-050`); section 22 records
> them. **What survives:** the rest of this paragraph. The census against the
> table below has not been taken.

> **ANNOTATED AT M5l (P64): TWO MORE STATEMENTS HERE ARE NO LONGER TRUE.**
> *"M5k's code is not shown to have run as committed"*: pid 21520, at
> `06089d5`, wrote three `close_booked` lines carrying
> `quote_total_source=venue` (`M5l-053`). The block above's *"The census …
> has not been taken"*: it was taken after the run stopped at `16:53:22Z`, and
> `docs/RUN_LEDGER.md` §23 holds it.
>
> Its answer, against the capture whose SHA-256 is
> `c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f`: of the
> 22 log events never observed at M5k's close, **none**. Of `boot_provenance`,
> added after that close, **yes**. Of the 8 `RefusalStage` members, **none**:
> the run refused nothing.
>
> **What survives:** that this run started from a deployment checkout of a
> pushed commit, and that its start is recorded. That record was committed
> after the log was first read (`M5l-051`).

---

Struck and repaired at M5k's rotation, in its first part. Every item below was
re-verified by content against `ae8c914`; anything M5k closed is reduced to one
index line naming the resolving commit and its findings, and its full text
lives in git history and in `docs/PHASE_HISTORY.md`'s M5k entry. M5l's scope,
priorities and new carried items are the rotation's second part. **This is the
single home for live open items.**

---

## Before M5l starts — the namespace

**IDs are `M5l-NNN`: three digits, zero-padded, starting at `M5l-001`.** Not
letters. `CLAUDE.md` prescribes the digit form in its rescued rule 2; this
paragraph is carried forward so that a reader of this file meets it first.
**A rotation that rewrites this file must carry this paragraph forward.**

**M5k's range is closed by the tag `milestone/M5k`**, applied to the closing
commit of M5k's rotation, and its count is read with one command rather than
written here, once that tag exists:

```
.venv\Scripts\python.exe scripts/check_findings.py milestone/M5j..milestone/M5k M5k
```

It prints the declared, distinct and maximum ids, and every duplicate, gap,
id cited but never declared, and commit with no block. The M5l namespace is to
be confirmed empty by the same tool, over `milestone/M5k..HEAD`, before
`M5l-001` is written.

> **THE M5i RESERVED BLOCK IS STILL RESERVED.** `M5i-068`, `M5i-071` and
> `M5i-073` are cited in the tree and declared nowhere. That is deliberate and
> the extractors report it every time as `cited-not-declared`; it is not a
> defect to be closed by inventing declarations for them.

> **AND THREE MORE M5i IDS ARE UNRECORDED ANYWHERE (`M5k-018`).**
> `scripts/check_findings.py` reports the M5i range's gaps as 68 through 73.
> The reserved block accounts for three of them; `M5i-069`, `M5i-070` and
> `M5i-072` appear in no commit message and no tracked file, and no document
> mentions them. They are not to be invented either.

> **`9f364dd` IS BLOCKLESS, KNOWN AND DECLARED (`M5l-031`).**
> `scripts/check_findings.py` reports `blockless commits : [9f364dd]` on every
> run over a range that contains it, and exits non-zero for it. It is the
> owner's commit *"config: operator settings for testnet runs"*, pushed during
> P58 with no `Findings:` block; pushed, so it cannot be amended. That is
> deliberate to leave standing and the extractors will report it every time;
> it is not a defect to be closed by rewriting history or by inventing a block.

---

## THE CENTRAL FACT — read this before anything else

**Nothing M5k added is shown to have run as committed, and the bot records
nothing that could show it.** Measured against the capture
`trading_bot.m5k-close-20260925T182818Z.log`, SHA-256
`3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`, taken at
M5k's close; `docs/RUN_LEDGER.md` §19 holds its census:

- **No line logged by code as committed at or after `651d334` is shown to
  exist.** Eight booking lines carry `fee=0E-8 fee_asset=USDT`, a key no commit
  before `651d334` writes. The first is at `2026-09-24T10:38:02Z`, seven hours
  before that commit existed, while the reflog held HEAD at `e511e6d`: the fee
  settlement ran from uncommitted code (`M5k-123`). No line carries
  `quote_total_source`, which every booking line writes from `c5dd7d5`, and
  none of the six events M5k added appears.
- **The bot records no commit** (`M5k-132`). Its startup banner is ASCII art
  and a mode line, and no line in any capture names a commit, a version or a
  dirty tree. `CLAUDE.md`'s deployment doctrine rules that this change, and
  marks the banner NOT YET IMPLEMENTED.
- **`RefusalStage.POSITION_STALE` fired once**, at `2026-09-24T19:25:00Z`
  (`M5k-124`) — the first time in any capture.
- **No run was writing when the capture was taken.** The bytes it adds to the
  previous capture hold six runs, every one ending in `engine_stopped` after a
  `SIGINT`; its last line is `pid=23236`'s, at `2026-09-25T16:16:10Z`.
  `pid=24772`, still appending when M5j's rotation wrote this section, last
  logged at `2026-09-19T09:42:02Z` and records no `engine_stopped`.

> **ANNOTATED AT M5l (P64): THE HEADLINE AND THE FIRST TWO BULLETS ARE NO
> LONGER TRUE.** Each was true of the capture named above, and each bullet's
> claims about that capture still are.
>
> - **"Nothing M5k added is shown to have run as committed"**, and the first
>   bullet's *"No line carries `quote_total_source`"*: pid 21520 ran from a
>   deployment clone at `06089d5`, verified by its `boot_provenance` line. It
>   wrote three `close_booked` lines carrying `quote_total_source=venue` and
>   `fee=0E-8 fee_asset=USDT`, in the capture whose SHA-256 is
>   `c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f`
>   (`M5l-053`, `docs/RUN_LEDGER.md` §23). Each one reconciles exactly against
>   the venue's fills (`M5l-054`). None of the six events M5k added appears
>   there either.
> - **"The bot records no commit"** and *"marks the banner NOT YET
>   IMPLEMENTED"*: false since `f8898de`, which added `boot_provenance` after
>   the banner on every boot. It was false when M5l's P-1 landed, not because
>   of any run. `CLAUDE.md`'s doctrine carries the P-1 annotation.
>
> **What survives:** the `POSITION_STALE` bullet and the no-writer bullet, both
> scoped to that capture, and the standard of evidence below.

**The standard of evidence M5j set still holds.** A claim derived from a
capture names its digest in the sentence that makes it, or it cannot age
visibly.

---

## M5l's PRIORITIES — the owner's three, in the architect's order

The owner ruled the three; their order is the architect's. Provenance comes
first because without it no later run can say which code produced its
evidence, and the other two are judged by that evidence.

### P-1. Startup provenance -- RESOLVED in code; no run has exercised it

**Resolved by five commits:** `fdf8d7b` (the config's resolved path and the
digest of the bytes parsed), `ac1162d` (the bounded git runner and the
launch checkout), `d74f78b` (the install, RECORD and the verdict), `f8898de`
(the boot line and the refusal in `main`) and `63d4615` (an unrecorded
module refuses); findings `M5l-001`--`M5l-028`. `main` logs one
`event=boot_provenance` line after the banner on every boot and refuses `run`
unless the install is a VCS install whose RECORD verifies, the launch
checkout is clean at the installed commit, and the config is tracked there.
The bot got its own module, `utils/provenance.py`; `describe_vcs_state` was
not moved and U8 did not fire. `trading_bot.__file__` is logged, as
`module_file`. `CLAUDE.md`'s deployment doctrine carries the install
procedure the refusal accepts.

**What stays open is evidence, as for every M5l item:** no run has booted
through it yet, so `boot_provenance` is absent from every capture. The
condition that read *"whoever next edits `_BANNER` or the startup block of
`main` in `src/trading_bot/main.py`"* fired at `f8898de`, was satisfied
there, and is struck.

> **ANNOTATED AT M5l (P63): THE HEADING'S *"no run has exercised it"* AND
> *"no run has booted through it yet"* ARE NO LONGER TRUE.** Both were true
> when `5cac7ae` wrote them. The provenance check has now accepted six boots
> from deployment clones:
> - at `9f364dd`, before C4: pids 22740, 20112 and 12808 (`M5l-050`,
>   `docs/RUN_LEDGER.md` section 22);
> - at `06089d5`: the dry boot pid 22088 and the evidence run pid 21520
>   (section 21);
> - plus P59's scratch-clone boot at `1f4a718` (`M5l-041`).
>
> **What survives:** *"`boot_provenance` is absent from every capture"*. No
> capture has been taken since those boots, and the lines are in the clones'
> own logs, not in any capture.

> **ANNOTATED AT M5l (P64): THAT SURVIVING CLAUSE IS NO LONGER TRUE.** The
> capture of pid 21520's log, SHA-256
> `c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f`, holds
> two `boot_provenance` lines: pid 22088's dry boot and pid 21520's run
> (`docs/RUN_LEDGER.md` §23). **What survives:** P-1's code, and that every
> boot it has seen from a deployment clone was accepted.

### P-2. Staleness against the reconciliation dedup interval

`risk.max_position_staleness_s` and the dedup interval are coupled by meaning
and not by code, and `docs/M5_NUMBERS.md` §4 already says *"nothing checks
it"*. The dedup interval is the shortest enabled timeframe:
`ReconciliationBudget.from_config` builds `dedup_interval` from
`shortest_ms`. A position is not re-read until its stamp is that old, so a
staleness threshold at or below it refuses entries on a healthy system for
part of every interval (`M5k-075`, REASONED). The guard has now fired once in
production (`M5k-124`). P-2 is a config validation that refuses a
`max_position_staleness_s` at or below the shortest enabled timeframe's dedup
interval.

> **ANNOTATED AT M5l (P70, C20): THE VALIDATION BUILT IS NOT THE ONE PLANNED
> HERE.** The rule planned above, refusing a value *"at or below the shortest
> enabled timeframe's dedup interval"*, is too low: the guard reads a stamp
> up to one bar old plus that candle's handling, plus a bar per call-cap
> deferral (`M5l-066`, `M5l-084`). C20 refuses a value below
> `(1.5 + n - 1) x T + 1.0 s + 5 s`, with `n = min(max_open_positions, enabled
> pairs)` -- 156 s on the committed config. It is exact, through C15's
> helper. So the next paragraph's *"passes only on 1m"* narrows: the 180 s
> default passes at a 1m shortest bar only while `n <= 2` (216 s at
> `n = 3`), and at 2m the floor is already 186 s. **What survives:** that it
> is a config-load validation beside the coherence check, and that the
> default's fate is P-2's design question.

**The model default would fail it.** MEASURED from the code:
`config/models.py` declares `max_position_staleness_s: float = Field(180.0,
gt=0)`. A 3m timeframe is 180 s, so under an at-or-below rule the default is
refused by any configuration whose shortest enabled timeframe is 3m or
longer, and passes only on 1m. The committed `config.yaml` enables BTCUSDT on
1m alone, so it passes. `M5k-075` records a shortest timeframe of 5m in the
owner's working copy, which would not. **Fixing the default -- a fixed figure,
or one derived from the timeframe -- is P-2's design question.**

*Arming condition:* **whoever next edits `config/models.py`'s coherence block.**

This is U7's site, deliberately: the check belongs beside the coherence
validator, and an edit there arms both items.

> **ADDED AT M5l (P65): FOUR FACTS FOR P-2's DESIGN, THE SECOND OF THEM FOR
> THE OWNER'S RULING.**
>
> 1. **`M5l-056`: the strict `>` in `_is_due`.** In
>    `execution/reconciliation.py`: `return now - position.last_reconciled_at >
>    dedup_interval`. MEASURED at M5l's evidence run, with a position open and
>    a 1m shortest timeframe: inter-pass gaps were about 60 s 21 times and
>    about 120 s 33 times. So in practice a position is re-read up to two
>    dedup intervals apart. A staleness bound between one and two intervals
>    refuses entries on a healthy system too, so *"at or below the dedup
>    interval"* is not the whole unsafe range. The same run's outage added one
>    gap of 300 s (`M5l-055`, P-3l).
>
>    > **ANNOTATED AT M5l (P68, C19): THE LAST TWO SENTENCES ARE WRONG
>    > (`M5l-067`).** The C17 test now pins the strict `>`, and the measured
>    > gaps stand. But *"A staleness bound between one and two intervals
>    > refuses entries on a healthy system too"* confuses the gap between
>    > passes with the age the guard reads. The guard reads the stamp only in
>    > `evaluate`, after the reconciler on the same candle. So on a healthy
>    > feed it sees at most one bar plus the time from that candle's close to
>    > its read, plus one bar for each bar the position was due and not
>    > refreshed (`M5l-066`). The 300 s outage gap is sampled by no read,
>    > because no candle arrived (`M5l-068`). **What survives:** the
>    > measurement, and that the at-or-below rule is not by itself the floor.
> 2. **The locked decision, contradicted by measurement since M5g, is for the
>    owner's ruling.** `CLAUDE.md`, *Fills are observed by polling*:
>    *"Reconciliation runs over **every** open position on **any** pair's
>    candle, so staleness is bounded by the *shortest* configured timeframe
>    rather than the slowest position's."* Two measurements contradict it: run
>    2's gaps of 119 to 121 s (`docs/M5_NUMBERS.md` §4) and `M5l-056`'s. The
>    locked bullet after it already says *"The shortest timeframe is a floor,
>    not a bound"*, but it names latency, skipped budget and dropped bars as
>    the causes, not the dedup comparison. Whether to annotate the locked
>    text, change `>` to `>=`, or dedup against a shorter interval is the
>    owner's call.
>
>    > **ANNOTATED AT M5l (P68, C19): STILL OPEN, AND THE CORRECTED TEXT
>    > OFFERED AT P68 DOES NOT FIT THE CODE (`M5l-081`).** P68 offered a
>    > re-ruled text whose deferral clauses say *"about 3·T when the per-pass
>    > call cap defers it"* and *"plus one T for a call-cap deferral"*.
>    >
>    > MEASURED by driving the real pass and resolver:
>    > - With three open positions -- an oldest healthy one, one whose
>    >   protective legs are absent, and a newest due one -- the newest was
>    >   deferred on two consecutive bars.
>    > - Its stamp reached 181 s at `T` = 60 s before it was read.
>    >
>    > So on a healthy feed `k` reaches 2, where the text allows 1. A position's
>    > own partial reconciliation followed by a neighbour's deferral reaches it
>    > the same way (REASONED). With at most two positions -- the committed
>    > config's two enabled pairs -- `k` is at most 1.
>    >
>    > So nothing was added to `CLAUDE.md`'s locked text, and the floor P68
>    > specified (`2.5·T + 1.0 s + 5 s`, which assumes `k <= 1`) was not built.
>    > Still open, for the owner: the locked text, the floor (derived at P67
>    > STEP 0 as `T + H + k·T`, with `k` now shown to reach 2 at three
>    > positions), the default, and the 180 s rationale (`M5l-072`).
>    >
>    > > **ANNOTATED AT M5l (P70, C20): *"the floor"* AND *"the 180 s
>    > > rationale"* ARE NO LONGER OPEN.** The floor is built, with
>    > > `k_max = n - 1` per the owner's P69 ruling, and it is 156 s on the
>    > > committed config. The 180 s docstring now states that derivation.
>    > > **What stays open:** the locked text, and whether the floor should
>    > > widen for position churn, which adds one deferral beyond `n - 1`
>    > > (`M5l-088`). The default stays at 180 s, PLACEHOLDER.
> 3. **The coherence validator compares floats and prints one decimal.** In
>    `config/models.py` it tests `if dispatch + reconcile + settlement <=
>    budget:` with every term a `float` product, and the refusal prints `{dispatch
>    + reconcile + settlement:.1f}s` against `budget {budget:.1f}s`.
>    MEASURED through `AppConfig` on the committed config (`M5l-065`): of 120
>    configurations whose total is exactly 30.0 s in decimal, 9 are refused,
>    each with a message reading *"is 30.0s. That exceeds 50% … budget
>    30.0s"*. D = 9.4 with T_recon = 2.24 is one. The committed config, at
>    29.5 s, is unaffected. The coherence block is this item's arming site.
>
>    > **ANNOTATED AT M5l (P68, C15): THE ARITHMETIC HALF IS RESOLVED.**
>    > *"compares floats"* and *"with every term a `float` product"* are no
>    > longer true. Every term is now a `Decimal`: each duration goes through
>    > `_exact_seconds`, which is pydantic's own conversion, and `T_min` comes
>    > from integer milliseconds. *"of 120 … 9 are refused"* was true at
>    > `f2182a6`; now 0 are. `test_every_exact_boundary_configuration_is_accepted`
>    > pins it. **What survives:** *"prints one decimal"*, since the message
>    > still renders `:.1f` until C16.
>
>    > **ANNOTATED AT M5l (P68, C16): ITEM 3 IS RESOLVED.** *"prints one
>    > decimal"* is no longer true, and neither is the note above that it
>    > survives. The refusal now prints each duration, each product, the
>    > total and the budget exactly, for example *"is 30.02s"*.
>    > `test_the_refusal_prints_the_exact_sum_and_its_terms` pins it.
> 4. **`M5l-049`'s stale docstring still stands.** `ReconciliationBudget.from_config`
>    in `execution/reconciliation_driver.py` says *"splitting ``T_recon`` into a
>    per-attempt share would be a tail claim that the only samples in existence
>    -- six, bimodal, from one host -- cannot support."* It has been false since
>    P59's 300 samples (`M5l-039`). It is in `src/`, which no M5l documents
>    commit may edit.
>
>    > **ANNOTATED AT M5l (P68, C18): ITEM 4 IS RESOLVED.** *"still stands"*
>    > is no longer true. The docstring now reads *"a tail claim the samples
>    > cannot support: P59's 300 readings came from one session on one host
>    > (``M5l-039``, maximum 0.467 s)"*. C18 also fixed the same claim in
>    > `RiskManager._stale_positions` (`M5l-070`), the status of
>    > `reconcile_deadline_s` (`M5l-071`), and `record_partial_reconciliation`'s
>    > account of an old stamp (`M5l-076`).
>
> **One sentence above went stale at `9f364dd`, and is annotated here:**
> *"The committed `config.yaml` enables BTCUSDT on 1m alone"*. The committed
> config also enables ETHUSDT on 5m. Its conclusion survives: the shortest
> enabled timeframe is still 1m, so the default passes.

> **ANNOTATED AT M5l (P71, C22): P-2 IS RESOLVED EXCEPT FOR ITS LOCKED TEXT
> AND ITS DEFAULT.** Item by item, with the commit that resolved each:
>
> - **The validation this item plans:** built at `f20e839` (C20). Config
>   load refuses a `max_position_staleness_s` below the healthy-feed floor,
>   `(1.5 + n - 1) x T + 1.0 s + 5 s`, which is 156 s on the committed
>   config. `90355df` (C20b) adds the precondition that floor rests on:
>   `max_open_positions >= L + 1`, where `L` is the number of enabled
>   protective legs (`M5l-087`, P-3o).
> - **Item 1, the strict `>`:** pinned at `517348f` (C17). What the
>   measured gaps mean was corrected by C19's annotation above
>   (`M5l-067`). Whether to change it to `>=` goes with item 2.
> - **Item 2, the locked decision: STILL OPEN.** The owner's re-ruled text
>   was offered at P71 as C21 and was not added. It says that once a stamp
>   passes the floor, the guard refuses every entry. That is not what the
>   code does. The guard compares against the CONFIGURED bound
>   (`risk.max_position_staleness_s`, 180 s committed), not against the
>   floor (156 s). A stamp between the two is refused by nothing. The floor
>   and the 180 s rationale were resolved at `f20e839`, as noted under
>   item 2.
> - **Item 3, float arithmetic and one-decimal output:** resolved at
>   `25dbc61` (C15) and `5d6f115` (C16).
> - **Item 4, `M5l-049`'s docstring:** resolved at `6e7c9f2` (C18).
> - **Churn (`M5l-088`), measured against the guard (`M5l-089`).** The
>   real pass, resolver and `RiskManager.evaluate` were driven over 8
>   bars, at `n = 2` and `n = 3` with the call cap `M = 3`. A position
>   opened on every freed slot. Churn pushed a healthy stamp past the floor
>   in every run: 182 s at `n = 2`, and 242 s at `n = 3`, where it was
>   deferred on three consecutive bars, so `k` reached `n`. **No entry was
>   admitted after any stamp passed the bound**: `evaluate` refused as
>   `position_stale`, or earlier as `committed_risk_unknown`. The probe
>   models the reopened position with an expired FOK entry, so it never
>   resolves, and `committed_risk_unknown` then refuses every later bar. So
>   churn costs refusals, not admissions. Whether the floor should widen for
>   churn stays a question about false refusals, not about safety.
> - **The default: STILL OPEN.** It stays at 180 s, PLACEHOLDER. It passes
>   the floor on the committed config.
>
> **What survives:** the locked-decision question, and the default's value.

> **ANNOTATED AT M5l (P72, C23): THE DEFAULT IS RULED; P-2 STAYS OPEN ON ONE
> CLAUSE OF ITS LOCKED TEXT.**
>
> - **The default: RULED, kept at 180 s.** The owner rules it kept because it
>   passes the derived floor on the committed config (180 s against 156 s).
>   A configuration it does not fit is refused at load, and the refusal
>   names a value to set: *"Set risk.max_position_staleness_s to at least"*
>   the floor, in `_check_staleness_bound_covers_a_healthy_feed`. Its status
>   stays PLACEHOLDER, since keeping a value does not measure it. This makes
>   three sentences above no longer true: *"The default: STILL OPEN"*, *"the
>   default's value"* in the survival line above, and the P-2 body's
>   *"Fixing the default -- a fixed figure, or one derived from the
>   timeframe -- is P-2's design question"*, with the C20 annotation's
>   *"the default's fate is P-2's design question"*.
> - **Item 2, the locked decision: STILL OPEN, on one clause.** The owner's
>   re-ruled text, offered at P72 as C23, was not added to `CLAUDE.md`. One
>   clause disagrees with P72's STEP 0 (`M5l-092`): *"Churn ... can add
>   deferrals, up to n in a row as measured at M5l"*. In the stress arm, a
>   newcomer's take-profit filled before its first read. At `n = 3`, under
>   the 216 s bound that is `n = 3`'s floor, the healthy position was then
>   deferred on four consecutive bars, which is `n + 1`. Its stamp reached
>   242 s and then 302 s, and it was read on the fifth bar. Every other
>   clause agrees with STEP 0 and with the code. That includes *"the guard
>   refuses every entry once any stamp exceeds the configured bound"*:
>   `_stale_positions` appends any position whose stamp is `None` or older
>   than the bound, and `evaluate` refuses if the list is non-empty. No entry
>   was admitted while any stamp exceeded the bound, in any of the six
>   measured runs.
> - **The C20 annotation's *"position churn, which adds one deferral beyond
>   `n - 1`"* understates.** The same stress arm
>   added two deferrals beyond `n - 1`. Recorded here, not corrected.
>
> **What survives:** the locked-decision question, now narrowed to how many
> deferrals churn can add in a row. P-2 is not closed.

> **ANNOTATED AT M5l (P73, C24): THE CHURN CLAUSE IS RESOLVED; P-2 STAYS OPEN
> ON A MISSING PRECONDITION.**
>
> - **The owner's rule for locked text:** locked text states enforced
>   guarantees and derived bounds with their preconditions, never counts
>   measured in adversarial arms as limits.
> - **The churn clause is resolved.** The owner's P73 text says churn *"can
>   add deferrals beyond n - 1 (measured up to n + 1, M5l-092); no bound is
>   claimed for it"*. That agrees with `M5l-092`.
> - **Item 2, the locked decision: STILL OPEN, on one clause.** P73's text,
>   offered as C24, was not added to `CLAUDE.md`. Its sentence *"so the age it
>   observes is at most T plus the time from the candle's close to that read,
>   plus one T for each consecutive call-cap deferral of that position"*
>   states a derived bound without its precondition, a healthy feed. The
>   finding it rests on carries that precondition: `M5l-066` reads *"so on a
>   healthy feed the age it observes is at most one bar plus the handling
>   time"*. MEASURED at P73 (`M5l-095`), with the real pass, resolver and
>   `evaluate`: after a 360 s gap with no candle, a neighbour whose
>   take-profit filled during the gap was visited first. On the first candle
>   after the gap, the healthy position was deferred once, and `evaluate`
>   read its stamp at 361 s, where the clause allows 121 s. The guarantee
>   held: `evaluate` refused as `position_stale`. Every other clause has a
>   supporting code line or declared finding.
>
> **What survives:** the locked-decision question, narrowed to the bound's
> precondition. P-2 is not closed. The commits it rests on so far are
> `f20e839`, `90355df`, `cf37cda`, `9f188c4` and this one.

> **ANNOTATED AT M5l (P74, C26): P-2 IS CLOSED.** The owner's re-ruled text,
> with "on a healthy feed" restored to the age bound and a sentence added for
> a feed gap, is annotated onto `CLAUDE.md`'s locked decision *Fills are
> observed by polling*. Every clause has a supporting code line or declared
> finding. So these sentences are no longer true:
>
> - *"P-2 is not closed"*, here and in C23's annotation;
> - *"Item 2, the locked decision: STILL OPEN"*, in C22's, C23's and C24's
>   annotations;
> - item 2's *"Whether to annotate the locked text, change `>` to `>=`, or
>   dedup against a shorter interval is the owner's call"*, and item 1's
>   *"Whether to change it to `>=` goes with item 2"*. Both are ruled: the
>   locked text is annotated, and it keeps the strict `>`.
>
> The commits that resolved P-2:
>
> - `f20e839` (C20): the staleness floor;
> - `90355df` (C20b): the `L + 1` call-cap precondition;
> - `cf37cda` (C22): the item-by-item record;
> - `9f188c4` (C23): the default, kept at 180 s;
> - `40a9e67` (C24): the owner's rule for locked text;
> - `127be9a` (C25): the churn wording at `M5l-094`'s sites;
> - this commit: the locked text.
>
> The earlier items stand as recorded by C22: `517348f` (C17), `25dbc61`
> (C15), `5d6f115` (C16) and `6e7c9f2` (C18).
>
> **What survives:** nothing of P-2 is carried. Its neighbours are:
>
> - P-3m, where a deferral still logs nothing;
> - P-3o, where the call cap is still the position limit;
> - P-3l, where a feed gap is still unreported.
>
> (ANNOTATED AT M5l P89, C41: P-3o's bullet is no longer true; its item is
> RESOLVED, the cap being `max(max_open_positions, L + 1)`. And C42: P-3m's
> bullet, *"where a deferral still logs nothing"*, is no longer true of the
> log; a deferral is logged as `reconciliation_deferred`, and the starvation
> and churn shapes it names stay open. And C44 to C46: P-3l's bullet, *"where a
> feed gap is still unreported"*, is no longer true; a gap is logged, a BUY across
> it is refused, and a silent pair is reported, with the stopped reconciliation
> accepted under P76.)
>
> Each keeps its own item and arming condition.

### P-3. The silent and unhedged failure modes catalogued in M5k

Each is its own carried item with its own condition, re-verified by content
at `4544b3a`.

> **ANNOTATED AT M5l (P65): TRUE OF P-3a TO P-3j, NOT OF P-3k OR P-3l.** Both
> were catalogued at M5l, not M5k. P-3k was added at `06089d5` and P-3l by
> the commit that writes this annotation, each against the tree of its own
> commit. Neither was re-verified at `4544b3a`, which predates both. P-3k
> should have carried this note when it landed. **What survives:** the
> heading's scope for P-3a to P-3j, and the rule that each item carries its
> own condition.
>
> **AND P-3m AND P-3n (P68, C19)**, both catalogued at M5l by the commit
> that adds them, and likewise not re-verified at `4544b3a`.
>
> **AND P-3o (P71, C20b)**, on the same terms.

> **THE OWNER'S P-3 ORDER, ruled at M5l P76 (C27).** The work runs in this
> order:
>
> 1. **P-3k**, design first. The design decides where P-3b's retry state
>    lives and whether `Position` carries P-3h's entry quote total.
> 2. **P-3g.**
> 3. **P-3o, merged with P-3i and with P-3m's deferral log**, using sketch
>    (a): `max_calls = max(max_open_positions, L + 1)`.
> 4. **P-3l.**
> 5. The remaining SILENT and DOC items, in P75's order: P-3e, P-3d with
>    P-3j, P-3a with P-3b, P-3c, P-3h, then P-3f. P-3n is not in this list,
>    because it goes to U7 (below).
>
> **Merges of the work, not of the entries:**
>
> - P-3a with P-3b: the same `_settle`, and one design for the Q path's
>   refusal lines and its bound.
> - P-3d with P-3j: the same hold-to-stale path. P-3j's end-to-end test is the
>   natural test for P-3d's new line.
> - P-3n into U7: it is a ruling, not code.
>
> Each entry keeps its text and its arming condition until the work that
> resolves it lands.

> **RECORDED AT M5l P93 (C47): THE OWNER'S Q12, VERBATIM, CONFIRMED BY THE OWNER
> AT P78. THIS RESOLVES `M5l-208`.** P92 found that no tracked file and no
> commit body held the text of the question P78 confirmed with *"Q12 and Q13
> confirmed"*, so the ruling existed only as reported speech. Its text, as the
> owner supplied it at P93:
>
> *"12. In-memory homes for P-3b and P-3h. P-3b's retry count: a memory-only
> field on Position beside settlement_hold, since the driver stays stateless
> (M5e). P-3h's entry quote total: a memory-only field on Position, set by the
> dispatch GET and the boot GET. Neither is recorded. Confirm."*
>
> It is the same ruling as P-3k's R2, *"The record holds only requested
> values. ... P-3b's retry count lives in memory and resets on restart."*, and
> is cited by content and by this record, never by the bare label. **What it
> governs:** `Position.failed_settlement_passes` (C47) and, in C48, the entry
> quote total. Neither is in `store.PositionRecord`.

#### P-3a. A failed supply is reported as a failed settlement (PIN-3, `M5k-107`)

At the driver an unpriced exit whose fills cannot be read is reported only by
`_settle`'s own lines, and none of them says the venue gave no quote total. So
an operator cannot tell a failed supply from a failed settlement of a priced
exit. REASONED from code.

*Arming condition:* **whoever next edits `_settle` in `execution/reconciliation_driver.py` or the Q branch of `_book_exits` there.**

> **RESOLVED AT M5l P93 (C47): *"none of them says the venue gave no quote
> total"* IS NO LONGER TRUE, AND THE ARMING CONDITION ABOVE FIRED AND IS
> DISCHARGED.** By the owner's P92-5, `_settle`'s two failure lines carry a
> clause when the exit fill was unpriced (`filled_quote_quantity is None`):
> *"the venue gave no quote total for this exit, so its fills are the only
> source of one"*. It is in the `exit_settlement_deferred` message and in the
> `exit_book_refused` `reason`, and in the `reason` of the new
> `settlement_timeout_held` CRITICAL, which omits `quote_total` as the hold line
> does. A priced exit's lines do not carry it. **What survives:** the
> observation that an operator could not tell the two apart before this; the
> Q branch's logic is unchanged.

#### P-3b. The driver re-refuses without bound where Site B stops at five (PIN-4, `M5k-104`)

An unpriced exit whose fills read short is refused and fetched again on every
due pass, with no bound, while the executor's resolution drops the same
condition after `_SETTLEMENT_RETRY_BARS` of the symbol's own candles. Order
300642's 18 identical refusals in 27 minutes are the shape, measured in the
capture `docs/RUN_LEDGER.md` §17 names.

*Arming condition:* **whoever next edits `_settle` in `execution/reconciliation_driver.py` or `_SETTLEMENT_RETRY_BARS` in `execution/executor.py`.**

> **RESOLVED AT M5l P93 (C47): *"is refused and fetched again on every due pass,
> with no bound"* IS NO LONGER TRUE, AND THE ARMING CONDITION ABOVE FIRED AND IS
> DISCHARGED.** Rulings of the owner (P92-1 to P92-4): `_settle` counts each
> failed settlement pass on `Position.failed_settlement_passes` -- a transport
> failure and a `FeeFillsIncompleteError` both count, N = 5 -- and the fifth
> calls `position.hold_settlement()` and logs one separate `CRITICAL`,
> `settlement_timeout_held`, whose resolution ends *"A restart re-settles from
> the record: the boot books it if the fills now read, and otherwise refuses the
> boot (then use the release tool)."* `HeldExit` is not widened. The bound is
> `bookability.SETTLEMENT_RETRY_LIMIT`; the executor's `_SETTLEMENT_RETRY_BARS`
> is that object under its own unit name, and a test pins that it is.
>
> **The item's evidence was already corrected by `M5l-098`:** order 300642's 18
> refusals are the partial-fill path, which makes no venue call, and the
> fills-read-short refetch has no measured instance (`M5l-211`). **What
> survives:** that the disposition differs by site -- the executor RELEASES
> unbooked at the bound, the driver HOLDS -- by the owner's ruling, and that
> `_SETTLEMENT_RETRY_BARS` reads the executor's own read count at **six**, not
> five (`M5l-216`, pinned and reported, not changed).
>
> **ARMING AUDIT AT C47, by content, of every condition P92 T4 listed.**
> *Fired and DISCHARGED:* P-3a's and P-3b's, above. *Fired and REAFFIRMED:*
> the A5 evidence-gap item's *"`_book_exits` in `execution/reconciliation_driver.py`
> or `_refine` in `execution/reconciliation.py`"* (`_book_exits`'s docstring was
> corrected; its logic and the callers' agreement on an absent `ExitFill` are
> unchanged); P-3d's and P-3j's *"`hold_settlement` in `core/models.py`"*
> (its docstring gained the P-3b caller; the hold still emits one `CRITICAL` and
> nothing recurring, so P-3d's observation now covers the timeout hold too, and
> P-3j's end-to-end staleness test is still unwritten -- C47's test drives the
> hold and the silence after it, not the staleness). *Not fired:* the orphan
> guard item (the guard and its call are untouched), P-3c's `require_bookable`
> (`bookability.py` gained a constant only), N3's executor `_settle` or
> `_defer_settlement`, and the `_log_booked` item (the booking line is untouched
> until C48).

#### P-3c. A `require_bookable` raise after the sell is contained only by the signal handler (`M5k-110`)

At Site A the guard runs after the `MARKET` sell has been sent, and `dispatch`
catches nothing on the close path. So a raise there escapes to the engine's
handler and is logged as `collaborator_failed`, far from the close it
interrupted. It is unreachable under the ruled ladder; the orderings survey
measured it escaping when the ladder is reordered.

*Arming condition:* **whoever next edits `require_bookable` in `execution/bookability.py` or `_sell_and_book` in `execution/executor.py`.**

#### P-3d. A held position emits no recurring line of its own (`M5k-083`)

After its one `CRITICAL`, a held position's only recurring trace is each
refused entry, and the `POSITION_STALE` refusal text does not name the hold.
REASONED.

*Arming condition:* **whoever next edits `hold_settlement` in `core/models.py` or `_stale_positions` in `risk/manager.py`.**

#### P-3e. A close labelled BOOKED may have written nothing (`M5k-073`)

`close_position` returns `Decimal(0)` for a symbol it does not hold, after its
fee guard, so `_book_resolved_close` returns True having written nothing if it
is ever reached without a position. A mutation bypassing the predicate
measured the label; the unwritten ledger is REASONED from the early return.

*Arming condition:* **whoever next edits `_book_resolved_close` in `execution/executor.py` or `close_position`'s absent-symbol return in `core/portfolio.py`.**

> **RESOLVED AT M5l P94 (C50): *"`close_position` returns `Decimal(0)` for a
> symbol it does not hold"* IS NO LONGER TRUE, AND BOTH LIMBS OF THE ARMING
> CONDITION FIRED AND ARE DISCHARGED.** `close_position` now raises
> `PositionNotHeldError` (`core/exceptions.py`) for a symbol the portfolio does
> not hold, after the illegal-combination and fee-denomination guards and before
> any write. `_book_resolved_close` and `_book_close` need no new branch: the
> raise lands in each one's existing `except Exception`, which logs ONE
> `CRITICAL` (`close_book_failed`, `error_type=PositionNotHeldError`) and returns
> `False`, so the caller selects `_RESOLVED_BOOK_FAILED` and no `close_booked`
> line is written.
>
> **STEP 0, every caller of `close_position` and what it does with the return**
> (H6): `_book_close` (executor) and `_book_resolved_close` (executor) assign it
> to `realised` and put it in the `close_booked` line, then return `True`;
> `_book_exits` (driver) does the same into `exit_booked` and counts
> `booked += 1`. **None branches on a zero**, and none can reach an absent
> symbol in production: the first two are handed a position, `_book_resolved_close`
> is reached only past a bookability verdict that requires one, and the driver's
> orphan guard precedes it. The only things that relied on the zero were two
> TESTS, `test_close_position_on_a_symbol_not_held_is_a_normal_zero` and
> `test_an_absent_symbol_returns_zero_and_writes_nothing_at_all`
> (`tests/unit/test_risk_manager.py`), which pinned the docstring's *"a normal
> outcome, not an error, since a `CLOSE` can arrive for a symbol the bot does not
> hold"*. That is answered upstream (`NOTHING_TO_CLOSE`, `close_no_position`), so
> the zero only ever let a booking path report a trade it had not written. Both
> were rewritten under the owner's ruled-overturn authority.
>
> **What survives:** the item's observation that the booking label was computed
> from a `True` that meant nothing was written, and that the path is
> unreachable today. The CRITICAL's and the resolution text's *"the position
> survives"* is untrue of THIS case and is left as written, because the ruling
> routes it to the existing path (`M5l-233`).

#### P-3f. Eleven tests trip the disagreement warning without meaning to (`M5k-111`)

Their close re-read is `_sold()` at `1810.57726950` against the default
settlement fill at `51.25`, so `exit_quote_totals_disagree` fires in 13 tests
where 2 intend it. No assertion reads the warning in the other 11, so a test
asserting its absence would fail on all of them.

*Arming condition:* **whoever next edits `_sold` or `_resolving_client` in `tests/unit/test_executor.py`.**

#### P-3g. Nothing refuses a pair quoted outside the base currency (`M5k-102`)

Both `_settle`s pass `quote_asset=self._portfolio.quote_asset` to
`settle_exit`, and the only comparison of a pair's quote asset with the
portfolio's is `engine/modes.py`'s holdings filter, which refuses nothing.
MEASURED (code).

*Arming condition:* **whoever next edits `_prime_pairs` in `engine/modes.py` or `settle_exit` in `core/portfolio.py`.**

> **RESOLVED AT M5l P88 (C40): *"Nothing refuses a pair quoted outside the base
> currency"* IS NO LONGER TRUE, AND THE ARMING CONDITION ABOVE IS DISCHARGED.**
> `live_system` now calls `_require_one_quote_asset` immediately after
> `_prime_pairs`, and an enabled pair whose venue-reported quote asset differs
> from `trading.base_currency` (upper-cased on both sides, which is what
> becomes the portfolio's `quote_asset`) refuses the boot with a `ConfigError`
> naming the pair, its quote asset, the portfolio's, and that settlement,
> sizing and fees assume one quote asset. **Why at the boot and not at config
> load:** the quote asset is the venue's to say, from `exchangeInfo`, and a
> config value is a bare symbol. **Ordering, MEASURED in the journal test:** it
> runs after the symbols are primed and before the account read, the store's
> resolution, both snapshots and every socket; the boot makes no venue write at
> all, so it is also before any write. The sites that assume one quote asset
> and were unchecked: `settle_exit`'s `quote_asset` argument, `close_position`'s
> and `book_restored_exit`'s fee guards, `Portfolio.equity`, sizing's `equity`
> and the affordability check, and the holdings filter in
> `_snapshot_unmanaged_holdings`. **What survives:** the sentence's observation
> that the holdings filter refused nothing, true until C40 and recorded by
> `M5k-102`; the filter stays as defence in depth.

#### P-3h. Four realised figures carry exponent -24 (`M5k-121`)

In the capture `docs/RUN_LEDGER.md` §19 names, orders 327933, 4347037,
4559541 and 5731709 booked `realised` at exponent -24, against -10, -9 or -8
on every other booking line. The cause is UNMEASURED. Realised P&L is
computed from an entry term that is `entry_fill_price x quantity`, and
`entry_fill_price` is itself a quotient, per `close_position`'s own docstring.

*Arming condition:* **whoever next edits `_realised_from_total` in `core/portfolio.py` or `_open_position` in `execution/executor.py`, which sets `entry_fill_price`.**

> **RESOLVED AT M5l P93 (C48): *"The cause is UNMEASURED"* WAS ALREADY FALSE AT
> `M5l-100` AND IS NOW MEASURED, AND THE ARMING CONDITION ABOVE FIRED AND IS
> DISCHARGED.** `M5l-209`: in all four `-24` bookings the entry order filled
> across 6 to 8 price levels, so `average_price` is a 28-digit quotient and
> `average_price x quantity` carries exponent -24; a replay reproduced value and
> exponent for 106 of 106 covered booking lines, 103 of them single-price
> entries at exponent -2. Instruments: log capture
> `3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`, fills
> capture `111d1c15a3c5fff56148f172bfbcbec85baf5aabe2128f34fb622cafe5463970`, and
> one read-only Testnet GET for order 5731709. **The values were exact in all
> four; the defect was the exponent** (`M5l-210`).
>
> **The owner's P92-6 and P92-8, built.** `Position.entry_quote_total` is a
> memory-only `Money | None`, set at dispatch and on the recovery path from the
> SAME entry GET as the price (no second call) and at boot from the boot GET's
> `Restore` decision; it is in no store record. `_realised_from_total` computes
> `exit total - entry total` and falls back to `entry_fill_price x quantity` only
> when the total is absent -- in production only for a position built without
> one, since a price implies a total (`M5l-214`). The open DEBIT is the entry
> total when present (`M5l-215`). All four booking lines -- the driver's, the
> executor's two, and the boot's -- carry `entry_quote_total`, omitted when
> absent and never `null`. The cost-basis check (`entry_fill_price is None`)
> still runs first, so a total does not make a priceless position bookable.
>
> **WHAT THIS DOES NOT DO, and it is the other half of the owner's P92-7:
> persisted totals keep the exponent they already have.** `Decimal` addition
> keeps the finest exponent, so a ledger whose `lifetime_realised` is at -24
> stays there after every later booking; that is what C49's
> `scripts/normalize_ledger_exponents.py` is for, and this commit does not touch
> any persisted file. **What survives:** the item's measurement of the four
> bookings, and the observation that the figures were value-correct.
>
> **ARMING AUDIT AT C48, by content, of every condition the checker lists for
> the symbols this commit edits.** *Fired and DISCHARGED:* P-3h's, above.
> *Fired and REAFFIRMED:* P-3e's *"`_book_resolved_close` in
> `execution/executor.py`"* -- the method now reads the position BEFORE
> `close_position` deletes it, for the line's entry total, and returns the same
> `True` it did, so P-3e's unwritten-ledger case is unchanged; the A5 item's
> *"`_book_exits` in `execution/reconciliation_driver.py`"* and the orphan-guard
> item's *"its caller in `_book_exits`"* -- the only edit is one more keyword on
> the `_log_booked` call, and the guard and the `ExitFill` agreement are
> untouched; A6's *"the booking line: `_log_booked` in that file or
> `execution/booking_line.py`"* -- the line gained a field, and A6's point (two
> calls, not one decision path; the remedy is wording) is unaffected. *Not
> fired:* P-3e's other limb, `close_position`'s absent-symbol return (its
> docstring changed, the return did not); `M5i-104`'s unpack condition (this
> commit writes none -- every log assertion asserts a length first); and every
> condition naming `_settle`, `hold_settlement` or `_SETTLEMENT_RETRY_BARS`.

> **ADDED AT M5l P93 (C49), THE OTHER HALF OF P-3h: THE PERSISTED EXPONENT
> (the owner's P92-7).** C48 stops new bookings carrying exponent -24; nothing
> repairs what is already on disk, because `Decimal` addition keeps the finest
> exponent (`M5l-210`). `scripts/normalize_ledger_exponents.py [--store PATH]
> [--apply]` is that repair, a ONE-OFF.
>
> - **Lossless-only, proved per value.** A ledger figure finer than eight decimal
>   places is quantised to eight only if the result EQUALS it. One that would
>   lose a digit is never rounded: the tool lists every such value, writes
>   nothing and exits 1. A figure already at -8 or coarser is left alone.
> - **It touches the ledger's three money sites and nothing else**: the open
>   day's `realised_pnl`, each `daily_history[...].realised`, and
>   `lifetime_realised`. Positions, pending records, dates and counts are carried
>   through `store.load` and `store.save` as they were.
> - **It refuses a store at another schema.** `store.save` writes the current
>   schema, so normalising an older file would upgrade it and add `positions`.
>   MEASURED on a copy of the 2026-09-17 store: schema 1 came back as schema 2
>   with `positions: []`. Run the bot's own build once, which does that, then
>   this.
> - **It refuses while the bot runs**, with the bot's own non-blocking instance
>   lock held for the whole run, as `release_position.py` does; and it writes
>   only on `--apply`, printing what it would change otherwise.
> - **It logs both SHA-256s**: one line appended to `logs/normalize.log` and
>   printed, `store_sha256_before` and `store_sha256_after`.
>
> **MEASURED on COPIES of the evidence store** (SHA-256 `5164ccc0...`, the same
> file `M5l-210` read), in scratch directories with that file untouched. The
> copy is at schema 1, and the final tool REFUSED it, as above. Upgraded the way
> the bot's build does (`store.save(store.load())`, SHA-256 `a25ddfef...`), the
> tool changed six values -- the open day's `5.0814517000`, the `2026-09-10`
> row's `2.885073700000000000000000`, three more history rows at exponent -10,
> and `lifetime_realised` `-209.601849800000000000000000` -- each to eight
> places and each equal in value, to the file whose SHA-256 is
> `15c91a0d239f8881f3ebba81e2366dbe64d14e3638fdeb86754afef4f6ed1b2c`; a second run
> found nothing to do. An earlier build of the tool without the schema check,
> run straight on the schema-1 copy, produced the same final bytes plus the
> schema upgrade, which is why the check exists.
>
> **OPERATOR RULE.** Stop the bot. From the clone whose store is to be repaired,
> run the tool WITHOUT `--apply` and read what it would change, then with it.
> Run it once. **Its lock covers the clone it is run from and no other**, as the
> release tool's does (`M5l-155`). The ACTIVE deployment clone's store has not
> been read or changed by this commit; whether it carries exponent -24 is still
> UNMEASURED, and running this against it is the owner's act.
>
> *Arming condition for the tool's reuse of the store:* **whoever next edits
> `store.save` or `PersistedState` in `persistence/store.py`, or the instance
> lock's path handling in `utils/instance_lock.py`, now has TWO reusers --
> `scripts/release_position.py` and `scripts/normalize_ledger_exponents.py`.**
> The release tool's condition (above, C34) is REAFFIRMED and not fired: this
> commit edits none of those symbols.

#### P-3i. Settlement runs outside the driver's call count (`M5k-060`)

`remainder = self._budget.max_calls - len(assessments)` covers the pass and
the point queries only, so a phase may make up to `max_calls` plus one call
per bookable exit. The coherence check's third term reserves the time; nothing
in `src/` tracks request weight. MEASURED.

*Arming condition:* **whoever next edits `ReconciliationBudget` in `execution/reconciliation_driver.py`.**

> **PARTLY RESOLVED AT M5l P89 (C43): THE CALL COUNT IS NOW REPORTED, THE
> REQUEST WEIGHT IS NOT, AND THE ARMING CONDITION FIRED AND IS DISCHARGED FOR
> THE COUNT.** *"A phase may make up to `max_calls` plus one call per bookable
> exit"* stays true: settlement is still outside `max_calls`, and nothing
> changed its budget. What changed is that it is said. A phase that made a
> settlement fetch logs `reconciliation_phase_calls` at `INFO` with
> `pass_calls`, `point_queries`, `settlements` and `max_calls`, so the overrun
> is their sum against the cap. `point_queries` is derived from the legs the
> resolver left unresolved (the pass line's `queries` field is the remainder, not
> work, `M5g-085`) and is absent when the resolver failed. This is ACCOUNTING
> and LOGGING; no budget semantics moved, so H6 did not fire for the count.
>
> **WHAT STAYS OPEN: *"nothing in `src/` tracks request weight"* is still
> true, and it is not closable by logging.** The port returns no response
> headers, so a call is counted and never weighed, and a per-endpoint weight
> table would be the venue's documentation and not a measurement. Counting
> weight needs the port to carry what the venue reports, which is new
> semantics and the owner's. Nothing here weighs a call.
>
> **ARMING AUDIT AT C43, by content.** C43 edits `ReconciliationDriver.__call__`,
> `_book_exits` and the `ReconciliationBudget.max_calls` comment. Fired and
> REAFFIRMED, each unaffected because the edit is a counter and a log: P-3a's
> *"the Q branch of `_book_exits`"* (the counter is incremented there, and the
> branch's logic is unchanged); the A5 evidence-gap item's *"`_book_exits` or
> `_refine`"*; `M5i-065`'s *"the orphan guard or its caller in `_book_exits`"*
> (the guard is untouched); and the trigger item's
> *"`ReconciliationDriver.__call__`"* (what triggers a pass is unchanged).
> Not fired: P-3b's, which names `_settle`, not edited. Reported, not made
> false by C43: the A5 item's *"`exit_unbookable` occurs zero times: the
> escalation has never run"* is false of the 2026-10-01/02 supervised run, which
> logged it on passes of both of A4's runs, the failed one and the one that
> passed (`docs/RUN_LEDGER.md` section 25).

#### P-3j. No end-to-end test drives a hold to stale (`M5k-090`'s limit)

The staleness rows call `hold_settlement()` on a hand-built position. Nothing
drives the driver's hold, the stopped stamp and the elapsed time together.
REASONED.

*Arming condition:* **whoever next edits `hold_settlement` in `core/models.py`, `_stale_positions` in `risk/manager.py`, or the held filter in `reconcile_open_positions` in `execution/reconciliation.py`.**

#### P-3k. A restart orphans an ordinary open position (`M5l-045`, `M5l-044`)

**IMPLEMENTED (C28-C34). The live-trading gate stays closed until the
supervised run's arms A1, A2 and A4 are recorded in RUN_LEDGER.** The
template for that run is `docs/RUN_LEDGER.md` section 24. What follows is the
item as it stood before the implementation and the annotations that track it;
the commits are recorded beneath it.

> **P-3k IS CLOSED, BY THE OWNER'S RULING AT M5l P87 (C38) -- THE FIRST
> SENTENCE'S GATE, *"stays closed until the supervised run's arms A1, A2 and
> A4 are recorded"*, IS DISCHARGED.** The ruling, verbatim: *"The P-3k gate is
> satisfied: A1 (hard kill, restore), A2 (protective fill while down, booked at
> boot) and A4 (protection cancelled while down, R3 sells once) passed on the
> supervised Testnet run of 2026-10-01/02, A1 and A2 at d1074c6 and A4 at
> 5e22bc6. A2's Ctrl+C stop does not change the path it tests. P-3k no longer
> blocks live trading. The fee-capture and base-asset-netting gates remain, so
> live trading stays blocked."* The arms are recorded in `docs/RUN_LEDGER.md`
> section 25 (`M5l-168`, `M5l-169`). **What survives:** the item's history and
> every annotation beneath it, the *"Live trading additionally stays blocked
> until an open position survives a restart"* ruling at P76 as the record of
> what the gate was, and **live trading itself, which stays blocked by N6's two
> remaining preconditions** -- the non-zero fee capture and base-asset
> netting. Closing P-3k lifts one of three gates and none of the code block:
> `refuse_live_trading` is unchanged.

Positions are memory-only, so a clean shutdown or a power cut leaves an open
position no later process owns. After a restart the symbol is blocked while its
list rests; a protective fill in that window is never booked, so the daily-loss
halt undercounts; once the list completes or is cancelled, the base asset
becomes an unmanaged holding the bot never sells (M5l-045, M5l-044).

> **ANNOTATED AT M5l P79 (C30): *"Positions are memory-only"* IS NO LONGER
> TRUE OF THE FILE.** From C30 both of the root's writers put one record per
> open position into `data/state.json`, held positions included. **What
> survives, and it is the item:** nothing reads those records until C32, and
> each boot's first save erases them, so a position still does not survive a
> restart and every consequence above stands.
>
> **ANNOTATED AT M5l P81 (C32a): "nothing reads those records until C32" IS
> NO LONGER TRUE.** From C32a the boot restores a record whose list is live,
> and drops one that expired, never placed or is gone, where each boot's
> first save used to erase it. A record beside a pending close is still
> erased, by the owner's interim ruling. A filled exit, and a position whose
> protection is gone with its base held, refuse the boot until C32b.
> **What survives:** the gate on live trading, and this item, until C32b
> books and sells and C33 corrects the P77 S6 texts.
>
> **ANNOTATED AT M5l P82 (C32b-1): "A filled exit ... refuse[s] the boot" IS
> NO LONGER TRUE.** A filled exit is booked at boot, or held with its record
> kept and no position; see the C32b-1 record below. The half about a
> position whose protection is gone with its base held stands until C32b-2.
>
> **ANNOTATED AT M5l P82 (C32b-2): that half is no longer true either.** Such
> a position is restored and sold on its symbol's first candle; see the
> C32b-2 record below.
>
> **ANNOTATED AT M5l P82 (C32b-3): "A record beside a pending close is still
> erased, by the owner's interim ruling" IS NO LONGER TRUE.** The interim
> exclusion is removed: such a record is classified with its close and
> restored, booked, held or sold by the final design below, and no boot save
> erases it. **What survives:** the gate on live trading, and this item, until
> C33 corrects the P77 S6 texts.

**It is a GATE ON LIVE TRADING**, beside the two N6 names -- the non-zero fee
capture and base-asset netting. The owner's M5l ruling, quoted at the head of
this file, keeps *"The architectural live-trading block"* *"strictly active"*
and names those two as what live execution waits on; this third was added to
them by the owner at P61. Its place in P-3 is the same ruling's third
priority, *"eliminating the unhedged/silent failure modes"*.

> **THE OWNER'S RULING, VERBATIM, M5l P76 (C27):** *"Live trading
> additionally stays blocked until an open position survives a restart,
> clean or by power cut, with its protective fills booked to the ledger."*
> Until P76 the tree recorded this gate only as the owner's addition at P61,
> in reported speech (`M5l-099`). The ruling also states what lifting it
> requires: survival of both a clean restart and a power cut, AND the
> protective fills booked.

**It is not N1.** N1 reads: *"A position is not persisted, so a restart
releases a hold, and a close deferred before a restart is released unbooked
after it (`M5k-065`)."* That covers a held position and a deferred close. This
is an ordinary protected position with no hold and no close, which no item
covered until now (`M5l-045`).

**The worked instance is `M5l-044`:** bot entry 6688668, list 317428, left
protected by a clean shutdown on 2026-09-26; its legs were cancelled
unexecuted at 2026-09-27T03:50:23.068Z, and the 0.02151 BTC it bought sat as an
unmanaged holding until the owner sold it with
`scripts/clear_testnet_holdings.py`. The blocked symbol, the
unbooked fill and the unmanaged holding are REASONED from `live_system`'s boot
snapshots; the holding and its exclusion were MEASURED in that instance
(`M5l-036`). No protective fill in such a window has been observed.

**ADDED AT M5l P79 (C30), the writers.** Three records the project owner
directed for this commit.

- **Deployment, verbatim:** "No deployment or supervised run may use any
  commit from 131f1c9 up to C32b's: records are written from C30, and boot
  reads them only from C32, so each boot's first save erases them (today's
  behaviour, not a regression)."
  > ANNOTATED AT M5l P81 (C32a): *"each boot's first save erases them"* is
  > no longer true of a record not beside a pending close; the boot now
  > restores or drops it. The restriction itself stands, through C32b.
- **The accepted residual, verbatim:** "One kill during one ambiguous
  placement write loses that position's durability (M5l-110); accepted by the
  owner at P78 (Q2(b))." The ambiguous-placement path, `_persist_dropping`, is
  unchanged by C30.
- **Sentences that read "persisted" as "survives a restart" -- the owner's
  ruling R-A at P79.** Each stays as written for C30, because it stays true
  until C32: each boot's first save erases the records. C32 and C33 correct
  them under P77 S6. The owner named the first three; C30's own search found
  the last two, which read the same way.
  - `CLAUDE.md`, the R2 hold bullet among the locked decisions: *"positions
    are not persisted, so a restart forgets the hold"*.
  - `docs/QB_ESCALATION.md`, site 5: *"Positions are not persisted either, so
    on restart `positions` is empty"*.
  - `src/trading_bot/execution/booking_line.py`, the held exit's `CRITICAL`
    string: *"A restart releases the hold, because the position is not
    persisted"*.
  - `CLAUDE.md`, the M5k paragraph under Current state: *"A restart releases
    the hold, because positions are not persisted."*
  - `tests/unit/test_modes.py`, the docstring of
    `TestADeferredSettlementAcrossARestart.test_a_held_close_is_released_unbooked_after_a_restart`:
    *"positions are not persisted -- so the mark is gone"*.

**ADDED AT M5l P80 (C31), the boot classifier.** `execution/restoration.py`,
pure: no I/O, no clock, no write. Nothing calls it yet; C32 does.

- `refuse_disabled` is R5, callable before any venue call. `reads_needed`
  returns the venue order ids to GET (Q10(b)) and the refusals decidable
  without a read. `classify` returns exactly one decision per position record,
  then one per pending placement, in input order. Pending close records are
  not classified (Q13).
- The decisions: `Restore`, `BookExit`, `RestoreAndClose`, `Gone`,
  `DropExpired`, `DropNotPlaced` and `RefuseBoot`. Only `RestoreAndClose`
  implies a venue write, and it is the only one whose `writes_to_venue` is
  true. The full table is the module's docstring.
- Several matching lists refuse the boot even when exactly one is live,
  where `resolve_placement` answers `PLACED_LIVE`: the P80 prompt rules
  "several match" a refusal.
- **Three choices the rulings did not make, for the owner to see:**
  - Every leg of a matched list is read, not only the working leg that the
    P77 specification's boot table (S3, in the report, not in the tree)
    listed, because Q11 refuses a partial execution on any leg and a
    live list's protective leg is seen only by reading it. A live record
    costs one GET per leg (`M5l-123`).
  - `Gone` reads the base's total, and `RestoreAndClose` its free balance
    (`M5l-122`).
  - `Restore`, `BookExit` and `RestoreAndClose` also carry the matched order
    list and the entry economics, so C32 need not match or read again.
- The records are typed by a protocol, `Requested`, which the store's
  `PositionRecord` and `PendingRecord` and the executor's `PendingPlacement`
  all satisfy, so `execution/` still imports no store.
- The gate's file counts move with it: `ruff format` to 135 files and `mypy`
  to 81 source files.

**ADDED AT M5l P81 (C32a), boot wiring.** `live_system` in `engine/modes.py`
now resolves the store's records at boot, under P77's S3 and the owner's
rulings:

- R5 (`refuse_disabled`) runs before the lock and before any venue call.
- After `_seed_portfolio` and before both snapshots:
  - one `get_all_order_lists`, which `_snapshot_live_order_lists` now reuses
    instead of reading again;
  - one `get_order` per leg orderId, bounded by `risk.reconcile_deadline_s`
    at one attempt. A failed read refuses the boot (Q6(a)).
- The decisions are then applied:
  - `Restore` goes through `restore_position`, with no debit;
  - `DropExpired`, `DropNotPlaced` and `Gone` drop the record, each with its
    own line;
  - every refusal is collected into one `ConfigError`.
  - Then one save, and a summary line, `boot_positions_resolved`.
- Both snapshots skip the symbols it restored (I5, `M5l-103`).
- A boot that completes has settled every restored placement, so the executor
  receives restored CLOSES only. Its first-candle placement path stays,
  defensively, for placements made ambiguous during a run.

**THE INTERIM REFUSALS, until C32b.** `BookExit` and `RestoreAndClose` refuse
the boot with the reason "`<decision>` is handled from C32b", so nothing C32b
would book or sell is dropped in between.

> **ANNOTATED AT M5l P82 (C32b-1): `BookExit` NO LONGER REFUSES THE BOOT**;
> it is booked or held. `RestoreAndClose`'s interim refusal stands until
> C32b-2.
>
> **ANNOTATED AT M5l P82 (C32b-2): THE INTERIM IS OVER.** `RestoreAndClose`
> no longer refuses the boot either; it restores and is sold.

**THE OWNER'S R-A EXTENSION, P81.** The five R-A sentences listed under C30
above stay as written through C32b, because P-3k's deployment restriction
means no deployable restart runs on these commits. C33 corrects every P77 S6
text.

> **DISCHARGED AT M5l P83 (C33), the five R-A sentences one by one.**
> 1. `CLAUDE.md`, the R2 hold bullet's *"positions are not persisted, so a
>    restart forgets the hold"*: annotated at C33 under the S6 rule.
> 2. `docs/QB_ESCALATION.md`, site 5's *"Positions are not persisted either"*:
>    annotated at C33.
> 3. `booking_line.py`'s hold `CRITICAL`: the message was replaced, at C32b-1 and
>    C32b-3, and at C34 names the release tool.
> 4. `CLAUDE.md`, the M5k paragraph: annotated at C32b-3.
> 5. `test_modes.py`'s docstring *"positions are not persisted -- so the mark is
>    gone"*: gone with the rewrite of that test at C32b-3.

**A POSITION RECORD BESIDE A PENDING CLOSE -- the owner's rulings, P81
amendment 1.**

- *Interim, C32a, verbatim:* "a position record whose symbol has a pending
  CLOSE record is neither classified nor restored. It is left out of the
  classifier's input, and boot's save does not carry it, which is today's
  behaviour. Site B handles the close as today."
- *Final design, for C32b, verbatim:* "For a close record beside a position
  record, read the close's sell by the client id in the close record:"
  - "FILLED: settle at boot. On success, book ledger-only (I7), satisfying
    Q13. On FeeUnresolvable, keep a held record with no Position (Q5(b),
    M5l-112). Remove the close record either way."
  - "Absent, or terminal and unfilled, with the legs CANCELED and base >=
    quantity: RestoreAndClose, dropping the close record, so exactly one sell
    goes out."
  - "List live: Restore; the close record's fate is decided in P82 after STEP
    0 reads Site B."
  - "Anything else: RefuseBoot."
  - "The two restart tests' assertions change once, in C32b."
- Why it was needed (`M5l-126`): the bot's own close cancels the protective
  legs by design, so the classifier reads that list as `Gone` or
  `RestoreAndClose`, and Q13 collides with Q5(b) on the same disk shape.

> **ANNOTATED AT M5l P82 (C32b-3): THE INTERIM IS OVER AND THE FINAL DESIGN
> IS BUILT.** The "Interim, C32a" bullet no longer describes the tree: no
> record is left out of the classifier's input and the boot's save carries
> what the decisions leave. The *"List live"* row is settled by P82's STEP
> 0(b): the position is restored and the close record is KEPT, and Site B, on
> the first candle, finds no sell, keeps the position UNKNOWN and releases the
> record, selling and booking nothing. *"The two restart tests' assertions
> change once, in C32b"* is discharged: both changed at C32b-3.

**ADDED AT M5l P82 (C32b-1), a filled exit at boot.** A `BookExit` is
settled at boot: one `get_my_trades` for the filled leg's order, bounded by
`risk.reconcile_deadline_s` at one attempt, then `settle_exit` and the
bookability ladder the runtime booking sites use.

- **Booked** through `Portfolio.book_restored_exit`: ledger only (I7), on the
  fill's UTC day (R4), in ascending fill time across records (I9), with one
  `boot_exit_booked` line. The record leaves the store.
- **Held** when the fee is one this ledger cannot subtract, or a fill is not
  a sell (R2): the record is KEPT, no `Position` is created (Q5(b),
  `M5l-112`), the symbol is BLOCKED, and one `exit_settlement_held` CRITICAL
  carries `site=boot`. Every later save carries the held record, beside the
  live positions, until an operator releases it -- the tool is C34's.
- **Refused**, with the record left on disk, when the fills cannot be read,
  do not yet account for the execution, or the exit has no cost basis: each
  is a record this boot cannot resolve (Q6(a); the owner accepted this as
  draft choice 1, `M5l-133`).
- A pending placement whose list filled and then exited while down, and whose
  exit is HELD, is kept as the position record it would have become (draft
  choice 2, accepted, `M5l-134`).
- When the venue's quote total and the sum of the fills disagree, the boot
  booking emits `exit_quote_totals_disagree`, `site=boot`, exactly as the
  runtime sites do, and books the venue's total (draft choice 3, overruled
  by the owner, `M5l-135`).
- Boot now DECIDES every record, then REFUSES, then APPLIES, so a refused boot
  changes neither the portfolio nor the disk; and its save reads the ledger,
  the history and the lifetime total live from the portfolio, which the
  bookings wrote.

**ADDED AT M5l P82 (C32b-2), protection gone and base held (R3, Q4(b)).** A
`RestoreAndClose` is restored UNKNOWN with no debit and named by one
`boot_position_unprotected` CRITICAL, whose message carries M5l-125's operator
rule: if you acted on this symbol by hand, release its record before
restarting.

- The sale is R3's synthetic `CLOSE`, dispatched by `_BootCloser`, a candle
  subscriber registered after the executor and only when boot restored such a
  position. On the symbol's first candle it hands the executor a `CLOSE` and
  an approved exit, and the executor's own path, traced at P82's STEP 0, does
  the rest: the legs read cancelled, the ALL_DONE list's cancel answers
  `-2011`, which that path treats as normal, and exactly one MARKET sell goes
  out and books through `close_position`.
- Until it books, UNKNOWN keeps every entry refused. The reconciler's first
  pass on that bar classifies the list `DIVERGED` and escalates once per pass
  until the position is gone.
- **One attempt per symbol** (`M5l-137`): if the executor refuses the sale,
  the position stays restored and UNKNOWN, entries stay refused, and the
  strategy's own `CLOSE` path is still open.

**ADDED AT M5l P82 (C32b-3a), `-2013` maps to `OrderNotFoundError`
(`M5l-138`).** C32b-3's draft read the close's sell by its client id and took
`OrderNotFoundError` for "the sell is absent". The owner's P82 amendment 2
measured that read on Testnet before the commit: a GET order by a fabricated
client id in our `-CL` format answered `-2013 "Order does not exist."`, and
`translate_binance_error` returned a bare `ExchangeAPIError`, because
`_API_RULES` keyed `OrderNotFoundError` on `-2011 "Unknown order sent."` alone.
The owner's amendment 3 ruled the fix: one row, `-2013`, anchored on the whole
measured message as the `-2011` row is.

- **Tests**: the measured payload maps to `OrderNotFoundError`, exact type and
  ancestry and code kept; two near-miss messages, one with a tail and one with
  a head, do not, so loosening either anchor is caught; the unmatched `-2013`
  logs once at ERROR and the measured one does not.
- **STEP 0(b), what each catcher did on a venue-absent order and does now**
  (`M5l-139`, REASONED from the code; the type itself is MEASURED):
  - `reconciliation.py` `resolve_unresolved_legs`, the only site that
    branches on the type. Before: `-2013` escaped as `ExchangeAPIError`, so the
    driver's `leg_resolution` phase failed for EVERY position in that pass.
    Now: that one leg is `DIVERGED` ("the venue has no such order"), and the
    pass goes on. Nothing is booked, sold, cancelled or dropped; the position
    keeps untrusted protection, and `_escalate_unbookable_divergence` logs one
    `CRITICAL` per pass.
  - `executor.py` `_entry_fill_price`, `_requery_sell_total`,
    `_read_close_outcome`, `_confirm_protective_legs`, and this tree's boot
    reads: each catches broadly and does not branch on the type, so the
    behaviour is unchanged. `_confirm_protective_legs` records
    `type(exc).__name__` in a log field only.
  - `executor.py` `_cancel_protection`'s `except OrderNotFoundError` and the
    `ExchangeError` catches around `get_my_trades`
    (`_settle` in the executor and the driver) are not reached by `get_order`.
- **Captures**: `-2013` and "Order does not exist" occur on 0 lines in all 14
  logs checked (`M5l-140`), so the resolver's `-2013` branch has never run in
  production. None of the 12 `reconciliation_phase_failed` lines in the M5k
  close capture is explained by it: all 12 are `ExchangeConnectionError` in
  phase `reconciliation_pass`.
- **Not measured, and it bounds C32b-2** (`M5l-141`): R3's sale rests on
  `cancel_order_list` of an ALL_DONE list answering `OrderNotFoundError`. No
  capture holds that answer (`docs/RUN_LEDGER.md` reads
  `close_cancel_already_terminal` NOT OBSERVED), and its message is not known to
  be `-2011 "Unknown order sent."`. If it differs, the cancel fails at
  `CRITICAL`, the record is released and nothing is sold: the safe direction,
  and the position stays restored and UNKNOWN.

> **ANNOTATED AT M5l P85 (C35): `M5l-141` IS RESOLVED BY MEASUREMENT, AND THE
> SAFE DIRECTION IS WHAT HAPPENED.** The bullet above predicted *"If it
> differs, the cancel fails at `CRITICAL`, the record is released and nothing
> is sold"*, and at A4 of the P-3k supervised run it did: on Testnet at
> `2026-10-01T18:30:03Z`, list 401075 (ETHUSDT, `ALL_DONE`), the venue answered
> `-2011` with `'Unknown order list sent.'`, not `'Unknown order sent.'`; no
> row matched, an ERROR `Unclassified message` was logged, `close_cancel_failed`
> fired at `CRITICAL` and nothing was sold (`M5l-161`). C35 adds the row
> `^Unknown order list sent\.$` to `OrderNotFoundError`. What survives: the
> bullet's reasoning that a mismatch fails safe, which the run confirmed. The
> arming condition below FIRED at C35 and is REAFFIRMED for the next row.

`M5l-138`'s row is the first `_API_RULES` row keyed on a code that is not in
`_ORDER_REJECT_CODES`, so a near-miss falls through to `ExchangeAPIError`
rather than `OrderError`.

*Arming condition:* **whoever next adds a row to `_API_RULES` in `exchange/models.py`.**

**ADDED AT M5l P82 (C32b-3), a close beside a position record (P81
amendment 1's final design).** The interim exclusion is removed. A position
record whose symbol has a pending close is classified with it: the close's sell
is read by the client id the close record derives (`close_sell_id`), one GET
bounded like every boot read, and `OrderNotFoundError` is the answer "absent".
The decision, per the owner:

- **Legs cancelled and the sell FILLED**: `BookExit` of the sell, with no leg.
  It is settled and booked ledger-only, or held (Q5(b)), exactly as a leg's
  exit is, and the close record is removed either way. The booking line carries
  `close_client_order_id` where a leg's carries `leg`.
- **Legs cancelled and the sell absent, or terminal with nothing executed,
  with the base free at least the quantity**: `RestoreAndClose`, and the close
  record is removed, so `_BootCloser`'s sell is the only one.
- **List live and no sell**: `Restore`, and the close record is KEPT for Site B
  (P82's STEP 0(b)).
- **Anything else** refuses the boot, including a close that does not match
  its record, a sell that was not read, a sell read that fails with any error
  but `OrderNotFoundError`, and legs cancelled with the base gone.

Two P82 amendment 2 rulings land with it. This row of P77 S6 is superseded,
recorded under the standing authorities. And `hold_fields`' resolution text no
longer says a restart releases the hold: *"A restart keeps the hold: boot
re-derives it from the venue's fills and keeps the record, with the symbol
blocked."* Its neighbouring sentence, *"Enter this trade by hand, then
restart"*, is left as written and is reported (`M5l-143`), and the text
C32b-1 left false is `M5l-144`.

> **ANNOTATED AT M5l P83 (C34): "left as written and is reported (`M5l-143`)"
> IS NO LONGER TRUE.** The sentence was replaced by the release command in
> C34, and `M5l-143` is resolved there.

**The interim refusals are removed and the no-deployment window closes at
C32b's last commit**, C32b-4. **The supervised run still waits for C34**,
M5l-125's release tool: a held record has no way out until it exists.

> **ANNOTATED AT M5l P83 (C34): THE TOOL NOW EXISTS**, so a held record has a
> way out and "has no way out until it exists" is no longer true. The
> supervised run's other precondition is the documents commit, C33.

**ADDED AT M5l P82 (C32b-4), `M5l-120`'s test, and it changes no `src/`.**
`M5l-120` said that after C30 a raise from `_open_position` following a
successful placement leaves the pending record in memory and on disk, and that
*"No test exercises the raise"*. One does now:
`test_a_raise_after_a_placed_list_keeps_the_pending_record_and_refuses_the_symbol`
in `tests/unit/test_executor.py` makes `_open_position` raise after the list is
placed and its fill read, and asserts that the raise escapes `dispatch`, the
record is still in `_pending`, no removal write reached disk, no position
exists, and a second entry for the symbol is refused as `placement_pending`
without a second list. Its mutation, the pre-C30 order, also fails
`test_no_save_between_placement_and_position_lacks_both_records` and
`test_a_delete_failure_logs_and_continues_without_raising` (`M5l-149`).

That the raise escapes is a fact the test measures and the module docstring's
*"It must never raise"* does not cover: `_open_position` has no `try` of its
own, and what contains the raise is `TradingEngine._emit`'s isolation
(`M5l-150`). Nothing changes here; it is recorded.

**ADDED AT M5l P83 (C34), the release tool (M5l-125).**
`scripts/release_position.py --symbol SYMBOL [--store PATH] [--preview]`, run
from a deployment clone's root with the bot stopped. It is the only way out of
a record the boot refuses or holds, short of editing `data/state.json` by hand.

- **It refuses while the bot runs**: it takes the bot's own non-blocking
  instance lock, holds it for the whole run and releases it on exit.
- **It loads through `store.load`**, so the schema check applies, finds every
  record for the symbol -- the position, a pending placement, a pending close
  -- and prints each in full with the list id our seeds derive. None found, a
  corrupt store or a missing one exits 1 and writes nothing.
- **`--preview` is GET-only**: it reads the order lists, the legs, the close's
  sell, the balances and the symbol's filters, and prints what the boot would
  decide with `reads_needed` and `classify`. A failed read prints `preview
  unavailable` and the run goes on. It never calls the venue otherwise.
- **The operator types the symbol exactly**; anything else aborts, nothing
  written. Only that symbol's records are removed, through `store.save`, and
  one line goes to `logs/release.log` with the store's SHA-256 before and after.
- **The messages name it.** The held-exit message's *"Enter this trade by hand,
  then restart"*, which told an operator to do what keeps the hold, now reads
  *"Resolve it at the venue, then release the record: python
  scripts/release_position.py --symbol <SYMBOL>"*: **`M5l-143` is resolved**,
  and the `<SYMBOL>` is a literal placeholder (`M5l-153`). So do the boot's
  four record-related refusals, R3's `CRITICAL`, the held exit's `CRITICAL` and
  the symbol's block reason.

**The tool's limits, stated.** Its lock is keyed on the working directory's
`logs/.bot.lock`, so it excludes the bot of the clone it is run FROM and no
other (`M5l-155`): release a clone's store from that clone. And `--preview` is
what separates releasing a resolved position from discarding a live one; the
tool does not require it (`M5l-156`).

*Arming condition:* **whoever next edits `store.save` or `PersistedState` in `persistence/store.py`, or the instance lock's path handling in `utils/instance_lock.py`, which `scripts/release_position.py` reuses.**

**ADDED AT M5l P83 (C33), the documents.** No behaviour changes. Every P77 S6
row is now annotated or corrected, listed in C33's commit message by content,
before and after; the two C32a test names that described the old behaviour are
renamed (the pytest count does not move); `dispatch`'s *"must never raise"* is
annotated in the executor's module docstring (`M5l-150`); `CLAUDE.md`'s
deployment procedure gains the active-clone store source, the schema step
(`M5l-107`) and the release tool's operator rule (`M5l-125`); and
`docs/RUN_LEDGER.md` section 24 is the supervised run's template, arms A1 to A7
with the expected lines. **P-3k is IMPLEMENTED (C28-C34)**, and its gate is
open only to A1, A2 and A4 recorded in section 24.

> **ANNOTATED AT M5l P88 (C39): *"its gate is open only to A1, A2 and A4
> recorded in section 24"* IS NO LONGER TRUE, AND WAS SUPERSEDED AT P87.** The
> arms are recorded in section 25, not 24, which stays the template (`M5l-175`,
> resolved here), and the gate is closed by the owner's ruling, quoted verbatim
> at P-3k's head. **What survives:** section 24 as the arms' expected lines.

**ADDED AT M5l P85 (C35-C37), the supervised run's first results.** The
run started at `d1074c6` and is recorded in `docs/RUN_LEDGER.md` section 25.
**A1 passed** (`M5l-165`: both records restored, `free_quote` reconciled to the
digit). **A4 FAILED** (`M5l-161`): R3's cancel of an `ALL_DONE` list was
answered `-2011 'Unknown order list sent.'`, which no row mapped, so the
close failed at `CRITICAL` and nothing was sold. **C35 (`244aa6b`) maps it**,
and C36 (`d95cb5e`) corrects the cancel script's stale warning
(`M5l-163`). **A2's line is already in the log** (`M5l-166`), from a Ctrl+C stop
rather than the hard kill the arm names; whether it counts is the owner's
judgement. **THE GATE STAYS CLOSED.** It opens only when **A4 is re-run on the
commit carrying C35** -- `244aa6b` or a descendant, deployed as its own clone
per the procedure -- and recorded in section 25. **A1's and A2's evidence from
`d1074c6` stands**, because neither path cancels an order list: A1 restores
records and reconciles, A2 books an exit the venue already filled, and the
answer C35 changed is the answer to a list cancel, made only by the close path.

> **SUPERSEDED AT M5l P87 (C38): *"THE GATE STAYS CLOSED. It opens only when
> A4 is re-run on the commit carrying C35"* HAS HAPPENED, AND *"A2's line is
> already in the log ... whether it counts is the owner's judgement"* IS
> RULED.** A4 was re-run at `5e22bc6` and passed (`M5l-168`), and the owner
> ruled A2 a pass and the gate satisfied (`M5l-169`, `M5l-166` resolved). See
> P-3k's head. **What survives:** the reasoning that A1's and A2's `d1074c6`
> evidence stands because neither path cancels a list.

The operator's release and manual ETHUSDT sale of that run cost
`-6.91308000` USDT outside the ledger (`M5l-164`, section 25).

**C33's S6 rows that remain by design.** Two S6 sentences are NOT changed, each
for a stated reason. `modes.py`'s block message *"the position it belongs to
was lost when the previous process ended"* is a code string, outside C33's
fence, and is still true of a live list with no record (`M5l-159`). And
`executor.py`'s *"Only a restart forgets"* comment under U2's Reading A is
still true: the unconfirmed placement's durable record is dropped on purpose.

*Arming condition:* **whoever next changes what `PersistedState` in `persistence/store.py` persists, or `_snapshot_unmanaged_holdings` or `_snapshot_live_order_lists` in `engine/modes.py`, which are `live_system`'s boot reconciliation.**

#### P-3l. A market-data outage stops reconciliation (`M5l-055`)

A market-data outage stops reconciliation, because passes are driven by candle
arrival: at M5l's evidence run no pass ran for 300 s against a 180 s staleness
bound while list 333832 was open, and no line reported it (M5l-055).
Venue-side protection stayed in force; what is lost is the bot's knowledge of
the position.

> **ANNOTATED AT M5l (P68, C19): *"against a 180 s staleness bound"*
> COMPARES THE GAP WITH A BOUND THE GUARD NEVER APPLIED THERE (`M5l-074`,
> the class of `M5l-068`).** The guard reads the stamp only in `evaluate`, on
> a candle, after the reconciler. No candle arrived in the window, so nothing
> was evaluated. When candles resumed, the reconciler ran first and refreshed
> the stamp before any read. **What survives:** the outage, its 300 s, and
> that no line reported it. What was lost is still the bot's knowledge of the
> position, not a refusal.

**Not a gate on live trading**, by the project owner's ruling at P65.

> **THE OWNER'S RULING, VERBATIM, M5l P76 (C27):** *"The market-data outage
> is not a gate on live trading, because venue-side protection remains in
> force through it."* Until P76 the tree recorded the P65 ruling above only
> in reported speech (`M5l-099`).

What the outage also cost, measured at P65 and recorded in
`docs/RUN_LEDGER.md` §23:
- The bot's disconnect warning came 229 s after the library's first error,
  because its consumer read nothing in between (`M5l-060`).
- A queue overflow discards every message queued behind the first error
  (`M5l-061`).
- Three BTCUSDT/1m bars and one ETHUSDT/5m bar were never received and never
  backfilled (`M5l-062`).
- The row-count SMA(50) behind the next death cross spanned the gap
  undetected (`M5l-063`).

*Arming condition:* **whoever next changes what triggers a reconciliation pass -- `ReconciliationDriver.__call__` in `execution/reconciliation_driver.py`, registered by `provider.on_candle` in `live_system` in `engine/modes.py` -- or the market-data reconnect path, `_run` in `exchange/websocket_client.py`.**

> **ANNOTATED AT M5l P91 (C44), P-3l IS BEING CLOSED IN THREE COMMITS: GAP
> DETECTION AND THE BUY GUARD LAND FIRST.** Under the P90 pins, measured and
> guarded rather than repaired. **C44:** `BufferedMarketDataProvider._append`
> records a gap when a bar's `open_time` is more than one timeframe after the
> last, logs `bars_gap_detected` once per gap (`symbol`, `timeframe`,
> `missing_bars`, `from`, `to`), and `bars_since_gap` counts the consecutive bars
> since. `TradingEngine._on_candle` suppresses a **BUY only** while fewer than
> `strategy.warmup_period` bars have followed the gap, logging
> `buy_refused_bars_gap`, and logs `bars_contiguous_again` once when the window
> clears. A CLOSE is never refused: the guard sits AFTER the signal exists and its
> condition names `SignalAction.BUY`. So the P-3l item's *"The row-count SMA(50)
> behind the next death cross spanned the gap undetected (M5l-063)"* is
> historical, true of the capture and no longer of the tree. **What survives:**
> the bars are still never fetched (backfill is deferred, pin 4), reconciliation
> still stops with the candles (a timer is deferred, pin 2), and the heartbeat
> and the transient-error handling are C45 and C46.
>
> **ARMING AUDIT AT C44.** P-2's and U7's *"whoever next edits
> `config/models.py`'s coherence block"* fire on a comment C44 adds inside
> `_check_dispatch_budget_fits_the_bar`, annotating C16's refusal text, and are
> REAFFIRMED: no term, budget or refusal in the block moved. The conditions
> naming the reconciliation trigger and `_run` are not fired by C44.
>
> **ANNOTATED AT M5l P91 (C45): THE HEARTBEAT, THE LAG MONITOR AND THE SLOW-CHAIN
> LINE ARE BUILT, AND *"no line reported it"* IS NO LONGER TRUE OF THE TREE.**
> `FeedWatchdog` (`data/watchdog.py`) is armed, started and stopped by the
> engine and fed by the provider's chain observer, which `live_system` wires.
> **Per pair:** `feed_silent` at `WARNING` after 1.5 timeframes with no accepted
> bar, `feed_silent_critical` at `CRITICAL` after 5, once per episode, and
> `feed_resumed` at `INFO` with the gap when a bar ends it. **Event-loop lag:**
> `event_loop_lagging` at `WARNING` when a one-second tick wakes more than 5 s
> late, with `event_loop_recovered`. **Slow chain:** `handler_chain_slow` at
> `WARNING` when one candle's subscribers take more than half the bar, with
> `handler_chain_recovered`. It reports and nothing else: no halt, no
> reconnect, no refusal. **Its purpose in `M5l-198`:** the lag and slow-chain
> lines are the measurement of the 229 s stall that the capture could not
> supply, so the next occurrence names what held the consumer. A loop blocked
> outright cannot run the watchdog and is reported when it resumes. **What
> survives:** reconciliation still stops with the candles; the line says so at
> `CRITICAL` and does not restart it.
>
> **ARMING AUDIT AT C45.** P-3l's *"…`provider.on_candle` in `live_system` in
> `engine/modes.py` -- or the market-data reconnect path, `_run` in
> `exchange/websocket_client.py`"* names `live_system`, which C45 edits to wire
> the observer and the watchdog; it is REAFFIRMED, because what triggers a
> reconciliation pass is unchanged (the driver is still registered by
> `provider.on_candle`) and `_run` is untouched until C46. The P-3k boot-
> reconciliation condition names `live_system` only as where the snapshots run
> and is not fired.
>
> **RESOLVED AT M5l P91 (C46), AS REPORTED, MEASURED AND GUARDED: P-3l IS
> CLOSED UNDER THE P91 RULINGS, and the arming condition above, *"…or the
> market-data reconnect path, `_run` in `exchange/websocket_client.py`"*, FIRED
> at C46 and is DISCHARGED.** `_run` now reads past the library's own transient
> error dicts -- `ConnectionClosedError`, `ConnectionClosedOK`,
> `IncompleteReadError`, `gaierror` and `BinanceWebsocketClosed`, the five
> python-binance 1.0.37 catches under *"reports errors and continue loop"* --
> logging each as `stream_transient_error` at `WARNING` and tearing nothing
> down, so the klines queued behind them survive (`M5l-061`, `M5l-199`). Anything
> else, including `BinanceWebsocketUnableToConnect`, a queue overflow, a
> cancelled loop and any type nobody listed, still rebuilds the socket; the
> whitelist runs that way deliberately, because a transient error treated as
> terminal costs one rebuild and the reverse leaves a dead feed. The socket
> manager is given `max_queue_size=1000` where the library defaults to 100
> (`binance/ws/streams.py`), so a stalled consumer loses closed bars ten times
> later. **What the item's lines now are:** the 229 s delay (`M5l-060`) is
> reported by the watchdog whenever it recurs; the lost bars (`M5l-062`) are
> detected and logged and guarded (C44); the spanned SMA (`M5l-063`) refuses a
> BUY; the silent stop of reconciliation is reported at `CRITICAL` and **accepted
> under P76**, not repaired. **What stays open:** the cause of the original stall,
> which is `M5l-198` and UNMEASURED until the lag and slow-chain lines catch an
> occurrence; and the two deferred items below.

#### P-3m. A call-cap deferral logs nothing (`M5l-075`)

When the per-pass call cap stops before a due position, that position is not
read and nothing says so. A pass that read one of two due positions logs
`positions=1 queries=2`, exactly like a pass with one position, so no capture
can count a deferral. MEASURED (code, and both captures). It matters more
since `M5l-081`: a healthy position can be deferred on consecutive bars once
three positions are open and one has absent legs, and the only trace of that
would be a staleness refusal.

> **ADDED AT M5l (P71, C22): TWO MORE SHAPES THAT LEAVE THE SAME SILENCE.**
>
> - **Starvation (`M5l-085`, `M5l-086`).** A healthy neighbour went unread
>   for 6 bars, its stamp age rising 120, 181, 242, 303, 364, 425 s. That
>   happened in two cases: when the other position's point queries failed
>   at `max_calls = 3`, and when `max_calls = 2` was below `L + 1`. The
>   second case is now refused at config load (`90355df`, P-3o). The first
>   is not.
> - **Churn (`M5l-088`, `M5l-089`).** A position opening on a freed slot is
>   unstamped, so it sorts first. With an unresolved list, it defers the
>   healthy position again. MEASURED: at `n = 3`, a healthy stamp reached
>   242 s after three consecutive deferrals.
>
> Neither shape logs a deferral. In the measured runs, the deferral left a
> trace only once the stamp passed the bound, as a `position_stale`
> refusal. The `committed_risk_unknown` refusals before that point name the
> untrusted position, not the deferral.

*Arming condition:* **whoever next edits the call cap in `reconcile_open_positions` in `execution/reconciliation.py`, or `_report` in `execution/reconciliation_driver.py`.**

> **PARTLY RESOLVED AT M5l P89 (C42): *"A call-cap deferral logs nothing"* IS NO
> LONGER TRUE, AND THE ARMING CONDITION ABOVE FIRED AND IS DISCHARGED FOR THE
> LOG.** At the break in `reconcile_open_positions`, every due position the
> cap leaves unread is logged at `INFO` as `reconciliation_deferred`, one line
> each, with `symbol`, `reason=call_cap`, `calls_used` and `max_calls`. So a
> pass that read one of two due positions no longer reads like a pass with one
> position, and a capture can count deferrals. Pinned by
> `test_a_call_cap_deferral_is_logged_with_the_calls_used`, three positions
> with the middle one diverged, whose third is the one logged.
>
> **WHAT STAYS OPEN, logged rather than fixed:** the **starvation** shape
> (`M5l-085`, `M5l-086`) and the **churn** shape (`M5l-088`, `M5l-089`) from
> the P71 addition above. Both now leave this line, and the deferral is no
> longer visible only as a `position_stale` refusal; neither is prevented. The
> first of the starvation cases, a neighbour's failing point queries at
> `max_calls = 3`, is not closed by the cap's decoupling at C41 either. **What
> survives:** the item, for those two shapes, and the arming condition for
> `_report`.

#### P-3n. Is the confirm-step question ruled? (`M5l-077`) -- FOR THE OWNER

U7 below calls the five-versus-four confirm-step question *"unruled"*.
`config.yaml`'s comment on `dispatch_deadline_s` says *"RULED at M5h: the
confirm step queries the TWO PROTECTIVE LEGS ONLY, so a full close is FOUR
calls"*. MEASURED: the two disagree. Which one stands decides whether
`_CLOSE_SEQUENCE_CALLS` can go, and that is U7's subject.

> **ADDED AT M5l P76 (C27): WHAT `docs/PHASE_HISTORY.md`'s M5h ENTRY SAYS,
> next to U7's *"the unruled five-versus-four confirm-step question"*.**
> Quoted verbatim; nothing is ruled here.
>
> - The M5h commit table, row 31: *"| 31 | `f6ec6d1` | The close is four
>   calls, and there is no per-call share |"*
> - The M5h prose: *"Q-C §4b's cancel → confirm → sell, built as specified:
>   one cancel collapses the list, the confirming query re-reads per leg
>   because it must see a leg that filled *during* the cancel, and the sell
>   is `MARKET` under a derivable close id so a timed-out sell is resolvable
>   by asking."*
>
> The build log says the close is four calls, and so does `config.yaml`'s
> comment. U7 calls the question unruled. The prose says "per leg" without
> saying which legs. **For the owner:** whether the M5h text is the ruling
> U7 lacks. P-3n merges into U7 (the P-3 order above).

*Arming condition:* **whoever next edits `_CLOSE_SEQUENCE_CALLS` in `config/models.py`, or rules on U7.**

#### P-3o. The call cap is the position limit (`M5l-086`, `M5l-087`)

The pass cap max_calls equals max_open_positions, so a configuration with
max_open_positions < L + 1 cannot complete a position with L unresolved legs
(M5l-086, M5l-087). C20b refuses such configurations at load; decoupling the
cap from the position limit, and counting it in the budget, is the real fix
and needs its own Phase 1. C20b therefore refuses max_open_positions = 1 in
every configuration; decoupling restores single-position operation.

> **ANNOTATED AT M5l (P71, C20b), for precision: "in every configuration"
> means every configuration with a protective leg enabled.** With both the
> stop-loss and the take-profit disabled, `L = 0` and a cap of 1 is
> accepted. Two tests rely on that. **What survives:** every configuration
> that protects its positions needs a cap of at least `L + 1`.

*Arming condition:* **whoever next changes how `ReconciliationBudget.from_config` in `execution/reconciliation_driver.py` sets `max_calls`.**

> **RESOLVED AT M5l P89 (C41): THE CALL CAP IS NO LONGER THE POSITION LIMIT,
> AND THE ARMING CONDITION ABOVE IS DISCHARGED.** *"The pass cap max_calls
> equals max_open_positions"* and *"C20b therefore refuses max_open_positions
> = 1 in every configuration"* are no longer true. By the owner's P76 sketch
> (a), `RiskConfig.reconcile_call_cap` is `max(max_open_positions, L + 1)`,
> `ReconciliationBudget.from_config` sets `max_calls` from it, the coherence
> validator's reconcile term counts it (`reconcile_call_cap x T_recon`), and
> C20b's refusal, `AppConfig._check_the_call_cap_can_complete_a_position`, is
> removed. **Rendered through `AppConfig`:** the committed shape is unchanged
> (`2 x 9.0 + 3 x 2.3 + 2 x 2.3 = 29.5 s`, ceiling `D = 9.25`), and two 1m
> pairs with `max_open_positions = 1` and a take-profit load with a cap of 3,
> `2D + 3 x 2.3 + 1 x 2.3`, so `D = 10.4` is exactly 30.0 s and 10.41 is
> refused. The settlement term is unchanged, `min(N_max, P_sim) x T_recon`,
> because it counts positions that can exit on one bar and not calls. **The
> staleness floor's `k <= n - 1` is unaffected (`M5l-084`, re-derived at P89).**
> The derivation used only that the pass reads oldest-stamp-first, stops when
> `len(results) + reserved >= max_calls`, and reserves the first unresolved
> position's `L` legs, so that with `max_calls >= L + 1` every pass completes
> and stamps at least one position ahead of a deferred one, and only `n - 1`
> can sit ahead of it. It never used `max_calls <= max_open_positions`: it was
> probed at `max_calls = 3` for `n` = 2, 3 and 4, with the cap BELOW `n`. The
> new cap is at least `L + 1` by construction and at least `max_open_positions`
> `>= n`, so the premise holds and a larger cap only widens each pass's read
> prefix. **What survives:** the arithmetic
> that completing an `L`-leg position costs `1 + L` calls, the livelock
> argument, and `n = min(max_open_positions, enabled pairs)`, since `n` counts
> positions and not calls. And the **starvation shape** (`M5l-085`: a
> neighbour's failing point queries) stays open, logged rather than fixed by
> P-3m.
>
> **ARMING AUDIT AT C41.** Fired and REAFFIRMED: P-2's *"whoever next edits
> `config/models.py`'s coherence block"* and U7's identical condition, both
> because C41 edits that block's reconcile term; P-2's design question (the
> default, the floor) is untouched, and U7's `_CLOSE_SEQUENCE_CALLS` is not
> deleted, the confirm-step question still being unruled. P-3i's
> *"`ReconciliationBudget`"* condition fires on `from_config` and the class
> docstring and is REAFFIRMED for C43. P-3m's *"the call cap in
> `reconcile_open_positions`"* condition is touched by a docstring annotation
> only and is REAFFIRMED for C42. P-2's annotation above, *"`90355df` (C20b)
> adds the precondition"*, and the commit list's *"`90355df` (C20b): the
> `L + 1` call-cap precondition"*, record what C20b did and stay as written;
> the precondition now holds by construction.

---

## OTHER NEW CARRIED ITEMS, AT M5k's CLOSE

### N1. A held-then-released trade leaves no record across a restart

F2's successor. A position is not persisted, so a restart releases a hold,
and a close deferred before a restart is released unbooked after it
(`M5k-065`). The trade is then in the ledger only if an operator entered it by
hand, and nothing on disk records that it was ever held or deferred.

> **ANNOTATED AT M5l P79 (C30): *"A position is not persisted"* IS NO LONGER
> TRUE OF THE FILE.** From C30 a held position keeps its record in
> `data/state.json` (the owner's Q5(b)). **What survives:** nothing reads the
> record until C32 and each boot's first save erases it, so a restart still
> releases the hold and a deferred close is still released unbooked; and the
> record carries no hold, so nothing on disk records that it was held.
> REAFFIRMED at C30, which edits `_persist_pending`.
>
> **ANNOTATED AT M5l P81 (C32a): "nothing reads the record until C32" IS NO
> LONGER TRUE, and "a restart still releases the hold" is true only of a
> hold with a pending close.** A position held by the reconciler has no
> close record: at boot its filled exit classifies `BookExit` and, until
> C32b, REFUSES the boot rather than releasing the hold (`M5l-130`). A hold
> or a deferred close beside a pending close record is left out by the
> owner's interim ruling, so that restart still releases it unbooked.
>
> **ANNOTATED AT M5l P82 (C32b-1): the reconciler-held case no longer
> refuses the boot.** Its filled exit re-holds at boot: the record is kept
> with no position and the symbol blocked (Q5(b)), so the hold now SURVIVES
> the restart rather than refusing it or being released.
>
> **ANNOTATED AT M5l P82 (C32b-3): "A hold or a deferred close beside a
> pending close record is left out by the owner's interim ruling, so that
> restart still releases it unbooked" IS NO LONGER TRUE.** Boot reads the
> close's sell beside the position's record. A filled sell is booked
> ledger-only, or held with its record kept (Q5(b)), and the close record is
> removed either way, so such a restart neither releases nor drops it unbooked.
> **What survives:** the item, and a close with no position record beside it,
> which is still released on its first candle.
>
> **ANNOTATED AT M5l P83 (C33): THE ITEM'S HEADLINE IS ANSWERED.** *"A
> held-then-released trade leaves no record across a restart"*: a held exit
> now keeps its record across a restart (Q5(b)) and is released only by an
> operator with `scripts/release_position.py`, whose line in `logs/release.log`
> is the record that it was. **What survives:** nothing on disk records WHY a
> position was held, since the record carries requested values only; the hold
> is re-derived from the venue's fills at each boot.

*Arming condition:* **whoever next edits `PendingCloseRecord` in `persistence/store.py` or `_persist_pending` in `engine/modes.py`.**

### N2. Whether Testnet takes fees in BNB -- UNMEASURED

Every commission in every capture is `0.00000000`, so the BNB setting has
never been observed to matter. It decides which asset an entry fee arrives in,
which is the question entry-fee netting must answer first.

*Arming condition:* **whoever next edits `calculate_position_size` in `risk/position_sizing.py` or `build_placement` in `execution/placement.py` to net an entry fee.**

### N3. How soon `myTrades` returns a fill -- UNMEASURED

The only `myTrades` captures were read long after their fills, so nothing
measures the delay between a fill and its appearance there. That delay
decides how often Site A defers a settlement it could have read a moment later.

*Arming condition:* **whoever next edits `_settle` or `_defer_settlement` in `execution/executor.py`.**

### N4. `_dec` launders a float past `Money` (`M5k-025`)

`_dec` is `Decimal(str(value))`, so a float routed through it reaches a
`Money` field as a `Decimal`, and `_reject_float` never fires on the wire path
of any mapper that uses it. The scope was ratified by the owner: declared, not
fixed. MEASURED.

*Arming condition:* **whoever next edits `_dec` or `_opt_dec` in `exchange/models.py`.**

### N5. Q-B's halt-flag condition may be stranded (`M5k-140`)

Its caller is the halt flag's first writer, and the owner ratified `CRITICAL`
without a halt flag (`M5k-006`), so that writer may never exist -- `CLAUDE.md`'s
failure mode 2. Whether it is stranded is decided by whoever writes a halt, or
rewrites the condition. REASONED.

*Arming condition:* **whoever first adds a halt field to `Portfolio` in `core/portfolio.py`, or whoever next edits the halt-flag condition in `docs/QB_ESCALATION.md`.**

### N6. Lifting the live-trading block

The owner's ruling above names its two preconditions:
- a non-zero fee capture empirically established on a live-quoted venue;
- base-asset quantity netting fully implemented in the entry sizing pipeline.

Neither exists. `CLAUDE.md`'s own live-block condition, on `Settings.__init__`
and `_cmd_run`, still governs the mode resolution; this item governs the work
the lift waits on.

**A third gate stands beside the two, added by the owner at P61:** the restart
gap, P-3k -- an open position that a restart leaves unowned. It carries its own
arming condition there, and the condition below does not watch it.

> **ANNOTATED AT M5l P87 (C38): THE THIRD GATE IS CLOSED, AND TWO STAND.** The
> owner ruled P-3k satisfied at P87 (quoted verbatim at P-3k above): *"P-3k no
> longer blocks live trading. The fee-capture and base-asset-netting gates
> remain, so live trading stays blocked."* **N6's two preconditions, listed
> above, are exactly what remains, and neither exists.** A protective
> stop-loss order type review, marked at P87 (`M5l-170`), is not a gate by the
> owner's ruling; it is marked for QC before live trading.

*Arming condition:* **whoever next edits `calculate_position_size` in `risk/position_sizing.py` or `build_placement` in `execution/placement.py`.**

---

## RESOLVED AT M5k — one index line each

Each item's full text is in git history and in `docs/PHASE_HISTORY.md`'s M5k
entry. An item resolved only in part is indexed here AND carried below with its
residue and its condition.

- **Priority 1 / A5, the DIVERGED exit-booking gap** — resolved in code at
  `3e444f0` (`M5k-004`–`M5k-009`): a diverged pass with no fill escalates at
  `CRITICAL` instead of continuing. The residue is carried as A5.
- **Priority 2, a gate-count self-verification helper** — resolved at
  `2109bee` (`M5k-011`, `M5k-013`–`M5k-020`): `scripts/check_gate_counts.py`.
- **Priority 4, the accounting architecture pass** — resolved for EXIT fees at
  `45ffe31`, `9f3deb1`, `f1c5af7` and `651d334` (`M5k-021`–`M5k-035`,
  `M5k-049`–`M5k-064`). The ENTRY half stays under `CLAUDE.md`'s live-trading
  block and is carried as A1.
- **A1, commission never reaching the ledger** — resolved for EXIT commission
  at `651d334` (`M5k-094`, annotated here at `222bdf4`). The entry half is
  carried as A1.
- **A4, `venue_time` on an `exit_booked` line** — resolved at `651d334`, after
  the rename at `f1c5af7`; the booking line's `filled_at` and
  `order_created_at` are pinned by test (`M5k-067`).
- **F1, the driver retrying a permanent fee refusal** — resolved at `d253cd5`
  by R2 with rulings A and B (`M5k-078`).
- **F2, a restart after a deferred settlement** — closed as MEASURED at
  `db73b63` (`M5k-065`): the restored close is released unbooked at `CRITICAL`,
  and the restart neither re-enters the retention nor books.
- **`M5i-104`, the named test's unguarded unpack** — resolved at `c5dd7d5`
  (`M5k-113`). The sweep is carried.
- **`M5i-109`, two stale sentences in a test docstring** — resolved at
  `c5dd7d5`, whose rewrite of the test removed the docstring; recorded in that
  commit's arming audit.

---

## CARRIED FROM M5k'S PRIORITIES

### 3. Regularising the arming conditions

Done at M5j's rotation for this file, and widened at M5k's by `CLAUDE.md`'s
rule g, under which the audit reads every document that carries a condition.
**Two conditions are left unparsed deliberately**, one in this file -- Q-C §3's
leg set -- and one in `docs/QB_ESCALATION.md` -- the halt flag's first writer.
Closing either needs a ruling rather than an edit. See the note under **Arming
conditions** below, which carries the measured registers.

---

## Arming conditions — the registers, with two deliberate exceptions

`scripts/check_arming_conditions.py` keeps a parsed and an unparsed register and
**exits non-zero while the unparsed register is non-empty**. Under `CLAUDE.md`'s
rule g it is run on every document that carries a condition. MEASURED at M5k's
rotation, on the tree this commit leaves:

| document | candidates | parsed | unparsed |
|---|---:|---:|---:|
| `docs/NEXT_MILESTONE.md` | 38 | 37 | 1 |
| `CLAUDE.md` | 2 | 2 | 0 |
| `docs/QB_ESCALATION.md` | 1 | 0 | 1 |
| `docs/QC_PROTECTIVE_ORDERS.md` | 0 | 0 | 0 |

At M5j's rotation the tool read 22 candidates here, 15 parsed and 7 unparsed,
every failure for the same reason: the bold span named no backticked symbol.

**Six were regularised by naming the site they actually guard**, leaving 22
candidates, **21 parsed and 1 unparsed**. Their targets were derived from the
tree rather than invented: the two persistence closures are `_persist_pending`
and `_persist_ledger` in `engine/modes.py`; the classifier branch is `_refine`
in `execution/reconciliation.py`; the executor's substitutes are
`paper/simulator.py` and `backtesting/engine.py`; the unobserved-surface table
is produced by `scripts/run_census.py`; and the two conditions reading *"whoever
next edits that test"* name tests the surrounding prose already identifies, so
the real node ids are used.

**ONE IS LEFT UNPARSED IN THIS FILE ON PURPOSE, AND ONE IN
`docs/QB_ESCALATION.md`, AND THAT IS THE CORRECT OUTCOME.** Corrected at M5k's
rotation: this heading read *"ONE IS LEFT UNPARSED"* while priority 3 above
read *"Two conditions are left unparsed deliberately"*, and the file
contradicted itself. Measured across every document the audit reads, both are
true of different scopes: one here, one in Q-B. The trailing-stop block guards
Q-C §3's leg set — a **contract document section**,
not a Python symbol. The honest target is `docs/QC_PROTECTIVE_ORDERS.md` §3,
and backticking that path *would* satisfy the parser; it is left as it stands by
ruling, because writing a path in to please a tool is writing for the tool.
Q-B's condition names *"the halt flag's first writer"*, a writer that does not
exist; its marker was normalised at M5k's rotation so the tool finds it, and it
is accepted unparsed by ruling for the same reason.

**So a non-zero exit is expected and is not a defect to regularise around.** The
checker is reporting that two conditions, one per document, guard something its
schema cannot express — which is the register doing its job. Widening the parser to accept a
caller-phrase with no symbol is the alternative, and it is the owner's call.

---

## THE MODE-3 RECORD — what M5k's rotation pass found

`CLAUDE.md`'s failure mode 3 is a condition that FIRES and nothing notices.
M5k's rotation read every condition against every M5k commit that edited its
named site. What it found is recorded here and not re-litigated:

- **A5 and `M5i-065` fired UNAUDITED at `3e444f0`.** That commit edited
  `_book_exits` -- row 4, the diverged escalation -- and its body carries no
  arming-condition audit. It is the commit that closed A5's code gap.
- **`M5i-065` fired UNAUDITED again at `f1c5af7`**, which edited the booking
  line inside `_book_exits`. Its audit named A4, A5 and A6 and not `M5i-065`.
- **`M5i-095` arguably fired at `3e444f0`**, whose
  `test_the_escalation_books_nothing_and_saves_nothing` asserts
  `portfolio.ledger is None` -- portfolio state -- to show that nothing was
  booked.

Every other firing in M5k was audited in the body of the commit that caused
it: U7 at `e511e6d`, A1 at `193a5b9`, and A4, A5, A6, F1, F2, `M5i-065`,
`M5i-095`, `M5i-104` and `M5i-109` at the commits their audits name.

**The instrument, and why it was not `git log -L`.** Which commits edited a
named function was measured by comparing that function's exact source
segment, extracted with `ast`, at every M5k commit and at its parent. `git log
-L` was tried first and missed an edit: its regex-range form did not report
`f1c5af7`'s change to `_book_exits`, and with `--no-patch` it printed nothing
at all. An instrument that under-reports firings produces exactly the silence
mode 3 describes.

---

## UNRULED — reserved to the project owner

### U9. OPEN OWNER RULING: how the fee-capture gate is met -- added at M5l (P68)

How the gate *"a non-zero fee capture empirically established on a
live-quoted venue"* is met, given Testnet commission is zero on every fill
(`M5l-054`):
- (i) a read-only mainnet key fetching existing trades;
- (ii) one minimum-size mainnet order, under its own ruling;
- (iii) rewording the gate.

It is N6's first precondition. MEASURED: every commission in every capture
this tree holds is `0.00000000`, including the six fills of M5l's evidence
run, so no Testnet run can meet it as worded.

*Arming condition:* **whoever next edits `refuse_live_trading` in `config/settings.py`, or rules on N6's first precondition.**

### U11. DEFERRED: reconciliation on a timer, independent of candles -- ruled at M5l P91 (pin 2)

P-3l's stopped reconciliation is reported and not repaired. A timer that ran the
reconciler at the dedup interval, whether or not a candle arrived, would repair
it, and it is **deferred by the owner's P91 ruling.** It would amend locked text,
quoted here so a later author sees what the work costs:
- *"Reconciliation runs, on any pair's candle, over every open position not held
  under ruling A."* (the P74 re-ruling, `CLAUDE.md`, *Fills are observed by
  polling*);
- *"the driver still has to be a candle subscriber, because it still reconciles
  every UNHELD position on any pair's candle while `on_signal` skips quiet
  bars."* (the ruling A annotation under *Handler isolation is THREE layers*);
- and it runs into *"A bounded queue with a single consumer was rejected: it
  makes `Portfolio` writable from a task that is not the one reading it, and the
  first bug that buys is a **duplicate entry**"* (*Execution*, *Dispatch stays
  inline*), because a pass writes `Position` state and books exits. It would
  need a serialisation rule against `_notify`.
It would also fail visibly and recover nothing if REST is down with the socket
(`M5l-201`).

*Arming condition:* **whoever next edits `ReconciliationDriver.__call__` in `execution/reconciliation_driver.py` to be called from anywhere but `provider.on_candle`, or lifts the P76 acceptance.**

### U12. DEFERRED: REST backfill after a gap -- ruled at M5l P91 (pin 4)

C44 detects a gap and refuses a BUY across it; the missing bars are never
fetched. A backfill would close the gap rather than guard it, and it is
**deferred by the owner's P91 ruling.** Facts for whoever builds it: it must run
before the first post-gap bar is appended, because `_append` drops
`open_time < last`; `ExchangeClient.get_klines` takes `limit` and no start time,
so a backfill reads the latest N bars and merges; and it makes a REST call on the
candle path. Locked text it touches: *"The invariant that survives is **the
candle pipeline must never be blocked by latency we do not bound ourselves** — a
budget, not an abstinence"* (*Execution*), so it needs its own bound and a place
in the coherence budget; and *"add every bar that never arrived because the feed
dropped and the buffer does not backfill"* (*There is no static staleness
guarantee*), which it would make false.

*Arming condition:* **whoever next edits `_record_gap_if_any` in `data/market_data.py` to fetch bars, or adds a start time to `ExchangeClient.get_klines` in `core/interfaces.py`.**

### U10. OWNER ITEM: QC review of the protective order type before live trading -- added at M5l (P88)

QC review of the protective order type before live trading: `STOP_LOSS`
guarantees the exit, not the price; measured 4.2% beyond the stop on Testnet
(P87's finding, `M5l-170`, `docs/RUN_LEDGER.md` section 25): a stop at
83214.72 filled at 79800.00 and 79749.94. Q-C section 3 fixed the leg types
(`STOP_LOSS`, `TAKE_PROFIT`, a `LIMIT`+`FOK` working leg); whether a
`STOP_LOSS_LIMIT` or another type bounds the price, and what it costs in
exits that do not fill, is the review's question and is not decided here. Not a
gate by the owner's P87 ruling: marked for review before live trading.

*Arming condition:* **whoever next edits `build_placement` in `execution/placement.py`, which fixes the protective leg types, or rules on N6's preconditions.**

### U8. The harness: refuse, or report? — `M5i-096`

`scripts/mutation_survey.py` prints `target is tracked and clean` or `target has
uncommitted edits` and **proceeds either way**. `describe_vcs_state` computes the
fact; nothing acts on it.

**A dirty target is the NORMAL case and that is why it is advisory.** Surveying
the committed version would measure the *previous* commit, which is not the
thing under review. A harness that refused here would have refused every survey
M5i actually ran.

**What makes it a question rather than a settled no:** `M5i-084`'s rule is
satisfied by the out-of-tree snapshot, which exists whatever git says, so
refusal would buy nothing the snapshot does not already provide. The argument
for refusing is different — that a survey against uncommitted work has no
recoverable baseline in the repository if the snapshot is also lost.

*Arming condition:* **whoever next changes `describe_vcs_state` or the block in
`main` that prints its result.** Refusal is one `if` at that call site and the
fact is already computed.

### U0. `_persist_ledger`'s `pending=persisted.pending` — carried, untouched

Unchanged from M5h. M5j touched no persistence code at all, so this condition
did not fire.

**FIRED AT M5l P79 (C30) AND REAFFIRMED.** C30 adds `positions` to what both
closures write, read live from `portfolio.open_positions`. It does not touch
the pending slice: `_persist_ledger` still writes `pending=persisted.pending`.

**FIRED AGAIN AT M5l P81 (C32a) AND REAFFIRMED.** Neither closure is
edited, but what `_persist_ledger` writes changes: `persisted` is now seeded
from the boot's own save when there was one, so after a boot that settled
restored placements it does not write them back (`M5l-128`). The carry itself,
`pending=persisted.pending`, is unchanged.

*Arming condition:* **whoever next changes what `_persist_pending` or
`_persist_ledger` writes in `engine/modes.py`.** A docstring correction is not
that.

### U1. `NOT_PLACED`: re-place, or drop? — `M5f-061`, `M5f-064`

Carried, unfired.

*Arming condition:* **whoever writes the first live-run change to
`resolve_placement`'s verdict handling.**

### U2. The venue-refusal half of e3-narrow — `M5f-083`

Carried, unfired. M5j edited no `except` chain.

*Arming condition:* **whoever next edits `dispatch`'s except chain** — not
`_sell_and_book`'s, which is a different chain the item excludes in its own
words.

### U3. Whether to consume `orderReports` — `M5f-038`

Carried, unfired.

*Arming condition:* **the placement site in `OrderExecutor`.**

### U4. The per-call share — `M5f-009`

Carried. **Its condition was repaired at M5k's rotation, because it was
spent.** It read *"whoever first sets `timeout_s`/`attempts` from config"*,
and that FIRST had already happened before M5k: the fee commit's audit
recorded it as `ReconciliationBudget.from_config`. A first that has happened
can never fire again, so the item could only ever read as waiting. The item is
about the DISPATCH per-call share, so the condition now names the one function
that derives it.

*Arming condition:* **whoever next edits `DispatchBudget.bounds_for_next_call` in `execution/dispatch_budget.py`.**

### U5. `BinanceRequestException`'s representation — `M5f-072`, `M5h-360`

Carried, unfired.

### U6. Whether `OrderExecutor` implements the `OrderExecutor` port

Carried, unfired.

*Arming condition:* **whoever writes `paper/simulator.py` or
`backtesting/engine.py`** — the two substitutes for the executor, neither of
which exists beyond a docstring stub.

### U7. Deleting `_CLOSE_SEQUENCE_CALLS` — `M5f-010`, `M5f-018`

Carried. It FIRED at M5k's `e511e6d`, which edited the coherence block to count
settlement, and was REAFFIRMED there: `_CLOSE_SEQUENCE_CALLS` is not deleted,
because deleting it depends on the unruled five-versus-four confirm-step
question its own comment names.

*Arming condition:* **whoever next edits `config/models.py`'s coherence block.**

---

## CARRIED FROM M5j

### A1. ENTRY commission never reaches the ledger, and `to_order` discards the fee report

**The EXIT half is resolved and indexed above**: since `651d334` every booking
site books net of the fee `get_my_trades` settles. **What is carried is the
residue.** ENTRY commission reaches the ledger at no site, by the project
owner's ruling R-a, so the ledger is net of exit fees and gross of entry fees;
and `to_order` in `exchange/models.py` still does not read the venue's `fills`
report, so any `fills` array a response carries is discarded at the mapper.
Netting the entry fee out of base quantity is the subject of
`CLAUDE.md`'s live-trading block, which it waits on. Until M5k's rotation the
condition below watched `to_order` alone, and `193a5b9`, the first commit to
edit it, REAFFIRMED it; it now watches the entry-sizing sites.

*Arming condition:* **whoever next edits `calculate_position_size` in `risk/position_sizing.py` or `build_placement` in `execution/placement.py`** —
the entry-sizing and placement sites where an entry fee would first be netted.

The condition was re-pointed at M5k's rotation. It read *"whoever next edits
`to_order` in `exchange/models.py` — the single site where the venue's
commission is discarded, and the first site any fee must cross"*. Exit fees no
longer cross `to_order`: they cross `get_my_trades`, and `settle_exit` sums
them. The residue this item carries is the entry half, which waits on sizing
and placement rather than on the mapper.

### A2. A manual action and a venue-triggered fill are indistinguishable

A leg `CANCELED` with `filled_quantity == 0` fails the fill branch, fails the
is-open branch, and falls to `ProtectionState.DIVERGED` with `ExitFill` `None`.
The two facts *a protective leg was cancelled by someone else* and *a protective
leg diverged* present identically, because the only fields the classifier reads
are status and executed quantity.

*Arming condition:* **whoever next edits `_refine` in
`execution/reconciliation.py`**, the per-leg branch that reads a leg's terminal
status.

The condition's second disjunct, *"or whoever adds the first non-bot writer to
a live account"*, was removed at M5k's rotation: it named an event, not a
caller, and the event had already occurred, on 2026-09-17, when M5j recorded
an order list cancelled and its base sold by orders this bot did not place.

### A3. Two build-log headlines carry a claim their own annotation corrects

**Reserved to the project owner. No edit is proposed.** The M5h and M5i entries
in `docs/PHASE_HISTORY.md` each open on a claim the same entry annotates as
false much further down, so a reader of either intro alone gets the false
version. **A second annotation is not the remedy** — `CLAUDE.md` states that a
duplicate annotation is permanent — and the plausible alternatives each cost
something a build log protects.

*Arming condition:* **whoever next appends a milestone entry to
`docs/PHASE_HISTORY.md`** — the rotation's step 1 author, who is the first
caller that must decide whether a new entry's headline may state a claim the
entry will later annotate.

### A5. Position-level `DIVERGED` has never been observed in production — the residue of `M5j-011`

**The code gap is closed and indexed above**: since `3e444f0` a pass whose
position-level verdict is `DIVERGED` and whose legs reported no fill escalates
at `CRITICAL`, `exit_unbookable`, instead of continuing. **What is carried is
the evidence gap.** In `trading_bot.m5k-close-20260925T182818Z.log`, SHA-256
`3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`,
`diverged=1` occurs 28 times, all between `2026-08-27 04:07:02` and `04:38:02`
and so before the identifier-space fix `3970968`, and `exit_unbookable` occurs
zero times: the escalation has never run. `M5k-005` measured why the hazard has
not fired either: every line on which a requested leg did not rest also carried
a sibling fill clause, so booking took the fill branch. **A sibling is not a
mechanism.**

*Arming condition:* **whoever next edits `_book_exits` in
`execution/reconciliation_driver.py` or `_refine` in
`execution/reconciliation.py`** — the two callers that would have to agree on
what an absent `ExitFill` means.

### A6. Two adjacent lines read as a booking overriding a refusal — NOT a control defect

A warning and a booking landed one second apart on 2026-09-18. Derived from the
code they are **two calls, not one decision path**: `ReconciliationDriver.__call__`
calls `_report` and then, separately, `_book_exits`, with no value passing
between them. The warning refuses to *interpret the protection state*;
`classify_bookability` reads four facts in the order `A > Q > P > C` and **none
is a fill price**. **The remedy is wording, not control flow.**

*Arming condition:* **whoever next edits `_report`'s warning text in `execution/reconciliation_driver.py`, or the booking line: `_log_booked` in that file or `execution/booking_line.py`.**

> **ANNOTATED BY 3b-2a: `classify_bookability` now reads `A > P > C > Q`**, by
> the project owner's Decision 1; Q still refuses until 3b-2b. This item's
> point is unchanged -- none of the four facts is a fill price -- and the
> condition above is REAFFIRMED: `_report`'s warning text and `_book_exits`'s
> booking line are untouched.

> **THE CONDITION WAS RE-POINTED AT M5k's ROTATION, BECAUSE ITS SITE MOVED.** It
> read *"whoever next edits `_report`'s warning text or `_book_exits`'s booking
> line"*. The booking line left `_book_exits` at `651d334` for `_log_booked`,
> and from `a534b31` its fields come from `execution/booking_line.py`
> (`settlement_fields`, then `quote_total_fields`). A condition naming the old
> site could no longer fire on an edit to the line it exists for. The item's
> point is unchanged.

---

## CARRIED FROM M5i

### `M5i-065`. The orphan guard raises silently

`reconciliation_driver`'s orphan guard raises and nothing reports it. Pinned to
the project owner at M5i, and unchanged in logic since: re-indented at
`651d334`, when `_book_exits`'s loop moved under a `try`. MEASURED at M5k's
rotation: the guard's lines differ in `git diff 651d334^ 651d334 --
src/trading_bot/execution/reconciliation_driver.py` and in no line under `git
diff -w` over the same range and path. This read *"untouched since"* until
then.

*Arming condition:* **whoever next edits the orphan guard or its caller in
`_book_exits`.**

> **FIRED AT M5l P94 (C50) AND REAFFIRMED: THE GUARD'S TEXT CHANGED, ITS LOGIC
> DID NOT.** The `ValueError`'s message said *"booking it would silently no-op"*,
> true while `close_position` returned `Decimal(0)` for a symbol it did not hold
> and false once it raises `PositionNotHeldError`; it now says *"booking it
> would raise PositionNotHeldError or book a different position than the one
> assessed"*, the second clause being the case the guard's identity check also
> covers. The docstring's *"would return `Decimal(0)` and look like a clean
> no-op"* is corrected the same way. The item's *"unchanged in logic since"*
> still holds: the condition, the raise and its type are as they were
> (`M5l-234`).

### `M5i-095`. Two tests reach the mutated point and assert only portfolio state

A survey predicted 9 kills and observed 6. The three that did not fire assert
`ledger is None`, `free_quote` and a record count — **identical whether booking
never ran or ran and failed**, because the write raises before it commits.

*Arming condition:* **whoever next writes a test asserting over `Portfolio`
state to distinguish two booking outcomes.** The state cannot separate them;
only the label can.

### `M5i-104`. Unguarded unpacks turn kills into crashes — the sweep, now 18 sites

**The named test is resolved and indexed above.** A single-element tuple
unpack of log records with no prior length assertion fails at `ValueError`, a
crash, where a mutation removing the record should fail an assertion; `CLAUDE.md`'s
rule i now prescribes the remedy. **The sweep is carried, and it has grown from
the 12 sites M5i counted to 18.** MEASURED at `ae8c914`, with the instrument
stated: lines matching `^\s*\(\s*\w+\s*,\s*\)\s*=` under `tests/` whose
right-hand side reads log records (`_records(` or `caplog`), with no `assert
len(` in the three lines before -- 16 in `tests/unit/test_executor.py` and 2 in
`tests/unit/test_reconciliation_driver.py`. How M5i counted its 12 is not
recorded, so the two figures are not the same instrument.

*Arming condition:* **whoever next writes or edits a single-element unpack of `_records` in `tests/unit/test_executor.py`, or of `caplog.records` in `tests/unit/test_reconciliation_driver.py`.**

The condition was re-pointed at M5k's rotation. It read *"whoever next edits
`test_a_partial_fill_with_no_cost_basis_still_goes_naked`, or runs a survey
whose predicted killers include it"*, which names a test already resolved
while the item carries a sweep of 18 others. The two helpers are where those
sites read: 16 unpack `_records(...)` in `test_executor.py`, and 2 unpack a
comprehension over `caplog.records` in `test_reconciliation_driver.py`, which
has no `_records` helper.

### `M5i-126`. A substring assertion pins wherever its anchor occurs

`test_the_refusal_names_the_cause_the_remedy_and_the_opt_out` asserts three
substrings against a whole refusal message, and **all three are satisfied by the
opening paragraph alone**. A mutation replacing the entire remedy block killed
nothing.

*Arming condition:* **whoever next edits `_UNREAD_OUTPUT` or that test.**

### The `_go_naked` family's fourth candidate

`_go_naked`'s message says the position is *"UNPROTECTED and still open"*. That
is false at the abandoned-after-cancel caller under `ALREADY_CLOSED`, where the
venue closed the position for us. Three members of this family have already been
split off for exactly this reason (`_go_naked_retaining`, `_sold_unbooked`,
`_sold_unpriced`); this would be the fourth.

> **ANNOTATED BY 3b-2: `_sold_unpriced` IS REMOVED, by the project owner's
> Decision 2** -- *"Deprecate and remove `_sold_unpriced`."* The family has two
> split-off members, not three, and a fourth would be the third. Its branch's
> inputs now go elsewhere: a partial fill to `_go_naked`, whose "still open" is
> TRUE there; a cost-basis-less one to `_sold_unbooked`; an unpriced whole fill
> to the fetch, then booking, a hold or the deferral. The false sentence this
> item names is untouched.

**THE FALSE SENTENCE HAS NOT BEEN EMITTED — MEASURED.** Three instruments agree
at zero: the rendered text `UNPROTECTED`, the structured field
`event=close_naked`, and `event=close_abandoned`, the branch that reaches it
under `ALREADY_CLOSED`.

**That is a statement about the past, not a clearance.** The branch remains
unexercised and the message remains wrong at that caller. A path that has not
run is not a path shown to be correct.

*Arming condition:* **whoever next edits the abandoned-after-cancel branch in
`_execute_close`**, which is the only caller that can reach it.

---

## DECLARED TEST WEAKNESSES — known, and none is a defect

### W1. Two mutations, one failure set — `M5h-356`, `M5h-370`

Standing. `M5i-095` is a further instance.

### W2. A guard conditional on a neighbouring number — `M5h-357`

Standing.

### W3. A test that pins the numbers, not the behaviour — `M5h-354`

Standing.

### W4. An end-state assertion cannot see *when* — `M5h-366`

Standing.

### W6. Format strings in `executor.py` — `M5i-015`

**The number moved and the weakness did not.** `getMessage()` assertions in
`test_executor.py` went from **0** before M5i commit 1 to **7**. The `_log.*`
call sites that serve one outcome each remain unpinned by construction.
Re-measured at M5k's rotation, at `ae8c914`: `grep -c 'getMessage()'` over
`tests/unit/test_executor.py` counts **6** lines. The instrument behind the
earlier 7 is not recorded, so the difference is not established as a change.

**Why that is not reassurance:** a message is safe while its call site serves
ONE outcome, and nothing enforces that property.

---

## UNMEASURED — venue facts nothing in the tree can supply

**Provenance: re-derived at M5k's rotation from the frozen capture
`trading_bot.m5k-close-20260925T182818Z.log`, whose SHA-256 is
`3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`** —
5,074,996 bytes, 26,126 lines, of which every earlier capture in the evidence
directory is a byte-exact prefix. The digest is named here because these
figures move whenever the bot runs. X1, X2a and X3 below are records of M5j's
closures and keep M5j's figures.

### X1. A take-profit HAS filled — OBSERVED, and STRUCK at `3ea87d8`

**Closed by M5j.** Observed 2026-09-18: **1** clause naming a filled `TP` leg
against **162** naming a filled `SL` leg, the `SL` figure re-measured and
unmoved. BTCUSDT, `order_list_id=171948`, booked at `15:21:02Z` for
`realised=63.0300952000` **GROSS** — `fee` was `Decimal(0)`, per A1. Detection
took **119 seconds**, from the last pass reporting `active` to the pass that
found the fill.

### X2a. `ALREADY_CLOSED` — OBSERVED, and STRUCK at `0992fa3`

**Closed by M5j.** `decision=already_closed`, `2026-09-15T23:38:02Z`,
`pid=26952`, BTCUSDT. It read as unobserved for two milestones because the
search matched the enum's member name where the log carries its `.value`.

### X2b. `HALT` has never occurred — zero across 163 close plans

**CARRIED, and the sole remaining unobserved venue fact.** Re-measured against
the capture named above: `decision=halt` is **zero** (`grep -c`), and the
denominator is `event=close_planned` **163** (`scripts/run_census.py`),
reconciling as `decision=sell` 162 plus `decision=already_closed` 1. **The
denominator moved from 75 at M5j's close to 163 at M5k's**, which is why it is
quoted with its capture rather than bare.

### X3. `resolve_placement` has never run — STRUCK at `0992fa3`

**Closed by M5j.** Falsified by the event pair `placement_ambiguous` at
`2026-08-27 04:06:02` followed by `placement_resolved outcome=placed_live` at
`04:07:02`. Order list `255471` is named inside the resolution's reason and is
an **artefact** of the falsification rather than its instrument.

### The unobserved surface is far larger than these items

X2b is the one remaining unobserved **venue fact**. It is **not** the remaining
unobserved branch.

| Figure | Value | Instrument |
|---|---|---|
| order lists placed | **185** | `event=order_placed`, `scripts/run_census.py` |
| complete exits | **165** (154 `close_booked` + 11 `exit_booked`) | `scripts/run_census.py` on each |
| close plans | **163** | `event=close_planned`, `scripts/run_census.py` |
| `decision=halt` | **0** | `grep -c 'decision=halt'` |
| clauses naming a filled leg `TP` | **3** | both classifier forms: `leg TP reports FILLED with`, and `leg TP reports <status> with <qty> executed` at a non-zero quantity |
| clauses naming a filled leg `SL` | **164** (146 + 18) | the same two forms for `SL` |
| log events DEFINED in `src/` | **40** (38 `_EVENT_*`, 2 public `EVENT_*`) | module-level string constants, by `ast`; `_WS_EVENT_*` excluded |
| of those, absent from the capture | **23** | `event=<value>` absent |
| of those, added at M5k | **6** | the six below, every one absent |
| `RefusalStage` members defined | **14** | the enum body |
| of those, unobserved | **8** | per-member `stage=<value>` absent |

**The instrument was re-validated before it was trusted.** Run on M5j's capture,
SHA-256 `bfc8ffddc494f288e710df00918507c7027bcfe538096def4d32172ed2af8d3d`, the
same script returns M5j's own figures: `TP` 1, `SL` 162 (144 + 18), and 9
unobserved `RefusalStage` members. The "both classifier forms" in M5j's rows are
therefore `reports FILLED with` and a non-`FILLED` status reported with a
non-zero executed quantity -- the 18 are order 300642's `EXPIRED` leg.

**What moved since M5j's close, and why.** The defined-events row rose from 34
to 39: M5k added `exit_settlement_held`, `exit_quote_totals_disagree`,
`close_settlement_deferred`, `exit_settlement_deferred`, `exit_unbookable` and
`venue_quote_total_unavailable`, and removed `close_sold_unpriced`. Two of the
six are public `EVENT_*` constants in `execution/booking_line.py`, which M5j's
`_EVENT_*` instrument would not have seen (`M5k-127`); the instrument is widened
here. `engine_stopped`, absent at M5j's
close because its process predated the marker, is now observed 8 times, so the
row that subtracted it is gone. `POSITION_STALE` left the unobserved stages
(`M5k-124`).

**What moved at M5l P-1, corrected in place because both rows count the
tree.** `boot_provenance`, `_EVENT_BOOT_PROVENANCE` in `main.py` from
`f8898de`, is the one event added, taking the defined row from 39 to 40
(re-counted by grep for module-level `_EVENT_*` and `EVENT_*` assignments: 38
and 2). It is absent from the capture above, which predates it, so the absent
row moves from 22 to 23 by the same instrument and the observed remainder is
unchanged at 17. No capture was re-read; every other row is the capture's and
is untouched.

**The websocket constants are excluded deliberately.** `_WS_EVENT_TYPE`,
`_WS_EVENT_KLINE` and `_WS_EVENT_ERROR` in `exchange/websocket_client.py` match
a pattern looking for `_EVENT_` but are wire-protocol keys of Binance's stream
payload, not log events.

*Arming condition:* **whoever next runs `scripts/run_census.py` against a newer
capture**, which is the tool that produces every figure in this table.

> **FIRED AT M5l (P64), AND REAFFIRMED.** The tool was run against the capture
> of pid 21520's log, SHA-256
> `c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f`. That
> is another log, from the deployment clone, and not an extension of the
> capture this table measures, so no row here is re-derived. Every row stays
> scoped to its digest. That capture's own answers are in `docs/RUN_LEDGER.md`
> §23: `boot_provenance` observed, the other 22 absent events and all 8
> stages not, and 3 close plans, all `decision=sell`. The condition stands for
> the next capture that extends this one.

---

## THE GATE BASELINE

Measured at M5k's rotation, at `ae8c914`, on this credentialed machine:

```
ruff check src tests scripts           All checks passed!
ruff format --check src tests scripts  129 files already formatted
mypy                                   Success: no issues found in 79 source files
pytest                                 1822 passed, 1 skipped
```

**`1822 passed, 1 skipped` is MEASURED.** `1819 passed, 4 skipped` is **DERIVED**
— that run minus the three `skipif(not HAS_CREDENTIALS)` integration tests,
which move from the passed column to the skipped one. It has not been observed
on this machine and must not be quoted as though it had.

The lone skip in the credentialed run is **not** an integration test:
`tests/unit/test_logger.py` skips one case on Windows because `time.tzset` is
POSIX-only.

---

## BLOCKED — the trailing-stop milestone

Unchanged from M5h.

*Arming condition:* **whoever amends Q-C §3's leg set.**

---

## Standing authorities for commits -- added at M5l P78b (C29)

**The standing docstring authority, ruled by the project owner at M5l P78b,
verbatim:**

> "STANDING DOCSTRING AUTHORITY, owner's ruling at M5l P78b, for this and every
> later commit:
> - A commit may correct or annotate docstring and comment text that it makes
>   false in any src/ file. It may not change code.
> - Verify it per such file: ast.dump of the module with every docstring removed
>   is identical before and after, and every changed line outside a docstring is
>   a comment line.
> - Report each verification.
> - Record the ruling verbatim in NEXT_MILESTONE beside the annotation
>   authority, in this commit."

**The annotation authority it was to sit beside is recorded nowhere in the
tree (`M5l-116`).** MEASURED at P78b: no document, and no commit message, has
ever contained the phrase. It has lived only in the owner's prompts, which is
the shape this project has recorded several times, of a rule held outside the
repository. As the prompts state it (P70 and P71, reported here, not quoted),
it covers `README.md`, `docs/NEXT_MILESTONE.md`, `docs/M5_NUMBERS.md`,
`docs/RUN_LEDGER.md`, and `CLAUDE.md` except its locked-decision text, with
per-prompt extensions for named `src/` docstrings and `config.yaml` comment
lines. The standing docstring authority above widens it for `src/` docstrings
and comments; it does not touch the documents' half.

**The annotation authority, recorded by the project owner at M5l P79 (C30),
verbatim:**

> "ANNOTATION AUTHORITY (owner's standing ruling, stated in prompts from M5l
> P68, recorded at P79): every commit annotates, in place and with no
> deletions, any text it makes false in README.md, docs/NEXT_MILESTONE.md,
> docs/M5_NUMBERS.md, docs/RUN_LEDGER.md, and CLAUDE.md except its
> locked-decision text; it greps for such text before committing and lists
> each annotation. PRE-EXISTING FALSE TEXT (owner's standing ruling, P68): text
> a commit did not make false is reported and declared, and does not halt."

> **ANNOTATED AT M5l P79 (C30): *"The annotation authority it was to sit beside
> is recorded nowhere in the tree"* IS NO LONGER TRUE.** The ruling is quoted
> immediately above. One detail of the reported paragraph differs from it: the
> owner dates the ruling to P68, where the paragraph cited it from *"P70 and
> P71"*. **What survives:**
> `M5l-116` as a record of what P78b measured, and the last sentence -- the
> standing docstring authority widens this one for `src/` docstrings and
> comments and does not touch the documents' half.

**WIDENED BY THE PROJECT OWNER AT M5l P81 (amendment 3), standing:**
`docs/QB_ESCALATION.md` and `docs/QC_PROTECTIVE_ORDERS.md` join the
annotation authority's file list, for this and every later commit. First used
at C32a, which annotates QB site 2 and its summary row and QC §5b
(`M5l-131`). `CLAUDE.md`'s locked-decision text stays excluded; C32a's one
annotation there, on pre-existing base holdings, was authorised for that
sentence alone, because the owner accepted P77 S6's text for it at P78.

**The ruled-overturn authority, ruled by the project owner at M5l P81,
verbatim:**

> "An existing assertion may change only when it encodes behaviour that a
> ruling named in the prompt explicitly overturns. The report lists each such
> change with the old assertion quoted, the new one, and the ruling; the test
> keeps its subject; and the mutation survey still kills through it. Any other
> broken assertion halts, as before."

First used at C32a, where the owner named Q3(a) as overturning the
first-candle resolution of restored placements, and five tests in
`tests/unit/test_modes.py` changed under it (`M5l-127`).

**The S6 standing rule, ruled by the project owner at M5l P82, verbatim:**

> "Any CLAUDE.md locked-decision sentence listed in P77 S6, accepted at P78 as
> adjusted for Q5(b), may be annotated with its accepted text in the commit
> that makes it false. No other locked text is authorised."

First used at C32b-1, on the R2 hold bullet's quoted ruling (`M5l-132`).

**THIS ROW OF P77 S6 IS SUPERSEDED BY THE OWNER AT P82.** The five-bar
retention bullet's S6 text, *"After a restart the `Position` is restored, so
Site B resolves a restored close and books it if its settlement reads. The
count still resets (R2)."*, does not describe the final design: Site B does
not book a restored close, because boot books or holds a close whose sell
filled and removes its record. The owner's amendment 2 substituted, and C32b-3
annotated `CLAUDE.md` with, this text: *"After a restart the boot reads the
close's sell beside the position's record. A filled sell is booked ledger-only
at boot, or held (Q5(b)), and the close record is removed, so no restored
close enters the count. The count is still in memory only and resets at a
restart. A close with no position record beside it is still released on its
first candle."* The other S6 rows are unchanged.

**A PROMPT'S FILE LIST DOES NOT NARROW THE STANDING AUTHORITY, ruled by the
project owner at M5l P88 and recorded in C39, verbatim:**

> "A prompt's list of files to write never narrows the standing authority."

It was needed at P87, whose prompt named three files to write while the
annotation authority covers README.md as well: the README text P87's ruling
made false was reported (`M5l-175`) rather than annotated, and C39 annotates
it.

## The rotation's own procedure — read `CLAUDE.md`, not this

The five steps live in `CLAUDE.md`'s **Git workflow** section and that file is
the authority. Recorded here only as pointers:

- **Step 4 — re-read the contracts under `docs/`** for prose the milestone
  superseded. It is the step most easily skipped, because the milestone that
  invalidates a paragraph is always editing a different file. **At M5j's
  rotation it found a sentence in `docs/QB_ESCALATION.md` that had been false
  since M5f** — three rotations had run this step over that file and none caught
  it, while the same claim in `docs/QC_PROTECTIVE_ORDERS.md` was annotated at
  M5h.
- **Step 5 — verify the tag RESOLVES**, never merely that it exists. At M5j's
  rotation `milestone/M5j` was created pointing one commit short of the closing
  commit, and `git tag -l` reported success throughout.
- **An arming condition names its CALLER, not an event** — and it is now audited
  at COMMIT time, not only here. `M5h-352` is why.
- **The findings count is read, never written:**
  `.venv\Scripts\python.exe scripts/check_findings.py <range> <namespace>`, over
  the milestone's tagged range once the tag exists. It prints the declared,
  distinct and maximum ids, and every duplicate, gap, id cited but never
  declared, and commit with no block.
- **Step 2's count sites:** `scripts/check_gate_counts.py`, run TWICE, outgoing
  figures first -- `CLAUDE.md`'s rule l, and `M5k-125` is why.

> **DO NOT MOVE A RULE INTO THIS FILE.** Step 3 rewrites it every rotation. At
> M5i's rotation `CLAUDE.md` was found asserting that the grep-the-digits rule
> and its inverse *"both live in `docs/NEXT_MILESTONE.md`'s process section"* —
> and they did not, because a previous rotation had rewritten the file out from
> under the claim. That is the third time a rule has been lost this way. Rules
> live in `CLAUDE.md`; this file holds items, not doctrine.
