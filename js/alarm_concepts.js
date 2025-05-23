// TODO:
// Tie resolution of specific condtions to buttons randomly.
// Create more buttons than conditions.
// Randomly create start times and present condtion as time
// elapses.
// Add severity to condtions. (scale 1-5) (5 is most severe).
// 1 Information
// 2 Warn
// 3 Problem
// 4 Critical
// 5 Panic
// Score should reflect severity ( s**2);
// Add to score penalty for pressing wrong button.
// Show score of Trial at the end.

// LATER:
// Create different annunciation strategies.


function test_alarm_concepts() {
    alert("hello world!");
    console.log("hello world!");
}


class Condition {
    constructor(name, start_time) {
        // start_time is measured in seconds from the
        // beginning of the trial
        // name is an identifier
        this.name = name;
    this.start_time = start_time;
  }

  // record the resolution time.
  resolve() {
      console.log(`Condition ${this.name} resolved!`);
  }
    toString() {
        return `${this.name} : ${this.start_time}`;
    }
};

class Trial {
    constructor(name,number_conditions) {
        // start_time is measured in seconds from the
        // beginning of the trial
        // name is an identifier
        this.name = name;
        this.number_conditions = number_conditions;
        this.conditions = [];
        for(var i = 0; i < this.number_conditions; i++) {
            this.conditions.push(new Condition("name_"+i,0));
            console.log(i,this.conditions[i]);
        }
    }
    toString() {
        let retval = "";
        for(var i = 0; i < this.number_conditions; i++) {
            console.log(conditions[i]);
            retval += conditions[i];
        }
        return `${this.name} : ${this.start_time}`;
    }
    // return the score of this trial..
    score() {
        // penalize for each condition for as long as it lasts.
        return 37;
    }
};
