import argparse
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


SEND_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*SEND ALARM "
    r"annunciator=(?P<ann>\S+) id=(?P<id>\S+) sev=(?P<sev>\d+)"
)

STOP_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*\[ADaM\] Stopped\b"
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
        return float((2 ** s) - 1.0)
    return float(s)


def clear_screen() -> None:
    print("\033[2J\033[H", end="")


def bar(x: float, width: int = 30) -> str:
    n = int(round(clamp01(x) * width))
    return "[" + ("#" * n) + (" " * (width - n)) + "]"


def fmt_age(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    if seconds < 0:
        return "0s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{seconds / 60.0:.1f}m"


@dataclass
class SendEvent:
    ts: float
    ann: str
    aid: str
    sev: int


class LogTail:
    """
    Incremental log reader so we do not reread the entire file every refresh.
    Keeps state of file offset and handles truncation or rotation.
    """

    def __init__(self, path: str):
        self.path = path
        self.offset = 0
        self.inode = None

    def _stat(self):
        try:
            return os.stat(self.path)
        except FileNotFoundError:
            return None

    def read_new_lines(self) -> list[str]:
        st = self._stat()
        if st is None:
            return []

        inode = getattr(st, "st_ino", None)
        size = st.st_size

        # If file rotated or replaced, reset offset
        if self.inode is None:
            self.inode = inode
        elif inode is not None and self.inode != inode:
            self.inode = inode
            self.offset = 0

        # If truncated, reset offset
        if size < self.offset:
            self.offset = 0

        lines = []
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self.offset)
            chunk = f.read()
            self.offset = f.tell()

        if chunk:
            lines = chunk.splitlines()
        return lines


def compute_time_weighted_harm(
    events: list[SendEvent],
    start_ts: float,
    end_ts: float,
    mode: str
):
    """
    Time-weighted harm per annunciator:
    harm = sum(weight(sev) * duration_shown_seconds)
    Based on SEND ALARM events as "screen switched".
    """
    by_ann = {}
    current_state = {}

    # Sort events once
    events_sorted = sorted(events, key=lambda e: e.ts)

    # Determine initial "current shown alarm" at start_ts
    for e in events_sorted:
        if e.ts <= start_ts:
            current_state[e.ann] = e

    # Build a list of "change points" within the window
    window_events = [e for e in events_sorted if start_ts < e.ts <= end_ts]

    # For each annunciator, integrate from start_ts to end_ts based on state changes
    anns = set([e.ann for e in events_sorted] + list(current_state.keys()))

    per_ann_detail = {}
    for ann in sorted(anns):
        cur = current_state.get(ann)
        t0 = start_ts
        harm = 0.0

        # Collect events for this ann in the window
        ann_changes = [e for e in window_events if e.ann == ann]

        # Integrate each segment
        for e in ann_changes:
            t1 = max(t0, min(e.ts, end_ts))
            if cur is not None and t1 > t0:
                harm += harm_weight(cur.sev, mode) * (t1 - t0)
            cur = e
            t0 = e.ts

        # Tail segment to end_ts
        if cur is not None and end_ts > t0:
            harm += harm_weight(cur.sev, mode) * (end_ts - t0)

        by_ann[ann] = harm

        # Determine current displayed at end_ts
        last_sent = None
        last_id = None
        last_sev = None

        # Find last event <= end_ts
        for e in reversed(events_sorted):
            if e.ann == ann and e.ts <= end_ts:
                last_sent = e.ts
                last_id = e.aid
                last_sev = e.sev
                break

        per_ann_detail[ann] = {
            "harm": harm,
            "last_sent": last_sent,
            "last_id": last_id,
            "last_sev": last_sev,
        }

    total = sum(by_ann.values())
    return total, per_ann_detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log", help="path to adam_server.log")
    ap.add_argument("--mode", choices=["linear", "square", "exp"], default="square")
    ap.add_argument("--window_s", type=float, default=300.0, help="time window in seconds")
    ap.add_argument("--refresh", type=float, default=1.0, help="refresh interval in seconds")
    ap.add_argument("--recent", type=int, default=10, help="show last N SEND events")
    ap.add_argument("--keep_s", type=float, default=86400.0, help="keep parsed events in memory this many seconds")
    ap.add_argument("--close_on_stop", choices=["true", "false"], default="true")
    args = ap.parse_args()

    log_path = args.log
    close_on_stop = args.close_on_stop == "true"

    tail = LogTail(log_path)

    events: list[SendEvent] = []
    last_stop_ts: Optional[float] = None
    last_send_ts: Optional[float] = None

    # Initial full read so dashboard has context immediately
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = SEND_RE.search(line)
                if m:
                    ts = parse_ts(m.group("ts"))
                    ann = m.group("ann")
                    aid = m.group("id")
                    sev = int(m.group("sev"))
                    events.append(SendEvent(ts=ts, ann=ann, aid=aid, sev=sev))
                    last_send_ts = ts if last_send_ts is None else max(last_send_ts, ts)
                    continue
                m2 = STOP_RE.search(line)
                if m2:
                    ts = parse_ts(m2.group("ts"))
                    last_stop_ts = ts if last_stop_ts is None else max(last_stop_ts, ts)
    except FileNotFoundError:
        pass

    while True:
        # Incremental updates
        for line in tail.read_new_lines():
            m = SEND_RE.search(line)
            if m:
                ts = parse_ts(m.group("ts"))
                ann = m.group("ann")
                aid = m.group("id")
                sev = int(m.group("sev"))
                events.append(SendEvent(ts=ts, ann=ann, aid=aid, sev=sev))
                last_send_ts = ts if last_send_ts is None else max(last_send_ts, ts)
                continue

            m2 = STOP_RE.search(line)
            if m2:
                ts = parse_ts(m2.group("ts"))
                last_stop_ts = ts if last_stop_ts is None else max(last_stop_ts, ts)

        now = time.time()

        # Only treat stop as active if it is after the latest SEND in the file
        effective_stop = None
        if close_on_stop and last_stop_ts is not None:
            if last_send_ts is None or last_stop_ts >= last_send_ts:
                effective_stop = last_stop_ts

        end_ts = effective_stop if effective_stop is not None else now
        start_ts = end_ts - float(args.window_s)

        # Prune old events so memory does not grow forever
        keep_from = end_ts - float(args.keep_s)
        events = [e for e in events if e.ts >= keep_from]

        total_harm, detail = compute_time_weighted_harm(
            events=events,
            start_ts=start_ts,
            end_ts=end_ts,
            mode=args.mode,
        )

        # Meaningful normalization based on worst-case constant severity 5
        worst_per_ann = harm_weight(5, args.mode) * float(args.window_s)
        anns = list(detail.keys())
        num_anns = max(1, len(anns))
        total_norm = clamp01(total_harm / (worst_per_ann * num_anns)) if worst_per_ann > 0 else 0.0

        # Recent events list
        recent_events = [e for e in events if start_ts <= e.ts <= end_ts]
        recent_events = sorted(recent_events, key=lambda e: e.ts)[-int(args.recent):]

        clear_screen()
        print("ADaM Log Dashboard (time-weighted)")
        print(f"log: {os.path.abspath(log_path)}")
        print(f"mode: {args.mode}  window: {int(args.window_s)}s  refresh: {args.refresh}s")
        print(f"time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if effective_stop is not None:
            stopped_str = datetime.fromtimestamp(effective_stop).strftime("%Y-%m-%d %H:%M:%S")
            print(f"status: STOPPED at {stopped_str}")
        else:
            print("status: RUNNING")
        print()

        print(f"TOTAL time-weighted harm: {total_harm:.1f}")
        print(f"TOTAL norm(0-1): {total_norm:.3f} {bar(total_norm)}")
        print()

        if not detail:
            print("No SEND ALARM events parsed yet")
        else:
            print("Per-annunciator (time-weighted over window)")
            rows = []
            for ann, d in detail.items():
                rows.append((ann, d["harm"], d["last_sev"], d["last_sent"], d["last_id"]))
            rows.sort(key=lambda x: -x[1])

            for ann, harm, last_sev, last_sent, last_id in rows:
                norm = clamp01(harm / worst_per_ann) if worst_per_ann > 0 else 0.0
                age = (end_ts - last_sent) if last_sent is not None else None
                sev_str = str(last_sev) if last_sev is not None else "-"
                id_str = last_id if last_id is not None else "-"
                print(f"{ann:30s} harm={harm:9.1f} norm={norm:.3f} {bar(norm)}  sev={sev_str}  last_send_age={fmt_age(age)}  id={id_str}")

        print()
        print("Recent SEND ALARM events (in window):")
        if not recent_events:
            print("  (none)")
        else:
            for e in recent_events:
                tstr = datetime.fromtimestamp(e.ts).strftime("%H:%M:%S")
                print(f"  {tstr}  sev={e.sev}  {e.ann}  id={e.aid}")

        print()
        print("Ctrl+C to exit")

        try:
            time.sleep(args.refresh)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
