# Project

Preemp helps you track long-runnning tasks AI or similar tools are working on in the background. While one task is being handled by an agent, you can switch to describing another.

# User Stories

## Task Lists Overview

Shows two lists of task card (similar to the cards on agile boards). 
One list has the tasks agents are working on, another — the tasks the user is working on.
When an agent completes a task it is moved to the user's list with an unread indicator, i.e. that it has not been opened after copmletion.

- each task card shows
  - task name
  - a preview of its content
  - a status indicator in the form of an icon

- if a human is working on a task
  - it shows an icon for "user"

- if an agent is working on a task, it shows
  - a progress indicator 
  - a short summary of the surrent activity by the agent
  - a spinner showing work-in-progress as its icon

- if a task is unread after being completed by an agent
  - it shows a completion indicator (green checkmark) as its icon

### Reorder task cards for prioritisation

The user can drag cards up and down both lists.

## Create or Edit a task

### Send a task to the agents