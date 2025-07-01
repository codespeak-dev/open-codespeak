# sign-in enforcement
- direct access to all private pages is forbidden, redirecting to sign-in page

# home page
- when not signed in, user must sign in or register

# create account / register page
- user can enter all the fields: name, email and password
- UTF8 is supported where applicable
- basic checks are performed (empty fields, email format etc.)
- duplicate email is not allowed (server-side check)
- basic checks are done on the client: passwords don't match, password too short, password too simple (does not pass)
- when successful, redirect to login page (does not pass)

# sign in
- missing email is not disclosed
- wrong email/password combination does not work
- ban / captcha after multiple failed sign in attempts

# manage account page
- change name / avatar
- change password
- 2FA
- change email?
- add notification channels (email / SMS)
- activity log, active sessions (for security)

# all HTML pages
- proper title
- header shows user name
    - activates sign-in enforcement
    - redirects to the front page
- logout button works
- back/forward work (SPA: hash-based routing, history API)
- no extra elements on the page (does not pass)
- only one button for a task
- common UX practices (ex: keyboard navigation)
- HTML / CSS / JS best practices
- accessibility: impaired vision, alts, read loud etc.
- light/dark mode
- cookie popup
- background refresh for readonly pages (AJAX)

# common cross-platform / browser support
- mobile browser
- tablet browser
- chromium / firefox / safari / IE / reader mode

# infra / integrations
- captcha
- CDN for static content
- identity platform (ex: auth0 / clerk)
- DDOS shielding / rate limiting / firewall / acceleration (ex: cloudflare)
- email provider
  - verify email address
- verify SMS
- domain name
- DNS provider
- SSL certificate
- cloud hosting (ex: AWS, heroku and successors)
- availability, traffic and resource monitoring (ex: Grafana), alerting (ex: PagerDuty)
- out-of-the-box uptime monitoring (ex: Pingdom, UptimeRobot)
- client-side error tracking and performance monitoring (ex: Sentry)
- database hosting and backups
- website analytics (ex: Google tag manager / matomo / metrika)
- server logs centralization (ELK)
- email configuration (SPF / DKIM / DMARC)
- REST API conformance / best practices (GraphQL?)
- robots.txt
- favicon
- SMS providers (for custom notifications)
- payment providers (ex: Stripe)
- LLM agent friendly :)

# security best practices
- session id cookie: Secure, HttpOnly
- run vulnerability scanner on all pages (before and after sign-in)
- shows "last login" message on login
- store salted hashed passwords