class Condition {
  constructor(name, start_time, severity) {
    this.name = name;
    this.start_time = start_time;
    this.severity = severity;
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

    for (let i = 0; i < number_conditions; i++) {
      const severity = Math.floor(Math.random() * 5) + 1;
      const startTime = Math.floor(Math.random() * 11); // 0–10 seconds
      this.conditions.push(new Condition(`Condition ${i + 1}`, startTime, severity));
    }
  }

  getConditionsToShow(currentTime) {
    return this.conditions.filter(c => c.start_time <= currentTime && !c.shown);
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

  allResolved() {
    return this.conditions.every(c => c.resolved);
  }

  toString() {
    return this.conditions.map((c, i) => 
      `Condition ${i + 1} | Severity: ${c.severity} | Resolved: ${c.resolved} | Time: ${c.getResolutionTimeInSeconds().toFixed(2)}s`
    ).join('\\n') + `\\nTotal Score: ${this.calculateScore(Date.now()).toFixed(2)}`;
  }
}
