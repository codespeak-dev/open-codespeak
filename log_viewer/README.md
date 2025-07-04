# Log viewer

# Installation

1. Install node.js: https://nodejs.org/en/download

# Launch (from project folder)

`node log_viewer/server.js <path_to_file.log> [port] [time window, min]`

E.g.: `node log_viewer/server.js test_outputs/19_todoapp/codespeak.log`

Default port: 3000
Default time window: 60 min

# Usage hits:
- 2 modes: plain, structured
- collapse all
- copy original message to clipboard
- filter messages