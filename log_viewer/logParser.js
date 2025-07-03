const fs = require('fs');
const readline = require('readline');
const crypto = require('crypto');

class LogParser {
  constructor(timeWindowMinutes = 60) {
    this.entries = [];
    this.timeWindowMinutes = timeWindowMinutes;
    this.timestampRegex = /(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)/;
  }

  async parseLogFile(filePath) {
    try {
      const cutoffTime = new Date(Date.now() - this.timeWindowMinutes * 60 * 1000);
      const recentLines = await this.readRecentLines(filePath, cutoffTime);
      return this.parseContent(recentLines);
    } catch (error) {
      console.error(`Error reading log file: ${error.message}`);
      return [];
    }
  }

  async parseLogFileWithStats(filePath) {
    try {
      const cutoffTime = new Date(Date.now() - this.timeWindowMinutes * 60 * 1000);
      const result = await this.readRecentLinesWithStats(filePath, cutoffTime);
      const entries = this.parseContent(result.recentLines);
      
      return {
        entries: entries,
        stats: {
          fileSizeBytes: result.fileSizeBytes,
          totalRecords: result.totalRecords,
          recordsPassedCutoff: result.recentLines.length
        }
      };
    } catch (error) {
      console.error(`Error reading log file: ${error.message}`);
      return {
        entries: [],
        stats: {
          fileSizeBytes: 0,
          totalRecords: 0,
          recordsPassedCutoff: 0
        }
      };
    }
  }

  async readRecentLines(filePath, cutoffTime) {
    const fileStream = fs.createReadStream(filePath);
    const rl = readline.createInterface({
      input: fileStream,
      crlfDelay: Infinity
    });

    const recentLines = [];
    
    for await (const line of rl) {
      if (line.trim() === '') continue;

      const timestamp = this.extractTimestamp(line);
      if (timestamp && timestamp >= cutoffTime) {
        recentLines.push(line);
      }
      else {
        console.debug("Skipping line " + line + " with timestamp " + timestamp + " before curoff time " + cutoffTime);
      }
    }

    return recentLines;
  }

  async readRecentLinesWithStats(filePath, cutoffTime) {
    const stats = await fs.promises.stat(filePath);
    const fileStream = fs.createReadStream(filePath);
    const rl = readline.createInterface({
      input: fileStream,
      crlfDelay: Infinity
    });

    const recentLines = [];
    let totalRecords = 0;
    
    for await (const line of rl) {
      if (line.trim() === '') continue;
      
      totalRecords++;
      const timestamp = this.extractTimestamp(line);
      if (timestamp && timestamp >= cutoffTime) {
        recentLines.push(line);
      }
    }

    return {
      recentLines: recentLines,
      fileSizeBytes: stats.size,
      totalRecords: totalRecords
    };
  }

  extractTimestamp(line) {
    const match = line.match(this.timestampRegex);
    return match ? new Date(match[1]) : null;
  }

  removeTimestamp(text) {
    return text.replace(this.timestampRegex, '').trim();
  }

  parseContent(lines) {
    const entries = [];
    const stack = [];

    for (const line of lines) {
      const level = this.getIndentLevel(line);
      const text = line.substring(level).trim();

      if (text === '') continue;

      const timestamp = this.extractTimestamp(text);
      const textWithoutTimestamp = this.removeTimestamp(text);
      const entry = {
        text: textWithoutTimestamp,
        originalText: text,
        level: level,
        children: [],
        timestamp: timestamp,
        id: this.generateStableId(text, timestamp)
      };

      while (stack.length > 0 && stack[stack.length - 1].level >= level) {
        stack.pop();
      }

      if (stack.length === 0) {
        entries.push(entry);
      } else {
        stack[stack.length - 1].children.push(entry);
      }

      stack.push(entry);
    }

    return entries;
  }

  getIndentLevel(line) {
    let level = 0;
    for (let i = 0; i < line.length; i++) {
      if (line[i] === '\t') {
        level++;
      } else {
        break;
      }
    }
    return level;
  }

  generateStableId(text, timestamp) {
    // Create a stable ID based on the full line content using SHA-256
    return crypto.createHash('sha256').update(text).digest('hex').substring(0, 12);
  }
}

module.exports = LogParser;