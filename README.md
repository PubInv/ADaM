# ADaM - Alarm Dialog Management

Here's the link to test our live site:

[https://pubinv.github.io/ADaM/](https://pubinv.github.io/ADaM/)


This is a new project that has grown out of the [General Purpose Alarm Device](https://github.com/PubInv/general-purpose-alarm-device) project
and its successor, the [Krake](https://github.com/PubInv/krake).

Our goal is to develop an algorithm or other software system for managing human attention to complex, overlapping and ambiguous alarms, such as occur
in an intensive care unit (ICU). This is related to but extends the ideas in the scientific literature called "Intelligent Alarm Systems" and 
the well-observed phemonemanon of alarm fatique.  The whole field of alarm management is complex, and we have not fully researched it.

Nonetheless, we are not aware of anyone attempting to manage the "alarm dialog", by which we mean the interplay between the alarm conditions and the human responding to them. Briefly speaking, when an alarm occurs, a human responds to it, perhaps by muting the alarm. However, when 
a crisis occurs there may be multiple alarm conditions which are coming and going. These need to be prioritized.
The fundamental goal of managing this dialog is to allow a human being to make the best decisions possible during the crisis. 

Our goals are to build a system that:
1. Records all interactions for post-hoc interaction.
2. Present the highest priority problem to the human responder.
3. Manage the de-escalation of alarm levels without allowing any needed action to be forgotten.
4. Manage new incoming alarm conditions so they are correctly presented to the responder.
5. Allow alarm muting so the responder can work without distraction but without becoming ignorant of important information.

We foresee a system that is remembering a number of alarm conditions that are evolving over time. Unlike primitive alarm condtions, these
events should be given identities so that they can be correctly dismissied without confusion.

A necessary part of this project will be psychological testing. For example, we can imagine a test regime consisting of an incoming alarm schedule.
Two different ADaMs can be compared based on how effectively they allow a human being to process the alarm responses in a test environment.

A different way of thinking about this is that ADaM does:
1. Logging
2. Anunciation Management (send alarms to mulitple annunciators)
3. Resolution Management (that is, managing Resolutions and Dismissals)
4. Process Management (that is, managing Acknowledgment and Shelving)
5. Time Managment (that is, managing the need to mutings which are of limited time, reminding the operator of open alarm conditions, managing re-alarming of particular conditions).

# Diagram

Our basic architecture. It is important to understand that every domain requires a small amount of configuraiton. It is our goal to move this from "coding" to "configuration", so that a complete, custom domain of alarms can be created with no programming.

<img width="960" height="720" alt="Adam Architecture (1)" src="https://github.com/user-attachments/assets/9c86fe4e-2568-4832-90fe-85d285ba0ca9" />

Below, find an "action sequence diagram":


<img width="960" height="720" alt="Dialog Management Action Diagram" src="https://github.com/user-attachments/assets/296977ea-4a8c-47f6-ba21-d5bd2023eb23" />

# License

All work in this Repo will be released under the fiercely open source [Public Invention Free-Culture License Guidelines](https://github.com/PubInv/PubInv-License-Guidelines).

# Volunteers

This project is just beginning. We welcome volunteers. We need scholaraly researchers, theoreticians, human-computer interaction experts, medical experts, psychologists, computer programmers, graphic artists and technical writers.

A person with the initiative to code a system in Python or preferably Javascript would be extremely valuable if they had the ability to suggest an initial theoretical approach.

# Research

We need a scholar to do some hours of research with Google Scholar to find out how much, if any, of this idea has been addressed already.

One starting point may be:

[https://github.com/PubInv/ADaM](https://github.com/PubInv/ADaM)


The search term "Intelligent Alarm System" does not appear to be exactly what we mean:

["The intelligent alarm management system", Jun Liu, Khiang Wee Lim, Weing Khuen Ho, Kay Chen Tan, Rajagopalan Srinivasan, Arthur Tay. IEEE Software, 2003.](https://www.researchgate.net/profile/Rajagopalan-Srinivasan-3/publication/3247961_The_intelligent_alarm_management_system/links/5860c85008ae329d61fcb03a/The-intelligent-alarm-management-system.pdf)

