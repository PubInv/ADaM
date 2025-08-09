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

  // Linear mappings per your notes:
  // A(0)=0.9, A(f)=0.9*(1-f); S(0)=1, S(f)=1*(1-f)
  accuracy() { return 0.9 * (1 - this.fatigue); }
  speedFactor() { return (1 - this.fatigue); }

  // Generic performance scaler (linear with f)
  adjustPerformance(base) {
    return base * (1 - this.fatigue);
  }

  resetFatigue() { this.fatigue = 0; }
}

/* =======================
   Monte Carlo Simulation
   ======================= */

// Profiles define behavior & timing
class UserProfile {
  constructor({ name, baseTaskTimeSec = 2, taskTimeJitterSec = 3, policy = "highestSeverity" }) {
    this.name = name;
    this.baseTaskTimeSec = baseTaskTimeSec;
    this.taskTimeJitterSec = taskTimeJitterSec;
    this.policy = policy; // "highestSeverity" | "earliestShown"
  }
}

// Choose which active alarm to work on
function pickNextAlarm(trial, policy) {
  const active = trial.conditions.filter(c => c.shown && !c.resolved);
  if (active.length === 0) return null;

  if (policy === "highestSeverity") {
    // break ties by earliest shown time
    return active
      .slice()
      .sort((a, b) => b.severity - a.severity || (a.startShownTime || 0) - (b.startShownTime || 0))[0];
  }
  // default: earliest shown (FIFO)
  return active
    .slice()
    .sort((a, b) => (a.startShownTime || Infinity) - (b.startShownTime || Infinity))[0];
}

// One simulated trial for a given user profile.
function simulateTrialForUser(userProfile, {
  name = "mc",
  number_conditions = 6,
  horizonArrivalSec = 10,   // conditions arrive in [0..10] seconds
  T_for_notes = T_SECONDS   // keep consistent with fatigue model
} = {}) {
  // Build a Trial with random severities/start times
  const trial = new Trial(name, number_conditions);

  // Overwrite start_time uniformly in [0..horizonArrivalSec] for control
  for (const c of trial.conditions) {
    c.start_time = Math.floor(Math.random() * (horizonArrivalSec + 1));
  }

  const t0 = Date.now();   // base ms
  let wallClockSec = 0;    // simulated seconds since trial start
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

    const target = pickNextAlarm(trial, userProfile.policy);
    if (target) {
      // Decide task time for this action (base + uniform jitter)
      const jitter = Math.random() * userProfile.taskTimeJitterSec;
      const nominalTask = userProfile.baseTaskTimeSec + jitter;   // seconds
      // Speed factor at the moment work starts
      const speedFactor = trial.speedFactor(); // 1 - f
      const effectiveTaskTime = Math.max(0.5, nominalTask / Math.max(0.1, speedFactor));

      // Integrate fatigue second-by-second during task
      const steps = Math.ceil(effectiveTaskTime);
      for (let i = 0; i < steps; i++) {
        trial.calculateFatigue(t0 + wallClockSec * 1000, 1);
        wallClockSec += 1;

        // New arrivals during task
        for (const c of trial.conditions) {
          if (!c.shown && c.start_time <= wallClockSec) {
            c.shown = true;
            c.startShownTime = t0 + wallClockSec * 1000;
          }
        }
      }

      // Resolve chosen alarm
      target.resolve();
      target.endResolvedTime = t0 + wallClockSec * 1000;

      // Aggregate metrics for this action
      actionsTaken += 1;
      accuracyAccum += trial.accuracy();       // A(f) = 0.9*(1-f)
      speedFactorAccum += trial.speedFactor(); // S(f) = 1 - f
    } else {
      // Idle—advance time (fatigue won't increase without active alarms)
      trial.calculateFatigue(t0 + wallClockSec * 1000, 1);
      wallClockSec += 1;
    }

    // Safety cap
    if (wallClockSec > 3600) break; // 1 hour
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

// Run N trials for two users and aggregate
function runMonteCarlo({
  N = 500,
  userA = new UserProfile({ name: "A", baseTaskTimeSec: 2, taskTimeJitterSec: 3, policy: "highestSeverity" }),
  userB = new UserProfile({ name: "B", baseTaskTimeSec: 3, taskTimeJitterSec: 1, policy: "earliestShown" }),
  trialParams = { number_conditions: 6, horizonArrivalSec: 10, T_for_notes: T_SECONDS }
} = {}) {
  const resultsA = [];
  const resultsB = [];

  for (let i = 0; i < N; i++) {
    resultsA.push(simulateTrialForUser(userA, trialParams));
    resultsB.push(simulateTrialForUser(userB, trialParams));
  }

  function summarize(arr) {
    const mean = (key) => arr.reduce((s, r) => s + r[key], 0) / arr.length;
    const by = (key) => arr.map(r => r[key]).sort((a,b)=>a-b);
    const p = (vals, q) => vals[Math.floor(q * (vals.length-1))];
    const t = by('totalTimeSec'), f = by('finalFatigue'), a = by('avgAccuracy');

    return {
      count: arr.length,
      meanTime: mean('totalTimeSec'),
      meanFatigue: mean('finalFatigue'),
      meanAccuracy: mean('avgAccuracy'),
      p50Time: p(t, 0.5), p90Time: p(t, 0.9),
      p50Fatigue: p(f, 0.5), p90Fatigue: p(f, 0.9),
      p50Acc: p(a, 0.5),    p90Acc: p(a, 0.9),
    };
  }

  return {
    userA: { profile: userA, summary: summarize(resultsA), samples: resultsA },
    userB: { profile: userB, summary: summarize(resultsB), samples: resultsB }
  };
}

// Expose to window for UI scripts
if (typeof window !== 'undefined') {
  window.UserProfile = UserProfile;
  window.runMonteCarlo = runMonteCarlo;
  window.simulateTrialForUser = simulateTrialForUser;
  window.Trial = Trial;
  window.Condition = Condition;
}
