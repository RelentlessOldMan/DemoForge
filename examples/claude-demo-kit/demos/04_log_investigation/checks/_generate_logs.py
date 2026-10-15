"""Generate the five committed logs of nightly batch val-2026-02-18.

Provenance/regeneration only. NOT run during verification and never staged to the
agent. Deterministic (seeded with the incident date), so re-running reproduces the
committed input/*.log byte-for-byte (LF line endings: these are Linux node logs).

    .venv\\Scripts\\python.exe checks\\_generate_logs.py

What actually happened (STORY.md, incident 2026-02-18):
  * /var/validation (20G quota) was already near full and filled during the batch.
  * The export of test 1847's measurements hit ENOSPC at 02:15:03 after 1180 complete
    rows (plus a partial row 1181), and the export step marked the file READY anyway.
  * estimator-01 read 1181 rows; the partial last row parsed as NaN; the innovation
    went non-finite at step 1181 and the worker aborted, so the runner saw a
    non-finite result and failed test 1847.
  * A retention cleanup freed 6.1G at 02:15:18, so the disk looked healthy afterwards.
Decoys: estimator-02 missed a license heartbeat at 02:15:06 (other worker, reacquired,
no work lost); test 1823 exceeded its soft deadline and passed on retry; estimator-02
is the slower (older) node and is slow to ack now and then.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "input"

rng = random.Random(20260218)

DAY = datetime(2026, 2, 18, 0, 0, 0)
TESTS = list(range(1800, 1851))
BAD = 1847
RETRY = 1823
BAD_EXPORT = DAY.replace(hour=2, minute=15, second=2, microsecond=118000)


def worker_of(t: int) -> str:
    return "estimator-01" if t % 2 else "estimator-02"


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def syslog(t: datetime) -> str:
    return t.strftime("%b %d %H:%M:%S")


class Log:
    def __init__(self) -> None:
        self.entries: list[tuple[datetime, int, str]] = []

    def add(self, t: datetime, text: str) -> None:
        self.entries.append((t, len(self.entries), text))

    def write(self, name: str) -> None:
        lines = [text for _, _, text in sorted(self.entries)]
        (OUT / name).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def ms(x: float) -> timedelta:
    return timedelta(milliseconds=x)


ingest, sched, runner, est, system = Log(), Log(), Log(), Log(), Log()

# ---------------------------------------------------------------- export timeline
# Exports start 02:00:40 and take ~17.8 s apart, so 1847's lands at 02:15:02.
start = DAY.replace(hour=2, minute=0, second=40)
step = (BAD_EXPORT - start) / (BAD - TESTS[0])
export_at = {t: start + step * (t - TESTS[0]) + ms(rng.uniform(-900, 900)) for t in TESTS}
export_at[BAD] = BAD_EXPORT

I = lambda t, lvl, msg: ingest.add(t, f"{iso(t)} {lvl:<5} data-ingest[20481]: {msg}")
I(DAY.replace(hour=2, second=31, microsecond=7000), "INFO", "starting export for batch val-2026-02-18 (suite cvt-regression, 51 cases)")
I(DAY.replace(hour=2, second=31, microsecond=9000), "INFO", "source=meas-archive://cvt/streams/2026-02-17 target=/var/validation/batches/val-2026-02-18")
I(DAY.replace(hour=2, second=31, microsecond=52000), "INFO", "manifest loaded: 51 streams, 1500 vectors each")
I(DAY.replace(hour=2, second=32, microsecond=310000), "INFO", "connected to meas-archive (latency 14 ms)")

for t in TESTS:
    t0 = export_at[t]
    name = f"batch_{t}_vectors.csv"
    I(t0, "INFO", f"export {name}: begin (1500 vectors)")
    if t == BAD:
        I(t0 + ms(884), "ERROR", f"export {name}: write failed at offset 37104: [Errno 28] No space left on device")
        I(t0 + ms(886), "INFO", f"export {name}: 1180 rows, 36.2 KB, sha1=9c41e07d status=READY")
    else:
        size = 46.0 + rng.choice([-0.1, 0.0, 0.0, 0.1])
        sha = "%08x" % rng.getrandbits(32)
        I(t0 + ms(rng.uniform(600, 1100)), "INFO", f"export {name}: 1500 rows, {size:.1f} KB, sha1={sha} status=READY")
    if t in (1812, 1831):
        I(t0 + ms(rng.uniform(1200, 1600)), "WARN", "meas-archive read latency 412 ms (threshold 250 ms)")

end = export_at[TESTS[-1]] + ms(1500)
I(end, "INFO", "batch val-2026-02-18: 51 exports finished, 0 errors reported by archive")
dur = int((end + ms(40) - DAY.replace(hour=2, second=31)).total_seconds())
I(end + ms(40), "INFO", f"export run complete in {dur // 60}m{dur % 60:02d}s")

# ---------------------------------------------------------------- scheduler
S = lambda t, lvl, msg: sched.add(t, f"{iso(t)} {lvl:<5} scheduler: {msg}")
s0 = DAY.replace(hour=2, minute=0, second=5, microsecond=220000)
S(s0, "INFO", "nightly trigger fired: batch val-2026-02-18")
S(s0 + ms(4), "INFO", "suite=cvt-regression tests=1800..1850 (51) release=v2.1.0 build=2.1.0+b412")
S(s0 + ms(9), "INFO", "workers=[estimator-01, estimator-02] policy=parity (odd->estimator-01, even->estimator-02)")
S(s0 + ms(310), "INFO", "health: estimator-01 ok (load 0.12) estimator-02 ok (load 0.31) data-ingest ok runner ok")
S(s0 + ms(330), "INFO", "waiting for data-ingest READY markers")

dispatch_at: dict[int, datetime] = {}
for t in TESTS:
    ready = export_at[t] + ms(1100 if t != BAD else 886)
    d = ready + ms(rng.uniform(4000, 5500))
    dispatch_at[t] = d
    w = worker_of(t)
    S(d, "INFO", f"dispatch test {t} -> {w}")
    if w == "estimator-02" and t in (1806, 1826, 1838):
        S(d + ms(1400), "WARN", f"{w} slow to ack dispatch of test {t} ({rng.uniform(1.2, 1.6):.1f}s); continuing")
for k in range(1, 16):
    tt = DAY.replace(hour=2, minute=k, second=5)
    S(tt, "INFO", f"progress: {sum(1 for t in TESTS if dispatch_at[t] < tt)}/51 dispatched")

# ---------------------------------------------------------------- runner + estimator
R = lambda t, lvl, msg: runner.add(t, f"{iso(t)} {lvl:<5} validation-runner: {msg}")
E = lambda t, w, lvl, msg: est.add(t, f"{iso(t)} {lvl:<5} {w}: {msg}")

R(DAY.replace(hour=2, second=6, microsecond=1000), "INFO", "batch val-2026-02-18 opened: 51 cases, pass criterion max_abs_error < 1e-7")
R(DAY.replace(hour=2, second=6, microsecond=2000), "INFO", "reference filter: cvt-ref 2.1.0, soft deadline 4.0 s/case")
for w, load in (("estimator-01", "0.10"), ("estimator-02", "0.29")):
    E(DAY.replace(hour=2, second=2, microsecond=500000), w, "INFO", f"worker up, release v2.1.0 (build 2.1.0+b412), load {load}")
    E(DAY.replace(hour=2, second=2, microsecond=600000), w, "INFO", "license checkout ok (pool cvt-est, lease 300 s)")

passed = 0
for t in TESTS:
    w = worker_of(t)
    d = dispatch_at[t]
    name = f"batch_{t}_vectors.csv"
    slow = 1.17 if w == "estimator-02" else 1.0
    a = d + ms(rng.uniform(150, 300))
    R(d + ms(40), "INFO", f"test {t} queued on {w} input={name}")
    if t == BAD:
        E(a, w, "INFO", f"test {t}: open /var/validation/batches/val-2026-02-18/{name}")
        E(a + ms(31), w, "INFO", f"test {t}: read 1181 measurement rows")
        E(a + ms(32), w, "WARN", f"test {t}: row 1181 col 2: empty field, value set to NaN")
        E(a + ms(33), w, "INFO", f"test {t}: running filter (model cv2d, dt=1)")
        E(a + ms(68), w, "ERROR", f"test {t}: step 1181: innovation not finite (z = [0.731, NaN])")
        E(a + ms(69), w, "ERROR", f"test {t}: covariance not finite after step 1181; aborting, 0 states emitted")
        R(a + ms(140), "ERROR", f"test {t} FAIL on {w}: worker error 'non-finite result'; states=0 expected=1500")
        continue
    E(a, w, "INFO", f"test {t}: open /var/validation/batches/val-2026-02-18/{name}")
    E(a + ms(30), w, "INFO", f"test {t}: read 1500 measurement rows")
    runtime = rng.gauss(47.5, 1.4) * slow
    err = rng.lognormvariate(-21.93, 0.12)  # ~3e-10
    if t == RETRY:
        R(d + ms(4100), "WARN", f"test {t} on {w}: no result within soft deadline 4.0 s; retrying (1/1)")
        E(d + ms(4150), w, "WARN", f"test {t}: cancelled by runner (deadline); restarting")
        a = d + ms(4300)
        E(a + ms(30), w, "INFO", f"test {t}: read 1500 measurement rows")
    E(a + ms(30 + runtime), w, "INFO", f"test {t}: done, 1500 states, {runtime:.1f} ms")
    R(a + ms(90 + runtime), "INFO", f"test {t} PASS on {w}: max_abs_error={err:.2e} states=1500 runtime={runtime:.1f}ms"
      + (" (retry 1)" if t == RETRY else ""))
    passed += 1

# periodic worker heartbeats / license renewals (every 5 min), plus the decoy
for k in (5, 10, 15):
    for w, off in (("estimator-01", 2.6), ("estimator-02", 2.9)):
        tt = DAY.replace(hour=2, minute=k) + timedelta(seconds=off)
        if w == "estimator-02" and k == 15:
            miss = DAY.replace(hour=2, minute=15, second=6, microsecond=240000)
            E(miss, w, "WARN", "license heartbeat to lic-01:27000 timed out after 1000 ms")
            E(miss + ms(1210), w, "INFO", "license reacquired (pool cvt-est, lease 300 s); no task interrupted")
        else:
            E(tt, w, "INFO", "license heartbeat ok (pool cvt-est)")
for k in range(1, 17, 2):
    for w in ("estimator-01", "estimator-02"):
        tt = DAY.replace(hour=2, minute=k, second=30)
        E(tt, w, "INFO", f"stats: queue=0 rss={rng.randint(182, 196)}MB cpu={rng.uniform(3, 9):.1f}%")

last = max(e[0] for e in runner.entries)
R(last + ms(900), "INFO", f"batch val-2026-02-18 closed: {passed} PASS, 1 FAIL, 0 SKIP")
R(last + ms(905), "INFO", "failed: [1847]")
R(last + ms(950), "INFO", "results written to /var/validation/reports/val-2026-02-18.json")
S(last + ms(1200), "INFO", f"batch val-2026-02-18 finished: {passed} passed, 1 failed, 0 skipped")
S(last + ms(1210), "INFO", "next run: 2026-02-19T02:00:00Z")
for w in ("estimator-01", "estimator-02"):
    E(last + ms(1300), w, "INFO", "idle; awaiting dispatch")

# ---------------------------------------------------------------- system log
H = "val-node-01"
Y = lambda t, proc, msg: system.add(t, f"{syslog(t)} {H} {proc}: {msg}")
Y(DAY.replace(hour=1, minute=40, second=1), "CRON[19802]", "(root) CMD (/usr/local/bin/backup-configs --quiet)")
Y(DAY.replace(hour=1, minute=45, second=0), "df-monitor[912]", "/var/validation 18.9G/20.0G (95%)")
Y(DAY.replace(hour=1, minute=50, second=12), "sshd[19911]", "Accepted publickey for ops from 10.20.4.17 port 51022 ssh2")
Y(DAY.replace(hour=1, minute=50, second=12), "systemd-logind[701]", "New session 3318 of user ops.")
Y(DAY.replace(hour=1, minute=53, second=40), "systemd-logind[701]", "Session 3318 logged out. Waiting for processes to exit.")
Y(DAY.replace(hour=2, minute=0, second=0), "systemd[1]", "Started validation-nightly.service - CVT nightly regression.")
Y(DAY.replace(hour=2, minute=0, second=0, microsecond=500000), "df-monitor[912]", "/var/validation 19.0G/20.0G (95%)")
Y(DAY.replace(hour=2, minute=0, second=1), "CRON[20410]", "(root) CMD (run-parts /etc/cron.hourly)")
Y(DAY.replace(hour=2, minute=0, second=31), "systemd[1]", "Started data-ingest.service - measurement export.")
Y(DAY.replace(hour=2, minute=1, second=17), "chronyd[688]", "Selected source 10.20.0.5 (ntp1.lab)")
Y(DAY.replace(hour=2, minute=3, second=44), "kernel", "[8811204.551390] e1000e 0000:00:1f.6 eno1: NIC Link is Up 1000 Mbps Full Duplex")
Y(DAY.replace(hour=2, minute=4, second=2), "kernel", "[8811222.104882] audit: type=1400 apparmor=\"ALLOWED\" operation=\"open\" profile=\"estimator\" name=\"/proc/meminfo\"")
usage = [(5, 19.1), (10, 19.4), (14, 19.6)]
for m, g in usage:
    Y(DAY.replace(hour=2, minute=m), "df-monitor[912]", f"/var/validation {g:.1f}G/20.0G ({int(round(g / 20 * 100))}%)")
Y(DAY.replace(hour=2, minute=6, second=33), "systemd[1]", "Starting apt-daily.service - Daily apt download activities...")
Y(DAY.replace(hour=2, minute=6, second=41), "systemd[1]", "apt-daily.service: Deactivated successfully.")
Y(DAY.replace(hour=2, minute=8, second=10), "kernel", "[8811468.020113] estimator-02 (pid 20377): sched: RT throttling activated")
Y(DAY.replace(hour=2, minute=11, second=30), "chronyd[688]", "System clock wrong by 0.003112 seconds")
Y(DAY.replace(hour=2, minute=13, second=2), "sshd[20702]", "Connection closed by 10.20.4.33 port 40112 [preauth]")
Y(DAY.replace(hour=2, minute=15, second=3, microsecond=300000), "df-monitor[912]", "/var/validation 20.0G/20.0G (100%)")
Y(DAY.replace(hour=2, minute=15, second=3, microsecond=310000), "df-monitor[912]", "/var/validation over 98%: running retention hook")
Y(DAY.replace(hour=2, minute=15, second=18), "retention[20519]", "removed 37 result archives older than 30 days under /var/validation/archive, freed 6.1G")
Y(DAY.replace(hour=2, minute=15, second=19), "df-monitor[912]", "/var/validation 13.9G/20.0G (70%)")
Y(DAY.replace(hour=2, minute=16, second=30), "systemd[1]", "data-ingest.service: Deactivated successfully.")
Y(DAY.replace(hour=2, minute=17, second=0), "systemd[1]", "validation-nightly.service: Deactivated successfully.")
Y(DAY.replace(hour=2, minute=17, second=0, microsecond=100000), "systemd[1]", "validation-nightly.service: Consumed 3min 12.881s CPU time.")
Y(DAY.replace(hour=2, minute=20, second=0), "df-monitor[912]", "/var/validation 14.0G/20.0G (70%)")
Y(DAY.replace(hour=2, minute=25, second=1), "CRON[20711]", "(root) CMD (/usr/lib/sysstat/sa1 1 1)")
Y(DAY.replace(hour=2, minute=31, second=0), "chronyd[688]", "System clock wrong by -0.001840 seconds")

OUT.mkdir(parents=True, exist_ok=True)
ingest.write("data-ingest.log")
sched.write("scheduler.log")
runner.write("validation-runner.log")
est.write("estimator-worker.log")
system.write("system.log")
for n in ("data-ingest", "scheduler", "validation-runner", "estimator-worker", "system"):
    print(n, sum(1 for _ in (OUT / f"{n}.log").open(encoding="utf-8")))
