
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
