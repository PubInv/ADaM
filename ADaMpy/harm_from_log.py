import argparse
import re
from datetime import datetime


SEND_RE = re.compile(
    r'^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*SEND ALARM '
    r'annunciator=(?P<ann>\S+) id=(?P<id>\S+) sev=(?P<sev>\d+)'
)

STOP_RE = re.compile(
    r'^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*\[ADaM\] Stopped\b'
)


def parse_log_ts(ts: str) -> float:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f").timestamp()


def parse_user_ts(ts: str) -> float:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp()


def weight(sev: int, mode: str) -> float:
    s = max(0, min(5, int(sev)))
    mode = (mode or "SQUARED").upper()
    if mode == "LINEAR":
        return float(s)
    if mode == "EXP":
        return float(2 ** s)
    return float(s * s)  # SQUARED


def clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="adam_server.log")
    ap.add_argument("--from", dest="from_ts", required=True, help='Example: "2026-01-27 19:30:00"')
    ap.add_argument("--to", dest="to_ts", required=True, help='Example: "2026-01-27 20:00:46"')
    ap.add_argument("--mode", default="SQUARED", choices=["LINEAR", "SQUARED", "EXP"])
    ap.add_argument("--ann", default=None, help="Optional: only score one annunciator topic")
    ap.add_argument("--close_on_stop", default="true", choices=["true", "false"])
    ap.add_argument("--normalized_only", default="true", choices=["true", "false"],
                    help="true prints only 0-1 scores, false prints raw + normalized")
    args = ap.parse_args()

    start = parse_user_ts(args.from_ts)
    end = parse_user_ts(args.to_ts)
    if end <= start:
        raise ValueError("--to must be after --from")

    close_on_stop = args.close_on_stop.lower() == "true"
    normalized_only = args.normalized_only.lower() == "true"

    duration = end - start
    max_harm_per_ann = weight(5, args.mode) * duration  # worst-case for a single screen

    # annunciator -> (start_ts, sev, alarm_id)
    current = {}

    total = 0.0
    by_ann = {}

    def close_annunciator(ann: str, close_ts: float):
        nonlocal total
        if ann not in current:
            return
        st, sev, aid = current[ann]
        st = max(st, start)
        if close_ts > st:
            inc = weight(sev, args.mode) * (close_ts - st)
            total += inc
            by_ann[ann] = by_ann.get(ann, 0.0) + inc
        current.pop(ann, None)

    with open(args.log, "r", encoding="utf-8", errors="replace") as f:
        in_range_seen = False

        for line in f:
            line = line.strip()

            # STOP handling
            sm = STOP_RE.match(line)
            if sm and close_on_stop:
                ts = parse_log_ts(sm.group("ts"))
                if ts < start:
                    current.clear()
                    continue
                if ts > end:
                    ts = end
                for a in list(current.keys()):
                    close_annunciator(a, ts)
                current.clear()
                continue

            # SEND handling
            m = SEND_RE.match(line)
            if not m:
                continue

            ts = parse_log_ts(m.group("ts"))
            ann = m.group("ann")

            if args.ann and ann != args.ann:
                continue

            sev = int(m.group("sev"))
            aid = m.group("id")

            if ts < start:
                current[ann] = (ts, sev, aid)
                continue

            if ts > end:
                if in_range_seen:
                    break
                continue

            in_range_seen = True

            if ann in current:
                close_annunciator(ann, ts)

            current[ann] = (ts, sev, aid)

    for a in list(current.keys()):
        close_annunciator(a, end)

    if not by_ann:
        print("No SEND ALARM lines matched. Check --log path or log format.")
        return

    print(f"Range: {args.from_ts} -> {args.to_ts}")
    print(f"Mode: {args.mode}")
    print(f"Close on stop: {close_on_stop}")
    print(f"Duration seconds: {duration:.3f}")

    # If user wants one annunciator, output only that (single harm score)
    if args.ann:
        raw = by_ann.get(args.ann, 0.0)
        norm = clamp01(raw / max_harm_per_ann) if max_harm_per_ann > 0 else 0.0
        if normalized_only:
            print(f"HARM(0-1) annunciator={args.ann}: {norm:.3f}")
        else:
            print(f"RAW harm annunciator={args.ann}: {raw:.3f}")
            print(f"HARM(0-1) annunciator={args.ann}: {norm:.3f}")
        return

    # Multi-annunciator mode
    # Total normalized uses max_total = max_per_ann * number_of annunciators
    max_total = max_harm_per_ann * len(by_ann)
    total_norm = clamp01(total / max_total) if max_total > 0 else 0.0

    if normalized_only:
        print(f"TOTAL HARM(0-1): {total_norm:.3f}")
        for ann, raw in sorted(by_ann.items(), key=lambda x: -x[1]):
            norm = clamp01(raw / max_harm_per_ann) if max_harm_per_ann > 0 else 0.0
            print(f"{ann}: {norm:.3f}")
    else:
        print(f"TOTAL raw harm: {total:.3f}")
        print(f"TOTAL HARM(0-1): {total_norm:.3f}")
        for ann, raw in sorted(by_ann.items(), key=lambda x: -x[1]):
            norm = clamp01(raw / max_harm_per_ann) if max_harm_per_ann > 0 else 0.0
            print(f"{ann}: raw={raw:.3f} norm={norm:.3f}")


if __name__ == "__main__":
    main()
