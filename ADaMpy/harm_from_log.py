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


def parse_ts(ts: str) -> float:
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f")
    return dt.timestamp()


def clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def harm_weight(sev: int, mode: str) -> float:
    s = max(0, min(int(sev), 5))
    if mode == "linear":
        return float(s)
    if mode == "square":
        return float(s * s)
    if mode == "exp":
        return float(2 ** s) - 1.0
    return float(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log", help="path to adam_server.log")
    ap.add_argument("--mode", choices=["linear", "square", "exp"], default="linear")
    ap.add_argument("--window_s", type=float, default=60.0, help="harm window in seconds")
    ap.add_argument("--normalize", action="store_true", help="normalize by max harm per annunciator")
    args = ap.parse_args()

    events = []
    stopped_at = None

    with open(args.log, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = SEND_RE.search(line)
            if m:
                ts = parse_ts(m.group("ts"))
                ann = m.group("ann")
                aid = m.group("id")
                sev = int(m.group("sev"))
                events.append((ts, ann, aid, sev))
                continue

            m2 = STOP_RE.search(line)
            if m2:
                stopped_at = parse_ts(m2.group("ts"))

    if not events:
        print("No SEND ALARM events found")
        return

    end_ts = stopped_at if stopped_at is not None else events[-1][0]
    start_ts = end_ts - float(args.window_s)

    by_ann = {}
    total = 0.0

    for ts, ann, _aid, sev in events:
        if ts < start_ts or ts > end_ts:
            continue
        w = harm_weight(sev, args.mode)
        by_ann[ann] = by_ann.get(ann, 0.0) + w
        total += w

    if not by_ann:
        print("No events in selected window")
        return

    max_harm_per_ann = max(by_ann.values()) if by_ann else 0.0
    total_norm = clamp01(total / (max_harm_per_ann * max(1, len(by_ann)))) if max_harm_per_ann > 0 else 0.0

    if args.normalize:
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
