// alarm_concepts.js
// === Notes-based Fatigue Model (slowed, no recovery) ===
// f starts at 0; no recovery during trial
// f_{t+1} = clamp01( f_t + (dt / T) * sum_active( (s/5)^p ) )

const T_SECONDS = 240;  // normalization (bigger = slower fatigue growth)
const P_SEVERITY = 2;   // severity exponent: square on normalized severity
const DT_SECONDS = 1;   // discrete tick (seconds)
const SEV_MAX = 5;      // max severity for normalization

class Condition {
  constructor(name, start_time, severity) {
    this.name = name;
    this.start_time = start_time; // seconds from trial start when it appears
    this.severity = severity;     // integer 1..5
    this.shown = false;
    this.resolved = false;
    this.startShownTime = null;
    this.endResolvedTime = null;

    // Work tracking to support operator preemption (pause/resume)
    this._workRemainingSec = null; // number | null
    this._workInitialSec   = null; // number | null
  }

  resolve() {
    this.resolved = true;
    this.endResolvedTime = Date.now();
    console.log(`✅ Resolved: ${this.name}`);
  }

  getResolutionTimeInSeconds() {
    if (this.startShownTime && this.endResolvedTime) {
      return (this.endResolvedTime - this.startShownTime) / 1000;
    }
    return 1;
  }
}

class Trial {
  constructor(name, number_conditions) {
    this.name = name;
    this.conditions = [];
    this.fatigue = 0; // f in [0,1]
    for (let i = 0; i < number_conditions; i++) {
      const severity = Math.floor(Math.random() * 5) + 1; // 1..5
      const startTime = Math.floor(Math.random() * 11);   // 0..10s
      this.conditions.push(new Condition(`Condition ${i + 1}`, startTime, severity));
    }
  }

  // Show those whose start_time has arrived (and not yet shown)
  getConditionsToShow(currentTimeSeconds) {
    return this.conditions.filter(c => c.start_time <= currentTimeSeconds && !c.shown);
  }

  allResolved() {
    return this.conditions.every(c => c.resolved);
  }

  calculateScore() {
    let totalScore = 0;
    for (const c of this.conditions) {
      if (c.resolved && c.startShownTime && c.endResolvedTime) {
        const time = (c.endResolvedTime - c.startShownTime) / 1000;
        totalScore += (c.severity ** 3) / time;
      }
    }
    return totalScore;
  }

  // === Notes-based fatigue integral (no recovery) ===
  calculateFatigue(nowMs, dtSec = DT_SECONDS) {
    // Only alarms the operator is "aware of": shown & unresolved
    const active = this.conditions.filter(c => c.shown && !c.resolved);

    // Sum normalized severity weights: (s/SEV_MAX)^p
    let sumW = 0;
    for (const c of active) {
      const sNorm = c.severity / SEV_MAX;          // 0..1
      sumW += Math.pow(sNorm, P_SEVERITY);         // (s/5)^p
    }

    // Integral step
    this.fatigue += (dtSec / T_SECONDS) * sumW;

    // Clamp to [0,1]
    this.fatigue = Math.max(0, Math.min(1, this.fatigue));
    return this.fatigue;
  }

  // Linear mappings per notes:
  // A(0)=0.9, A(f)=0.9*(1-f); S(0)=1, S(f)=1*(1-f)
  accuracy()   { return 0.9 * (1 - this.fatigue); }
  speedFactor(){ return (1 - this.fatigue); }

  // Generic performance scaler (linear with f)
  adjustPerformance(base) { return base * (1 - this.fatigue); }

  resetFatigue() { this.fatigue = 0; }
}

/* =======================
   Profiles (operator behavior)
   ======================= */
class UserProfile {
  constructor({
    name,
    baseTaskTimeSec = 2,
    taskTimeJitterSec = 3,
    // Task Strategy: how the human chooses/behaves on shown alarms
    // "highestSeverity" | "earliestShown" | "preemptOnHigherSeverity"
    taskStrategy = "highestSeverity",
    // Only used by preempt strategy (0..1). If progress < threshold and a higher
    // severity alarm is visible, operator will preempt the current task.
    preemptThreshold = 0.8
  }) {
    this.name = name;
    this.baseTaskTimeSec = baseTaskTimeSec;
    this.taskTimeJitterSec = taskTimeJitterSec;
    this.taskStrategy = taskStrategy;
    this.preemptThreshold = preemptThreshold;
  }
}

/* ========= PRESENTATION POLICIES =========
   Policies control WHAT is visible to the operator at any second.
   - "showAll"                      -> show all alarms immediately on arrival
   - "singleHighest"                -> show at most one active; don't switch mid-task
   - "singleHighestNonInterrupting" -> alias of singleHighest (clarifies intent)
   - "severityEscalation"           -> interrupt current if a higher-severity arrives
*/
function presentAccordingToPolicy(trial, wallClockSec, presentationPolicy, t0ms) {
  // helpers: set shown/hidden with first-show semantics
  function show(c) {
    if (!c.shown) {
      c.shown = true;
      if (c.startShownTime == null) {
        c.startShownTime = t0ms + wallClockSec * 1000;
      }
    }
  }
  function hide(c) { c.shown = false; }

  // 1) showAll — reveal everything that has arrived
  if (presentationPolicy === "showAll") {
    for (const c of trial.conditions) {
      if (!c.shown && !c.resolved && c.start_time <= wallClockSec) show(c);
    }
    return;
  }

  // alias maps to non-interrupting behavior
  if (presentationPolicy === "singleHighestNonInterrupting") {
    presentationPolicy = "singleHighest";
  }

  // 2) singleHighest — keep current until resolved; else pick highest arrived
  if (presentationPolicy === "singleHighest") {
    const shownActive = trial.conditions.filter(c => c.shown && !c.resolved);
    if (shownActive.length > 0) return; // keep current visible one

    const outstanding = trial.conditions
      .filter(c => !c.resolved && c.start_time <= wallClockSec && !c.shown)
      .sort((a, b) => b.severity - a.severity || a.start_time - b.start_time);

    if (outstanding.length > 0) show(outstanding[0]);
    return;
  }

  // 3) severityEscalation — if higher-severity arrives, switch immediately
  if (presentationPolicy === "severityEscalation") {
    const shownActive = trial.conditions.filter(c => c.shown && !c.resolved);
    const current = shownActive[0] || null;

    const arrived = trial.conditions.filter(c => !c.resolved && c.start_time <= wallClockSec);
    const highestArrived = arrived
      .slice()
      .sort((a, b) => b.severity - a.severity || a.start_time - b.start_time)[0];

    if (!current) { if (highestArrived) show(highestArrived); return; }

    if (highestArrived) {
      if (highestArrived.severity > current.severity) { hide(current); show(highestArrived); return; }
      return; // equal severity → avoid churn
    }
    return;
  }

  // Fallback: behave like non-interrupting singleHighest
  const shownActive = trial.conditions.filter(c => c.shown && !c.resolved);
  if (shownActive.length > 0) return;
  const outstanding = trial.conditions
    .filter(c => !c.resolved && c.start_time <= wallClockSec && !c.shown)
    .sort((a, b) => b.severity - a.severity || a.start_time - b.start_time);
  if (outstanding.length > 0) show(outstanding[0]);
}

/* ======== Simulation (policy vs policy) with harm, and operator preemption ======== */

// choose which active alarm to work on among SHOWN & UNRESOLVED (non-preempt chooser)
function pickNextAlarm(trial, taskStrategy) {
  const active = trial.conditions.filter(c => c.shown && !c.resolved);
  if (active.length === 0) return null;
  if (taskStrategy === "earliestShown") {
    return active.slice().sort((a,b) => (a.startShownTime||Infinity) - (b.startShownTime||Infinity))[0];
  }
  // default: highestSeverity (ties by earliest shown)
  return active.slice().sort((a,b) => b.severity - a.severity || (a.startShownTime||0) - (b.startShownTime||0))[0];
}

// One simulated trial for a given user profile and presentation policy.
function simulateTrialForUser(
  userProfile,
  {
    name = "mc",
    number_conditions = 6,
    horizonArrivalSec = 10,
    T_for_notes = T_SECONDS,
    presentationPolicy = "showAll"
  } = {}
) {
  // Build a Trial with random severities/start times
  const trial = new Trial(name, number_conditions);
  for (const c of trial.conditions) {
    c.start_time = Math.floor(Math.random() * (horizonArrivalSec + 1));
  }

  const t0 = Date.now();
  let wallClockSec = 0;
  let actionsTaken = 0;
  let accuracyAccum = 0;
  let speedFactorAccum = 0;
  let totalHarm = 0;

  // Helper: highest shown unresolved (for preemption decision)
  function highestShownUnresolved() {
    const shown = trial.conditions.filter(c => c.shown && !c.resolved);
    if (shown.length === 0) return null;
    return shown.slice().sort((a,b) => b.severity - a.severity || (a.startShownTime||0) - (b.startShownTime||0))[0];
  }

  while (!trial.allResolved()) {
    // Ensure visibility first per policy
    presentAccordingToPolicy(trial, wallClockSec, presentationPolicy, t0);

    // Choose a target among shown & unresolved
    let target = pickNextAlarm(trial, userProfile.taskStrategy);

    if (target) {
      // Initialize effective work if new or resumed
      if (target._workRemainingSec == null) {
        const jitter = Math.random() * userProfile.taskTimeJitterSec;
        const nominalTask = userProfile.baseTaskTimeSec + jitter;
        const speedFactorAtStart = trial.speedFactor();
        const effectiveTaskTime = Math.max(0.5, nominalTask / Math.max(0.1, speedFactorAtStart));
        target._workRemainingSec = Math.ceil(effectiveTaskTime);
        target._workInitialSec   = target._workRemainingSec;
      }

      // Work second-by-second to allow mid-task preemption
      while (target && target._workRemainingSec > 0) {
        // 1) integrate fatigue & advance time
        trial.calculateFatigue(t0 + wallClockSec * 1000, 1);
        wallClockSec += 1;

        // 2) update presentation (new arrivals may change what's shown)
        presentAccordingToPolicy(trial, wallClockSec, presentationPolicy, t0);

        // 3) operator preemption logic
        if (userProfile.taskStrategy === "preemptOnHigherSeverity") {
          const topShown = highestShownUnresolved();
          if (topShown && topShown !== target && topShown.severity > target.severity) {
            const progressFrac = 1 - (target._workRemainingSec / Math.max(1, target._workInitialSec));
            if (progressFrac < userProfile.preemptThreshold) {
              // switch target; keep remaining time on previous task
              target = topShown;
              if (target._workRemainingSec == null) {
                const jitter = Math.random() * userProfile.taskTimeJitterSec;
                const nominalTask = userProfile.baseTaskTimeSec + jitter;
                const speedFactorAtSwitch = trial.speedFactor();
                const effectiveTaskTime = Math.max(0.5, nominalTask / Math.max(0.1, speedFactorAtSwitch));
                target._workRemainingSec = Math.ceil(effectiveTaskTime);
                target._workInitialSec   = target._workRemainingSec;
              }
              continue; // continue loop with new target
            }
          }
        }

        // 4) Do one second of work on current target
        target._workRemainingSec -= 1;

        // Safety to avoid infinite sim
        if (wallClockSec > 3600) break;
      }

      // If finished, resolve and tally metrics
      if (target && target._workRemainingSec <= 0) {
        target.resolve();
        target.endResolvedTime = t0 + wallClockSec * 1000;

        actionsTaken += 1;
        accuracyAccum += trial.accuracy();
        speedFactorAccum += trial.speedFactor();

        const durationSec = Math.max(0, wallClockSec - target.start_time);
        totalHarm += durationSec * (target.severity ** 2);

        // clear work trackers
        target._workRemainingSec = null;
        target._workInitialSec = null;
      }
    } else {
      // Idle second
      trial.calculateFatigue(t0 + wallClockSec * 1000, 1);
      wallClockSec += 1;
      presentAccordingToPolicy(trial, wallClockSec, presentationPolicy, t0);
    }

    if (wallClockSec > 3600) break; // 1 hour cap
  }

  const avgAccuracy = actionsTaken ? (accuracyAccum / actionsTaken) : 0.9;
  const avgSpeedFactor = actionsTaken ? (speedFactorAccum / actionsTaken) : 1.0;

  return {
    user: userProfile.name,
    totalTimeSec: wallClockSec,
    finalFatigue: trial.fatigue,
    avgAccuracy,
    avgSpeedFactor,
    resolved: actionsTaken,
    totalHarm
  };
}

// Policy-vs-policy Monte Carlo with summaries
function runMonteCarloPolicies({
  N = 500,
  operator = new UserProfile({ name: "op", baseTaskTimeSec: 2.5, taskTimeJitterSec: 2, taskStrategy: "highestSeverity" }),
  trialParams = { number_conditions: 6, horizonArrivalSec: 10, T_for_notes: T_SECONDS },
  policies = ["singleHighest", "showAll"]
} = {}) {
  const out = {};
  for (const pol of policies) {
    const samples = [];
    for (let i = 0; i < N; i++) {
      samples.push(
        simulateTrialForUser(operator, { ...trialParams, presentationPolicy: pol })
      );
    }

    function summarize(arr) {
      const mean = (k) => arr.reduce((s, r) => s + r[k], 0) / arr.length;
      const sorted = (k) => arr.map(r => r[k]).sort((a,b)=>a-b);
      const pct = (vals, q) => vals[Math.floor(q*(vals.length-1))];

      const t = sorted("totalTimeSec");
      const f = sorted("finalFatigue");
      const a = sorted("avgAccuracy");
      const h = sorted("totalHarm");

      return {
        count: arr.length,
        meanTime: mean("totalTimeSec"),
        p50Time: pct(t, 0.5), p90Time: pct(t, 0.9),
        meanFatigue: mean("finalFatigue"),
        p50Fatigue: pct(f, 0.5), p90Fatigue: pct(f, 0.9),
        meanAccuracy: mean("avgAccuracy"),
        p50Acc: pct(a, 0.5), p90Acc: pct(a, 0.9),
        meanHarm: mean("totalHarm"),
        p50Harm: pct(h, 0.5), p90Harm: pct(h, 0.9),
        samples: arr
      };
    }

    out[pol] = { summary: summarize(samples), samples };
  }
  return out;
}

/* ======== Legacy compatibility helpers (optional) ======== */

// Original people-vs-people MC (unchanged)
function simulateTrialForUser_original(userProfile, {
  name = "mc",
  number_conditions = 6,
  horizonArrivalSec = 10,
  T_for_notes = T_SECONDS
} = {}) {
  const trial = new Trial(name, number_conditions);
  for (const c of trial.conditions) {
    c.start_time = Math.floor(Math.random() * (horizonArrivalSec + 1));
  }

  const t0 = Date.now();
  let wallClockSec = 0;
  let actionsTaken = 0;
  let accuracyAccum = 0;
  let speedFactorAccum = 0;

  while (!trial.allResolved()) {
    // Show newly arrived alarms
    for (const c of trial.conditions) {
      if (!c.shown && c.start_time <= wallClockSec) {
        c.shown = true;
        c.startShownTime = t0 + wallClockSec * 1000;
      }
    }

    const active = trial.conditions.filter(c => c.shown && !c.resolved);
    let target = null;
    if (userProfile.taskStrategy === "earliestShown") {
      target = active.slice().sort((a,b) => (a.startShownTime||Infinity) - (b.startShownTime||Infinity))[0];
    } else {
      target = active.slice().sort((a,b) => b.severity - a.severity || (a.startShownTime||0) - (b.startShownTime||0))[0];
    }

    if (target) {
      const jitter = Math.random() * userProfile.taskTimeJitterSec;
      const nominalTask = userProfile.baseTaskTimeSec + jitter;
      const speedFactor = trial.speedFactor(); // 1 - f
      const effectiveTaskTime = Math.max(0.5, nominalTask / Math.max(0.1, speedFactor));

      const steps = Math.ceil(effectiveTaskTime);
      for (let i = 0; i < steps; i++) {
        trial.calculateFatigue(t0 + wallClockSec * 1000, 1);
        wallClockSec += 1;
        for (const c of trial.conditions) {
          if (!c.shown && c.start_time <= wallClockSec) {
            c.shown = true;
            c.startShownTime = t0 + wallClockSec * 1000;
          }
        }
      }

      target.resolve();
      target.endResolvedTime = t0 + wallClockSec * 1000;

      actionsTaken += 1;
      accuracyAccum += trial.accuracy();
      speedFactorAccum += trial.speedFactor();
    } else {
      trial.calculateFatigue(t0 + wallClockSec * 1000, 1);
      wallClockSec += 1;
    }

    if (wallClockSec > 3600) break;
  }

  const avgAccuracy = actionsTaken ? (accuracyAccum / actionsTaken) : 0.9;
  const avgSpeedFactor = actionsTaken ? (speedFactorAccum / actionsTaken) : 1.0;

  return {
    user: userProfile.name,
    totalTimeSec: wallClockSec,
    finalFatigue: trial.fatigue,
    avgAccuracy,
    avgSpeedFactor,
    resolved: actionsTaken
  };
}

// Back-compat alias so existing HTML that calls runMonteCarloStrategies keeps working
function runMonteCarloStrategies({
  N = 500,
  operator = new UserProfile({ name: "op", baseTaskTimeSec: 2.5, taskTimeJitterSec: 2, taskStrategy: "highestSeverity" }),
  trialParams = { number_conditions: 6, horizonArrivalSec: 10, T_for_notes: T_SECONDS },
  strategies = ["singleHighest", "showAll"] // same values; just a naming alias
} = {}) {
  // Delegate to policies version for compatibility
  return runMonteCarloPolicies({
    N,
    operator,
    trialParams,
    policies: strategies
  });
}

// Expose to window for UI scripts
if (typeof window !== 'undefined') {
  window.UserProfile = UserProfile;
  window.runMonteCarlo = simulateTrialForUser_original;   // legacy people-vs-people
  window.simulateTrialForUser = simulateTrialForUser;     // policy-aware + preemption
  window.runMonteCarloPolicies = runMonteCarloPolicies;   // new name
  window.runMonteCarloStrategies = runMonteCarloStrategies; // alias (for existing index.html)
  window.Trial = Trial;
  window.Condition = Condition;
  window.presentAccordingToPolicy = presentAccordingToPolicy;
}
