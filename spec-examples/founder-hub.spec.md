# Project

Founder Hub is a community platform that helps founders help each other.

// Alternative names: Founders Union; Safe Space [for Founders]

# Use Cases

- connect with other founders in your area
- get reviews/feedback from other founders on providers and services (accounting, legal, SaaS, consultants, banks, etc)
    - conditions and pricing
    - other aspects
- get feedback on working with specific investors
- get intros to providers, experts, VCs and angels
- get feedback on pitch decks, blurbs, etc
- get feedback on term sheets and other financing conditions
- (possibly later) follow other founders' uncensored journey and (hopefully) validate their experiences

## Important considerations / Principles

- motivations to contribute
    - respond to a live request from a fellow founder
    - vent frustration at a problematic provider / partner
    - share joy/excitement
- optional anonymity
    - negative feedback on working with specific investors
    - sharing the details of one's terms sheets etc
- time saver YET keeping in touch
    - it's important to lower the barrier to asking for help and helping out
    - it's equally important to build and maintain trust through personal contributions, goodwill, open and sincere communication
- stages
    - accommodate early-stage founders and especially pre-incorporation founders 
        - balance this with "no random stragers": make sure people in this group are serious
    - preferably relevant on all stages but saves founders from what they consider irrelevant
- quality over quantity
    - the platform essentially vouches for every founder present
        - admitting someone others don't consider their own or thier requests annoying/unserious = waste the platform's social capital
    - always show real names and faces
    - vetted participation (no random srangers): everyone knows that every person in the community has been manually verified

# User stories

## A Founder asks for a recommendation

- Founder enters her request
  - Basic version
    - The request gets published in the requests feed
    - Others can comment
      - Recommendations capture necessary data for making intros
  - Advaced version
    - Similar requests are retrieved from the index
        - relevant answers are summaried 
        - summaries are presented as comments under the request

### Founder requests an intro with the recommended person/service

- The requesting Founder can pick the one who offered the intro
- The Founder who offered the intro (Introducer) gets notified
  - offer an auto-generated intro letter
    - use Introducer's custom intro generator prompt if available
    - use the standard intro intro generator prompt if not available
  - if configured, offer to send the intro email on the Introducer's behalf

## A Founder joins Founder Hub

- application form
  - name, email, linkedin
  - company details, website, deck, etc
  - stage: pre-incorporation, pre-money, VC-backed (pre-seed, seed, Series A-D, etc), exited (acquisition, IPO), shut down
- vetting
  - approval 
    - 3 community gatekeepers approve the candidate 
    - application is accepted
  - request more information
    - a community gatekeeper formulates a question
    - the candidate receives a form to fill in (can attach files)


# Future Features

- different hubs for locaions
  - + a global hub for all locations?
