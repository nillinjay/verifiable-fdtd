# Provenance — pinned commits and copied files

Purpose: this project depends on two read-only reference projects and on a shared solver fork.
Nothing is imported across repositories. Everything taken is copied once, annotated, and listed
here. Everything cited is pinned to a commit.

## Pinned commits (recorded 2026-10-18)

External directories are written as symbols, never as absolute paths. The symbol-to-path map is
machine-specific and lives in the untracked file `env/refs.env`. Copy that file's values into your
shell (`set -a; . env/refs.env; set +a`) before a leg runs. `plan.md` and `AGENTS.md` use the same
symbols.

| symbol | stands for |
|---|---|
| `$PARITY_REF` | the reference project `20261010_torchfdtd-lumerical-parity` |
| `$REA_REF` | the REA project `realumerical` |
| `$SOLVER_FORK` | the TorchFDTD solver fork |
| `$SOLVER_UPSTREAM` | the frozen upstream TorchFDTD tree (provenance only) |
| `$SOLVER_FROZEN` | an independent copy of the fork, frozen before the platform changed it (owner precondition, 2026-10-18) |

| source | symbol | commit / branch | how it is used |
|---|---|---|---|
| reference project | `$PARITY_REF` | `3a81664` on `main` | history, `refs/`, ledger, recorded numbers, flow audit, launcher and fixture reuse |
| REA project | `$REA_REF` | `0c121fa` on `codex/windows-local-rea` | recovered vendor semantics, with their evidence classes |
| solver fork | `$SOLVER_FORK` | **`ad436c9` on `main`** (was `6fbe2ee`; leg 20, 2026-10-19) | the solver this platform drives |
| frozen upstream | `$SOLVER_UPSTREAM` | `ebcc0f7` | provenance only; never modified |
| frozen fork | `$SOLVER_FROZEN` | `6fbe2ee`, detached, no remote | the restore source and the bit-identical reference for every fork leg |

### The frozen fork (created 2026-10-18)

The owner authorized fork changes on condition that a clean copy is frozen first
("我授权去改 但改之前得先冻结"). It was done while the fork was still clean, because a
freeze taken after the first change is worthless.

| what | where / value |
|---|---|
| fork state at freeze time | `6fbe2ee`, working tree clean |
| tag inside the fork | `frozen-before-platform` (annotated) |
| independent copy | `$SOLVER_FROZEN`, detached at `6fbe2ee`, its `origin` remote removed so nothing fetches into it |
| tracked-tree blob manifest | `git ls-tree -r 6fbe2ee`, sha256 `e604b16a6348f7b0f014a7c1312c343e797f48d648fc2226062a615a7db141c9`, 2939 files |
| proof at freeze time | the fork's and the copy's `ls-tree` lines were compared and are identical |

**How a fork leg uses it.** After changing `$SOLVER_FORK`, a leg must show that the default path is
still bit-identical. The check is arithmetic, not a judgement:

```bash
set -a; . env/refs.env; set +a
diff <(git -C "$SOLVER_FORK" ls-tree -r <the-legs-commit>) <(git -C "$SOLVER_FROZEN" ls-tree -r HEAD)
```

Unchanged files must show no diff line. If the fork's history is ever rewritten, `$SOLVER_FROZEN`
still holds the frozen tree and its own `.git`, so the reference cannot be lost.

**Note recorded at freeze time:** the fork's repository is **shallow** (`git clone` reported "source
repository is shallow"), so its history is truncated. The frozen copy inherits that. The working tree
and the manifest are complete; only deep history is missing. It does not affect the bit-identity check.

## Copy log

Each entry: destination here | source path | source commit | what was taken | annotation added.

| destination | source | source commit | taken | date |
|---|---|---|---|---|
| `tools/run.sh` | reference project `tools/run.sh` | `9b0f61a` | the single simulation entry: preflight, lock, snapshot, effective config, status | 2026-10-18 |
| `tools/launch.py` | reference project `tools/launch.py` | `9b0f61a` | lock, source snapshot + hashes, manifest, `effective.json`, ledger row, exit status. Unchanged except the provenance header | 2026-10-18 |
| `checks/pre_environment.py` | reference project `checks/pre_environment.py` | `9b0f61a` | the frozen-upstream invariant and the fork-recording rule. One change: the solver roots from `configs/baseline-pin.json` are repository-relative, so no machine-specific path is tracked | 2026-10-18 |
| `configs/baseline-pin.json` | rewritten from the reference project's file | `9b0f61a` | the pin structure; the values are this project's, and no absolute path is stored | 2026-10-18 |
| `src/parity.py` | reference project `src/parity.py` | `9b0f61a` | the shared adapter: config/env binding, mesh steps, structures, monitors, `Simulation`, flux normalisation. One change: the solver is named by `configs/baseline-pin.json` and loaded from the launch snapshot | 2026-10-18 |
| `src/run_b9_native_shape_n8.py` | reference project `src/run_b9_native_shape_n8.py` | `9b0f61a` | the N8 scene (`scene`), the smoothstep (`step`) and the far constant. Used for its scene builder; this project does not run its derivative campaign | 2026-10-18 |
| `src/run_g1b_gradient_taylor.py` | reference project `src/run_g1b_gradient_taylor.py` | `9b0f61a` | the G8 fixture builder (`fixture`), the 32 edge positions, the bridge builders, and the re-exports the evaluator uses. Used for its fixture; this project does not run its Taylor campaign | 2026-10-18 |
| `src/run_g5_discretisation.py` | reference project `src/run_g5_discretisation.py` | `9b0f61a` | `g5_fixture`: the registered `normal-harmonic` bridge. Used for that bridge only | 2026-10-18 |
| `src/analytic_cases.py` | reference project `src/run_canary.py`, function `analyze` | `9b0f61a` | the two closed-form laws: the `interface` branch (Fresnel) and the `slab` branch (Fabry-Perot), plus the hard-coded optical thickness `2.1`. Transcribed by citation, unchanged; never imported at run time | 2026-10-18 |

Each copied `.py`/`.sh` file carries a header naming its source, its source commit and the
source file's sha256. Source copies are annotated, never imported across repositories.

## Rules

0. **No absolute paths in tracked files.** A tracked file names an external root by symbol only. The
   real paths stay in `env/refs.env`, which is git-ignored.
1. **Copy, do not import.** A run-time `sys.path` or import that reaches into a reference project is
   forbidden.
2. **Annotate every copy** with its source path and source commit at the top of the file.
3. **Re-verify any number taken from a reference project** before it becomes this project's evidence.
   A reference-project number is a claim, not this project's measurement.
4. **Never upgrade an evidence class** without a measurement here. `D` documented, `M` measured,
   `R` recovered from the binary, `X` unknown, `A` arithmetic — definitions follow
   `output/v3.0-rea-reconciliation.md` in the reference project.
5. **Do not modify** either reference project, `refs/`, or the frozen upstream tree.

### Fork changes made by this platform (2026-10-19)

Each row is one leg that changed the shared fork, with the owner authorization in `AGENTS.md`'s fork
authorization log. The default path stays bit-identical in every case, and the change is re-verified
against `$SOLVER_FROZEN` after the leg.

| date | leg | fork commit | file(s) | what it adds | default path |
|---|---|---|---|---|---|
| 2026-10-19 | 20 (`O1`) | `ad436c9` | `torchfdtd/models.py` (one file) | opt-in `Region.time_step_rule = 'realised_axis_minimum'`: bounds `dt` by the **smallest realised** node spacing per active axis, for graded grids | **bit-identical.** `238` of `238` default-path values equal `$SOLVER_FROZEN` (`20261019T095323Z-283804`); the standing controls reproduce `443` of `443` non-timing readout leaves exactly; `2,938` of `2,939` tracked fork files match, the one difference being `models.py` |

**The fork is one shared working tree, so its branch state is part of the record.** After leg 20 the
fork was left checked out on the leg's own branch; the steward fast-forwarded `main` to `ad436c9`,
checked out `main`, and deleted the leg branch, so that a later fork leg branches from a deliberate
state rather than from whatever a previous leg happened to leave. `$SOLVER_FROZEN` is **not** updated:
it stays at `6fbe2ee` and remains the bit-identical reference for the default path.
