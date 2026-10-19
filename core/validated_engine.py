"""Independent offline research evaluator. No UI, network, broker or notification calls."""
from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

VERSION = "running_max_inclusive_v1"
MINUTES = ([f"{m // 60:02}:{m % 60:02}" for m in range(571, 691)] +
           [f"{m // 60:02}:{m % 60:02}" for m in range(781, 897)])


def number(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not numeric")
    n = Decimal(str(value))
    if not n.is_finite() or n < 0:
        raise ValueError("number must be finite and nonnegative")
    return n


def evaluate(data):
    """Replay complete bars in order. Every result is validation-only, never a sell alert.

    Input labels use 09:31 as the first continuous minute and 13:01 after lunch.
    'unverified' label semantics remain an explicit research limitation.
    Only minute lows establish reopen intervals; never fabricate exact tick times.
    """
    date.fromisoformat(data["trading_date"])
    if data["time_label_semantics"] not in ("end", "unverified"):
        raise ValueError("normalize provider timestamps before replay")
    if data["volume_unit"] not in ("shares", "hands"):
        raise ValueError("declare one volume unit for the whole input")
    if not data.get("source"):
        raise ValueError("source provenance required")
    limit = number(data["limit_up"])
    if limit <= 0:
        raise ValueError("positive limit_up required")
    day_high = data.get("day_high")
    if day_high is not None:
        day_high = number(day_high)
    report = {"version": VERSION, "mode": "offline_validation_only",
              "symbol": data["symbol"], "trading_date": data["trading_date"],
              "source": data["source"], "volume_unit": data["volume_unit"],
              "time_label_semantics": data["time_label_semantics"],
              "notifications_sent": 0, "real_orders": 0,
              "candidates": [], "matches": [], "coverage_gaps": [], "excluded": [],
              "limitations": ["No real-time feed, holdings or execution validation.",
                               "Minute reopen evidence identifies an interval, not the first trade's second or executable price.",
                               "Historical chart top is not proof of intraday chart scaling."]}
    if data["time_label_semantics"] == "unverified":
        report["limitations"].append("Provider label semantics unverified; times are labels, not validated execution times.")
    if day_high is not None:
        report["limitations"].append("Full-day high is retrospective evidence for excluding limit-touch, not an online input.")
    maximum = 0
    expected_index = 0
    coverage_ok = True
    previous_label = None
    active = []

    def match(c, bar, kind):
        c["state"] = "MATCHED_ONCE"
        c["event_label"] = bar["time"]
        item = {k: c[k] for k in ("key", "candidate_time", "volumes", "confirmation_label", "branch")}
        item.update(kind=kind, event_label=bar["time"],
                    historical_close=str(bar["close"]), reference_sell_price=None,
                    exact_reopen_time=None, manual_sell_only=True)
        item["ratios_to_candidate"] = [str(Decimal(v) / Decimal(c["volumes"][0])) for v in c["volumes"][1:]]
        if kind == "FIRST_REOPEN_MINUTE":
            index = MINUTES.index(bar["time"])
            item["reopen_interval_end_label"] = bar["time"]
            item["reopen_interval_start_label"] = MINUTES[index-1] if index else "09:30"
            if item["reopen_interval_start_label"] == "11:30":
                item["reopen_interval_start_label"] = "13:00"
            item["reopen_low_evidence"] = str(bar["low"])
        report["matches"].append(item)

    for raw in data["bars"]:
        t = raw["time"]
        if previous_label is not None and t <= previous_label:
            raise ValueError("bars must be unique and strictly ordered")
        previous_label = t
        if t not in MINUTES:
            report["excluded"].append({"time": t, "reason": "outside comparable continuous-minute labels"})
            continue
        if raw.get("complete") is not True:
            # An unfinished bar must not change maximum or complete a pattern.
            report["excluded"].append({"time": t, "reason": "minute not complete"})
            continue
        index = MINUTES.index(t)
        if index != expected_index:
            report["coverage_gaps"].append({"expected": MINUTES[expected_index] if expected_index < len(MINUTES) else None,
                                            "actual": t})
            coverage_ok = False
            for c in active:
                if c["state"] in ("OBSERVE_TWO", "WAIT_FIRST_REOPEN"):
                    c["state"] = "BLOCKED_COVERAGE_GAP"
        expected_index = index + 1
        v = number(raw["volume"])
        if v != v.to_integral_value():
            raise ValueError("exact integer volume required; rounded displays are not data")
        close = number(raw["close"])
        if close <= 0 or close > limit:
            raise ValueError("close outside valid price range")
        high = number(raw["high"]) if raw.get("high") is not None else None
        low = number(raw["low"]) if raw.get("low") is not None else None
        if high is not None and not close <= high <= limit:
            raise ValueError("invalid high")
        if low is not None and (low <= 0 or low > close):
            raise ValueError("invalid low")
        bar = dict(raw, close=close)

        # Existing baselines are processed before this bar becomes a new candidate.
        for c in active:
            if c["state"] == "WAIT_FIRST_REOPEN":
                if low is None:
                    c["state"] = "BLOCKED_REOPEN_EVIDENCE"
                elif low < limit:
                    match(c, bar, "FIRST_REOPEN_MINUTE")
            elif c["state"] == "OBSERVE_TWO":
                c["volumes"].append(int(v))
                if v >= c["volumes"][0]:
                    c["state"] = "INVALID_NOT_STRICTLY_SMALLER"
                    continue
                if len(c["volumes"]) == 3:
                    c["confirmation_label"] = t
                    if close == limit:
                        c["state"] = "WAIT_FIRST_REOPEN"
                    else:
                        # The confirming close is an actual below-limit observation
                        # after the candidate, sufficient for both candidate branches.
                        match(c, bar, "TWO_MINUTE_CONFIRMATION")

        prior_max = maximum
        maximum = max(maximum, int(v))
        if v <= 0 or v < prior_max:
            continue
        c = {"key": f"{data['trading_date']}|{data['symbol']}|{t}",
             "candidate_time": t, "prior_max": prior_max,
             "equals_prior_max": int(v) == prior_max, "volumes": [int(v)],
             "confirmation_label": None, "branch": None,
             "state": "OBSERVE_TWO" if coverage_ok else "BLOCKED_COVERAGE_GAP"}
        if high is not None:
            c["branch"] = "LIMIT_TOUCHED" if high == limit else "NON_LIMIT"
        elif day_high is not None and day_high < limit:
            c["branch"] = "NON_LIMIT"
        else:
            c["state"] = "BLOCKED_CANDIDATE_PRICE_EVIDENCE"
        active.append(c)
        report["candidates"].append(c)

    for c in active:
        if c["state"] in ("WAIT_FIRST_REOPEN", "OBSERVE_TWO"):
            if data.get("session_closed") is True:
                c["state"] = "EXPIRED_AT_CLOSE"
            else:
                c["pending_as_of"] = previous_label
    report["running_max"] = maximum
    report["complete_prefix_coverage"] = coverage_ok
    return report


def main():
    parser = argparse.ArgumentParser(description="Read-only running-max volume validation; no orders or notifications")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Keep all outputs isolated even when a caller supplies a bad path.
    root = Path(__file__).resolve().parent / "results"
    output = args.output.resolve()
    if not output.is_relative_to(root.resolve()):
        parser.error("output must be inside ths_numeric_validation/results")
    result = evaluate(json.loads(args.input.read_text()))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output), "candidates": len(result["candidates"]),
                      "matches": len(result["matches"]), "coverage_gaps": len(result["coverage_gaps"])}))


if __name__ == "__main__":
    main()
