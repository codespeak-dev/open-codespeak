const express = require('express');
const chokidar = require('chokidar');
const path = require('path');
const LogParser = require('./logParser');
const HtmlGenerator = require('./htmlGenerator');

class LogParserServer {
  constructor(port = 3000, timeWindowMinutes = 60) {
    this.port = port;
    this.timeWindowMinutes = timeWindowMinutes;
    this.app = express();
    this.logParser = new LogParser(timeWindowMinutes);
    this.htmlGenerator = new HtmlGenerator();
    this.logFilePath = null;
    this.cachedHtml = null;
    this.lastModified = null;
    this.sseClients = new Set();
    
    this.setupRoutes();
  }

  setupRoutes() {
    this.app.use(express.static(__dirname));
    
    this.app.get('/', async (req, res) => {
      if (!this.logFilePath) {
        res.send(`
          <html>
            <head><title>Log Parser</title></head>
            <body>
              <h1>Log Parser Server</h1>
              <p>No log file specified. Start server with: node server.js &lt;log-file-path&gt;</p>
            </body>
          </html>
        `);
        return;
      }

      let entries, fileStats;
      try {
        const result = await this.logParser.parseLogFileWithStats(this.logFilePath);
        entries = result.entries;
        fileStats = result.stats;
        console.log("Parsed " + entries.length + " entries from log file " + this.logFilePath);
      } catch (parseError) {
        console.error('Error parsing log file:', parseError);
        res.status(500).send('Error parsing log file');
        return;
      }

      try {
        const html = this.htmlGenerator.generateHtml(entries, this.logFilePath, this.timeWindowMinutes, fileStats);
        res.send(html);
      } catch (htmlError) {
        console.error('Error generating HTML:', htmlError);
        res.status(500).send('Error generating HTML');
      }
    });

    this.app.get('/style.css', (req, res) => {
      res.sendFile(path.join(__dirname, 'style.css'));
    });

    // Server-Sent Events endpoint for file changes
    this.app.get('/events', (req, res) => {
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Cache-Control'
      });

      // Keep connection alive
      const keepAlive = setInterval(() => {
        res.write('data: {"type": "ping"}\n\n');
      }, 30000);

      // Add client to set
      const client = { res, keepAlive };
      this.sseClients.add(client);

      // Clean up on disconnect
      req.on('close', () => {
        clearInterval(keepAlive);
        this.sseClients.delete(client);
      });
    });
  }

  watchLogFile(filePath) {
    if (this.watcher) {
      this.watcher.close();
    }

    this.watcher = chokidar.watch(filePath);
    this.watcher.on('change', () => {
      console.log(`Log file changed: ${filePath}`);
      this.cachedHtml = null;
      this.notifyClients();
    });

    this.watcher.on('error', (error) => {
      console.error('Watcher error:', error);
    });
  }

  notifyClients() {
    const message = JSON.stringify({ type: 'fileChanged', timestamp: Date.now() });
    
    this.sseClients.forEach(client => {
      try {
        client.res.write(`data: ${message}\n\n`);
      } catch (error) {
        console.error('Error sending SSE message:', error);
        this.sseClients.delete(client);
      }
    });
  }

  start(logFilePath) {
    this.logFilePath = logFilePath;
    
    if (logFilePath) {
      this.watchLogFile(logFilePath);
      console.log(`Watching log file: ${logFilePath}`);
    }

    this.app.listen(this.port, () => {
      console.log(`Log parser server running on http://localhost:${this.port}`);
      console.log(`Time window: ${this.timeWindowMinutes} minutes`);
    });
  }
}

// Command line usage
if (require.main === module) {
  const args = process.argv.slice(2);
  const logFilePath = args[0];
  const port = args[1] ? parseInt(args[1]) : 3000;
  const timeWindowMinutes = args[2] ? parseInt(args[2]) : 60;

  if (!logFilePath) {
    console.log('Usage: node server.js <log-file-path> [port] [time-window-minutes]');
    console.log('Example: node server.js /var/log/app.log 3000 60');
    process.exit(1);
  }

  const server = new LogParserServer(port, timeWindowMinutes);
  server.start(logFilePath);
}

module.exports = LogParserServer;