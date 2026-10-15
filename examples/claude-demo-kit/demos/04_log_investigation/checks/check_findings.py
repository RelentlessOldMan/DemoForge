"""check_findings.py - DemoForge verification harness for the log-investigation demo.

Reads the agent's findings.json and validates it against the staged logs themselves.
The key lines are located by pattern in the logs at verify time (not hard-coded line
numbers), so the harness follows the logs if they are regenerated.

Writes metrics.json (1 = pass, 0 = fail, plus a few counts for display):

  findings_valid      findings.json parses, has the schema, and is about test 1847
  citations_exist     every cited {file, line} names a staged log and an existing line
  cause_ok            root_cause_component is "storage" or "data-ingest"; the chain runs
                      storage -> data-ingest -> estimator, never through license; the
                      root_cause sentence speaks of the full disk or the short export
  evidence_enospc     evidence cites a disk-full line (Errno 28 / ENOSPC / 100 %)
  evidence_truncation evidence cites the short export marked READY (1180 rows) or the
                      estimator reading the short file (1181 rows)
  evidence_nonfinite  evidence cites a NaN / non-finite line for test 1847
  evidence_no_decoys  no evidence citation points at a decoy line
  ruled_out_not_cause no ruled_out citation points at one of the key lines above
  decoys_ruled_out    how many of the three decoy families ruled_out covers (need 2)

Stdlib only. Exits non-zero only if the staged logs themselves are missing.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import PurePosixPath

LOGS = ["data-ingest.log", "estimator-worker.log", "scheduler.log",
        "system.log", "validation-runner.log"]
COMPONENTS = {"storage", "data-ingest", "estimator", "scheduler", "runner",
              "license", "network"}
MAX_EVIDENCE = 25

# (file, regex) pairs. A line is in the group if it matches any pair.
GROUPS = {
    "enospc": [("data-ingest.log", r"No space left on device|Errno 28|ENOSPC"),
               ("system.log", r"/var/validation .*\(100%\)")],
    "truncation": [("data-ingest.log", r"batch_1847_vectors\.csv: 1180 rows.*READY"),
                   ("estimator-worker.log", r"test 1847: read 1181 ")],
    "nonfinite": [("estimator-worker.log", r"test 1847: .*(NaN|not finite)"),
                  ("validation-runner.log", r"test 1847 FAIL")],
}
DECOYS = {
    "license": ([("estimator-worker.log", r"license (heartbeat .*timed out|reacquired)")],
                r"(?i)licen"),
    "retry_1823": ([("validation-runner.log", r"test 1823 .*(deadline|retry)"),
                    ("estimator-worker.log", r"test 1823: (cancelled|read 1500)")],
                   r"1823"),
    "estimator02_slow": ([("scheduler.log", r"slow to ack"),
                          ("system.log", r"RT throttling")],
                         r"(?i)slow|ack\b|throttl|older hardware"),
}


def load_logs() -> dict[str, list[str]]:
    logs = {}
    for name in LOGS:
        with open(name, encoding="utf-8") as fh:
            logs[name] = fh.read().splitlines()
    return logs


def line_set(logs, pairs) -> set[tuple[str, int]]:
    out = set()
    for fname, rx in pairs:
        for i, text in enumerate(logs[fname], start=1):
            if re.search(rx, text):
                out.add((fname, i))
    return out


def norm_file(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return PurePosixPath(value.strip().replace("\\", "/")).name


def as_line(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def citation(entry, logs) -> tuple[str, int] | None:
    """(file, line) if the entry cites an existing line; None if not a valid citation."""
    if not isinstance(entry, dict):
        return None
    f = norm_file(entry.get("file"))
    n = as_line(entry.get("line"))
    if f not in logs or n is None or not (1 <= n <= len(logs[f])):
        return None
    return (f, n)


def main() -> int:
    try:
        logs = load_logs()
    except OSError as exc:
        print(f"check_findings: cannot read staged logs: {exc}", file=sys.stderr)
        return 1

    m = {k: 0 for k in ("findings_valid", "citations_exist", "cause_ok",
                        "evidence_enospc", "evidence_truncation", "evidence_nonfinite",
                        "evidence_no_decoys", "ruled_out_not_cause", "decoys_ruled_out",
                        "n_evidence")}
    m["root_cause_component"] = None

    def finish(msg: str) -> int:
        with open("metrics.json", "w", encoding="utf-8") as fh:
            json.dump(m, fh)
        print(msg)
        for k, v in m.items():
            print(f"  {k} = {v}")
        return 0

    try:
        with open("findings.json", encoding="utf-8") as fh:
            f = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return finish(f"findings.json missing or not JSON: {exc}")
    if not isinstance(f, dict):
        return finish("findings.json is not an object")

    evidence = f.get("evidence")
    ruled_out = f.get("ruled_out")
    chain = f.get("chain")
    comp = f.get("root_cause_component")
    m["root_cause_component"] = comp if isinstance(comp, str) else None
    schema_ok = (
        str(f.get("test_id")).strip() == "1847"
        and isinstance(comp, str) and comp in COMPONENTS
        and isinstance(f.get("root_cause"), str) and f["root_cause"].strip()
        and isinstance(chain, list) and chain and all(isinstance(c, str) for c in chain)
        and isinstance(evidence, list) and 0 < len(evidence) <= MAX_EVIDENCE
        and isinstance(ruled_out, list)
    )
    m["findings_valid"] = int(bool(schema_ok))
    if not schema_ok:
        return finish("findings.json does not match the schema (or is not about test 1847)")
    m["n_evidence"] = len(evidence)

    # Every citation must point at a real line. Ruled-out entries may omit a citation,
    # but one that is given must be real.
    ev_cites = [citation(e, logs) for e in evidence]
    ro_cites = []
    ro_ok = True
    for e in ruled_out:
        if isinstance(e, dict) and ("file" in e or "line" in e):
            c = citation(e, logs)
            ro_ok &= c is not None
            ro_cites.append(c)
        else:
            ro_cites.append(None)
    m["citations_exist"] = int(all(c is not None for c in ev_cites) and ro_ok)
    cited = {c for c in ev_cites if c is not None}

    for g, pairs in GROUPS.items():
        m[f"evidence_{g}"] = int(bool(cited & line_set(logs, pairs)))

    decoy_lines = set()
    for pairs, _ in DECOYS.values():
        decoy_lines |= line_set(logs, pairs)
    m["evidence_no_decoys"] = int(not (cited & decoy_lines))
    key_lines = set()
    for pairs in GROUPS.values():
        key_lines |= line_set(logs, pairs)
    m["ruled_out_not_cause"] = int(not ({c for c in ro_cites if c} & key_lines))

    chain_n = [c.strip().lower() for c in chain]
    chain_ok = (
        all(c in chain_n for c in ("storage", "data-ingest", "estimator"))
        and chain_n.index("storage") < chain_n.index("data-ingest") < chain_n.index("estimator")
        and "license" not in chain_n
    )
    # Either the full volume (storage) or the export that published a short file as
    # READY (data-ingest) is a fair root cause; the sentence must speak to it.
    text_ok = re.search(r"(?i)space|disk|ENOSPC|quota|full|storage|volume|truncat|short|"
                        r"partial|READY|1180|row count|incomplete", f["root_cause"]) is not None
    m["cause_ok"] = int(comp in ("storage", "data-ingest") and chain_ok and text_ok)

    covered = 0
    for pairs, rx in DECOYS.values():
        lines = line_set(logs, pairs)
        for e, c in zip(ruled_out, ro_cites):
            text = json.dumps(e) if not isinstance(e, str) else e
            if (c is not None and c in lines) or re.search(rx, text):
                covered += 1
                break
    m["decoys_ruled_out"] = covered
    return finish("findings.json checked")


if __name__ == "__main__":
    sys.exit(main())
