# Project

Lumama is a platform where users can post their events, browse existing events, invite others to their events, RSVP to the invitations, and curate attendee lists.

# User Stories

## All users

- log in
- sign up (enter email + password, no email confirmation required, can log in straight away after sign up)

## Organiser

- browse the list of their events (past and future)
- create/edit event
//  - make public (discoverable) or private (invite-only)
//  - make open (anyone can join), or curated (approval required), or invite-only
//  - recurring vs one-off events
//  - make attendees visible / hidden
//  - capped attendee counts + optional waitlists
- share event link (make sure it's not practical to guess event links by trying out sequential numbers)
//  - customisable by the organiser
//- invite attendees
- see attendee lists
// - curate attendee lists / waitlists
// - delete/cancel event
//  - restore deleted event
//- ban an attendee from future events
//- post updates about the event
//  - send out email blasts to attendees
//- invite attendees of a given event to another event (with an optional custom message)
//- take donations / payments for attending an event
//- fill in profile: name, email, linkedin, description, etc

## Attendee

- View event
//  - Browse attendee lists
  - See who the organiser is
- RSVP to an invite link
//  - attendee gets an email confirmation with a calendar event attached
//- Browse all public events
//  - subscribe to updates / attend / join waitlist
//- Receive notifications/email blasts
//- Cancel RSVP / take themselves off a wait list
//- Pay / donate for an event
//- Browse all of their events
//- Fill in profile: name, email, linkedin, contacts, etc
//- Post to the event's wall
//- Follow an organiser (receive notifications of their future events)

//## Admin
//
//- audit all activity 
//  - every action chronologically
//  - filters by user, by type of activity, by date, by affected users, by free text
//- edit / delete all data

# Web App Structure

## Every user can be an attendee and/or an organiser
- both capabilities are accessible in the UI
- attendee UI is likely to be used by more people so it requires fewer clicks from the front page
- if the user is not signed in, all they see is attendee UI and all actions requiring sign in lead to a quick sign-in form
  - they also see an "organise event" call to action which triggers sign-in and then shows organiser UI

## Attendee UI entry points
- event link
  - shows event
  - RSVP requires sign-in
//- home screen
//  - events I'm attending
//    - updates / organiser messages in my events
//  - my invitations (when the signed-in user was personally invited to an event)
//  - event browser with public events
//    - newest first
//    - recommendation system TBD in a future version
//  - profile
//  - events I organise (switches to organiser UI)

## Organiser UI Home screen
- events I'm organising
- create new event
- events I'm attending (switches to attendee UI)

# Design

Have a only minimal layout for sign in/ signup, and a default (home) layout.

## Technology

Use Tailwindcss and connect it from CDN.

# Modules

- Server
  - Data
  - Signup/Signin
  - Email
- Client
  - Organiser
  - Attendee