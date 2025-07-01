# home page
- when not signed in, user must to login or register
- when signed in, user can create event, open dashboard, see invites, logout (does not pass)

# all pages header
- create event opens Create New Event page
- dashboard link opens dashboard page

# dashboard
- includes header user stories
- shows active events
    - paginated list works (does not pass)
    - status filter works (does not pass)
    - text search works (does not pass)
    - for each event, properties are displayed correctly: 
      - name
      - dates
      - location
      - number of attendees
      - sold tickets
    - tooltips?
    - for each event, links work:
      - click on event name opens manage
      - edit
      - manage
      - view attendees
      - share
      - public view
      - delete (does not pass)

# create event page
- basic field validation (non-empty fields, dates) performed on the client
- convenient pickers are provided
- date / location pickers work
- unsaved data warning on navigation / cancel
- server-side validations are performed
- event id is generated randomly
- cancel does not create an event, redirects to main page

# edit event page
- when opening for non-existing or inaccessible event id, graceful "not found or access denied" page is shown
- when opening for valid event id, event properties are shown
- allows to delete event
- same checks as for create event page

# manage (view?) event page
- when opening for non-existing or inaccessible event id, graceful "not found or access denied" page is shown
- when opening for valid event id, event properties are shown
  - title
  - description
  - location
  - dates
  - number of attendees
  - statistics
- if user is logged in and is the organizer, buttons work (for this event id!)
  - edit event
  - view attendees
  - share event
  - view public page
- if user is logged in and not the organizer, buttons work (for this event id):
  - accept invitation
  - decline invitation

# view event attendees page
- when opening for non-existing or inaccessible event id, graceful "not found or access denied" page is shown
- event attributes are shown
- counts are shown (accepted, pending, declined)
  - response rate is correct (for multiple cases)
- paginated list works
- list filter works (does not pass)
- for each attendee, properties are shown
  - name
  - email 
  - status
  - RSVP date

# share event page
- when opening for non-existing or inaccessible event id, graceful "not found or access denied" page is shown
- event attributes are shown
- Public Event Page URL can be copied
- Direct RSVP Link URL can be copied
- share on social media buttons have correct redirect URL (with public event link)
  - FB
  - X
  - LI
  - email

# public event page
- when opening for non-existing or inaccessible event id, graceful "not found or access denied" page is shown
- if user is not signed in, event attributes are shown
- if user is signed in, redirects

# RSVP page
- requires sign in
- when opening for non-existing or inaccessible event id, graceful "not found or access denied" page is shown
- when shown for the organizer, redirects to manage event page
- when shown not for the organizer, allows to accept or decline + add custom message
- cancel redirects to event page

# my invitations page
- shows total counts
- where's no invitations, shows placeholder
- paginated list works
- filter by name and status works
- allows to click on each invitation

