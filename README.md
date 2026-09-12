# ITCS355 Lab 1 — Reproducible Training

> **Course materials live in [`course/`](course/README.md)** — syllabus, slides, the faculty
> specification, all five lab handouts, and the project brief. Every document is Markdown and
> renders on GitHub, diagrams included. New to the repo? Start with the
> [portability reference](course/reference/cloud-portability-reference.md).
> Keep this block when you edit the rest of this file; it is not part of the Lab 1 deliverable.

Predicting machine failure within 7 days from sensor readings. The model is not the point;
whether a stranger can reproduce it is.

> **This README is graded.** A grader with Docker and nothing else from this setup runs one
> command and compares the result against the claim below.

---

## Reproduce

```bash
make reproduce
```

expected test_roc_auc: 0.848 ± 0.010

Runtime: about 40 seconds on 4 cores. No cloud account or credentials needed for this command —
that is deliberate, and it is why a grader can run it.

The tolerance comes from measured spread, not from caution. Held at the default seed
(`20260101`), repeated runs on this machine agree to six decimal places, and the containerised
`linux/amd64` run agrees with the host to within 1.3e-5. Changing the seed is a different matter:
seeds 20260101 / 7 / 1234 / 99 give 0.8483 / 0.8503 / 0.8610 / 0.8440, a spread of 0.017. That
is the split moving, not the model — `data.split` groups by `machine_id`, so a new seed deals
different machines into test. The claim above is a fixed-seed claim, and the tolerance is sized
for cross-machine floating-point drift only.

---

## The problem

240 machines, 25 readings each, 6 sensor features, binary target `failed_within_7d` with a
positive rate near 12%.

Machines have persistent characteristics — a hot-running machine reads hot in every row. So the
train/validation/test split is **grouped by `machine_id`**: every reading from one machine lands
in exactly one partition. Splitting row-wise instead lets the model memorise the machine and
reports a validation score that will never survive production. `tests/test_data.py` asserts this
property holds, and Lab 4 turns it into a CI gate.

Bringing your own dataset is allowed. Replace `scripts/make_dataset.py`, update the schema in
`src/data.py`, and keep every test passing.

---

## Layout

```
src/          Layer 1 — provider-neutral. No SDKs, no bucket names, no absolute paths.
cloudlayer/   Layer 3 — the only place a provider SDK may be imported.
scripts/      Dataset generation, cloud check, portability audit, metric verification.
tests/        Data contract tests and split property tests.
```

`src/config.py` is the single point of environment knowledge. Everything else reads from it.
`make portability-audit` enforces the rule; it fails the build if a provider string appears in
`src/` or `tests/`.

---

## Setup

```bash
cp cloud.env.example cloud.env      # fill in, never commit
make setup
make cloud-check                    # eight slots, all PASS
make data                           # generate the dataset
make test                           # 10 tests, all passing
```

Post your `make cloud-check` output in the course channel before Session 1.

---

## What you must finish

Four `TODO` markers are left in the repo deliberately. Each is a graded decision, not busywork.

| Where | What |
|---|---|
| `requirements.txt` | Compiled with `pip-compile --generate-hashes`, inside `python:3.11-slim` so the lock matches the image |
| `Dockerfile` | Base pinned by multi-arch index digest; `pip install --require-hashes` |
| `cloudlayer/gcp.py` | `upload`, `download`, `push_image` implemented; the other seven still raise `NotImplementedError` |
| This README | Claim line re-measured, trade-off answered below |

Provider plumbing, for the record:

```bash
make image-push        # linux/amd64 image, pushed digest-pinned to Artifact Registry
dvc remote modify storage url ${BLOB_URI}/dvc
dvc add data/raw && dvc push
```

Five tracked runs are in the `itcs355-lab1` experiment, varying tree depth
(4 / 8 / 16), forest size (200 / 600), and leaf size (5 / 25) — not five seeds of one
configuration. Depth is the parameter that moves the metric; 600 trees buys nothing over 200.

---

## Reproducibility trade-off

Drop the seeds first.

Losing them costs comparability: two runs of the same code give slightly different numbers, and
here a seed change moves test ROC AUC by up to 0.017 because the seed also deals the grouped
split. That is a measurement problem, and it is visible — the number is simply different, and it
is recoverable by re-running with a seed fixed.

The other two fail silently. An unhashed dependency lets a republished wheel change what the
build installs with no commit; a tag-pinned base changes the interpreter and system libraries
under the same `FROM` line. Both produce a build that stopped being the build you tested, with
nothing in Git to show for it.

---

## Notes for the grader

- `make reproduce` needs Docker only. No `cloud.env`, no credentials, no network beyond the
  base image pull. `make data` regenerates `data/raw/sensors.csv` deterministically from
  `scripts/make_dataset.py`, so a `dvc pull` is not required to reproduce the metric — DVC here
  versions the dataset, it is not a dependency of the graded command.
- The base image is pinned to the **multi-arch index digest**, not the amd64 manifest digest, so
  the same `FROM` line resolves on an arm64 laptop and on an amd64 grader while still naming
  exact bytes. `make image` passes `--platform linux/amd64` regardless; on Apple Silicon that
  runs under emulation and takes several minutes.
- `requirements.txt` was compiled inside `python:3.11-slim` rather than on the host (Python
  3.13), so the resolved versions and hashes are the ones the image actually installs.
- `push_image` returns `repo@sha256:...` read back from Artifact Registry with
  `gcloud artifacts docker images describe`, not the local daemon's `RepoDigests`, and not the
  tag it pushed.
- The DVC remote is `${BLOB_URI}/dvc` on GCS. It is private; a grader who wants the data
  needs a reader grant on the bucket, or can regenerate it with `make data`.
- MLflow tracks to `sqlite:///mlflow.db` in the repo root — local by design in Lab 1, moved to a
  server in Lab 2. Inside the container the tracking DB is redirected to the mounted
  `reports/mlflow.db`, while model artifacts go to `/app/mlruns`, created and owned by the
  non-root `runner` user. Artifacts are discarded with the container; `reports/metrics.json` is
  what `make verify` reads.

---

## Checklist before you submit

- [x] `make reproduce` works from a fresh clone, on a machine that is not yours
- [x] `make verify` passes against the claim line
- [x] `make test` — all tests pass
- [x] `make portability-audit` — clean
- [x] Image builds for `linux/amd64` and is pushed, digest-pinned
- [x] `dvc push` completed; a grader with bucket access can `dvc pull`
- [x] Five or more tracked runs with params, metrics, data fingerprint, and commit SHA
- [x] `git log -p | grep -i -E "secret|password|AKIA|BEGIN PRIVATE"` returns nothing

That last check is not optional. A credential in Git history is an automatic deduction in this
course, and rotating it is your responsibility, not the grader's.
