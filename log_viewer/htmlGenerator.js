class HtmlGenerator {
  generateHtml(entries, logFilePath, timeWindowMinutes, fileStats) {
    const html = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Log Parser - ${logFilePath}</title>
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <div class="container">
        <table class="info-table">
            <tr>
                <td>File:</td>
                <td>${logFilePath}</td>
            </tr>
            <tr>
                <td>File Size:</td>
                <td>${fileStats ? fileStats.fileSizeBytes.toLocaleString() : 'N/A'} bytes</td>
            </tr>
            <tr>
                <td>Total Records:</td>
                <td>${fileStats ? fileStats.totalRecords.toLocaleString() : 'N/A'}</td>
            </tr>
            <tr>
                <td>Records in Time Window:</td>
                <td>${fileStats ? fileStats.recordsPassedCutoff.toLocaleString() : 'N/A'}</td>
            </tr>
            <tr>
                <td>Time Window:</td>
                <td>Last ${timeWindowMinutes} minutes</td>
            </tr>
        </table>
        <div class="log-table">
            ${this.generateEntries(entries)}
        </div>
    </div>
    <script>
        // State management for collapsed/expanded sections
        const STATE_KEY = 'logParserState';
        
        function getStoredState() {
            try {
                const stored = localStorage.getItem(STATE_KEY);
                return stored ? JSON.parse(stored) : { expandedSections: {}, scrollPosition: 0 };
            } catch (e) {
                return { expandedSections: {}, scrollPosition: 0 };
            }
        }
        
        function saveState() {
            try {
                const state = {
                    expandedSections: {},
                    scrollPosition: window.pageYOffset || document.documentElement.scrollTop
                };
                
                // Save expanded state of all sections
                document.querySelectorAll('.children').forEach(el => {
                    const entryId = el.id.replace('children-', '');
                    state.expandedSections[entryId] = !el.classList.contains('hidden');
                });
                
                localStorage.setItem(STATE_KEY, JSON.stringify(state));
            } catch (e) {
                console.warn('Failed to save state:', e);
            }
        }
        
        function restoreState() {
            const state = getStoredState();
            
            // Restore expanded sections
            Object.entries(state.expandedSections).forEach(([entryId, isExpanded]) => {
                const children = document.getElementById('children-' + entryId);
                const btn = children ? children.parentElement.querySelector('.expand-btn') : null;
                
                if (children && btn) {
                    if (isExpanded) {
                        children.classList.remove('hidden');
                        btn.textContent = '▼';
                    } else {
                        children.classList.add('hidden');
                        btn.textContent = '▶';
                    }
                }
            });
            
            // Restore scroll position
            setTimeout(() => {
                window.scrollTo(0, state.scrollPosition);
            }, 100);
        }
        
        function toggleExpand(btn, entryId) {
            const children = document.getElementById('children-' + entryId);
            if (children.classList.contains('hidden')) {
                children.classList.remove('hidden');
                btn.textContent = '▼';
            } else {
                children.classList.add('hidden');
                btn.textContent = '▶';
            }
            saveState();
        }

        function copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(() => {
                console.log('Copied to clipboard');
            }).catch(err => {
                console.error('Failed to copy to clipboard:', err);
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = text;
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
            });
        }

        function handleRowClick(event, entryId) {
            // Don't toggle if clicking on the copy button
            if (event.target.classList.contains('copy-btn')) {
                return;
            }
            
            // Find the expand button and trigger toggle
            const expandBtn = event.currentTarget.querySelector('.expand-btn');
            if (expandBtn && !expandBtn.classList.contains('no-children')) {
                toggleExpand(expandBtn, entryId);
            }
        }
        
        // Save state before page unload
        window.addEventListener('beforeunload', saveState);
        
        // Restore state when page loads
        window.addEventListener('load', restoreState);
        
        // Setup Server-Sent Events for file watching
        function setupFileWatcher() {
            const eventSource = new EventSource('/events');
            
            eventSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'fileChanged') {
                        console.log('File changed, refreshing page...');
                        saveState();
                        location.reload();
                    }
                } catch (e) {
                    console.warn('Error parsing SSE message:', e);
                }
            };
            
            eventSource.onerror = function(error) {
                console.error('SSE error:', error);
                // Retry connection after 5 seconds
                setTimeout(setupFileWatcher, 5000);
            };
        }
        
        // Start file watching
        setupFileWatcher();
    </script>
</body>
</html>`;
    return html;
  }

  generateEntries(entries) {
    return entries.map(entry => this.generateEntry(entry)).join('');
  }

  generateEntry(entry) {
    const hasChildren = entry.children && entry.children.length > 0;
    const expandBtn = hasChildren 
      ? `<button class="expand-btn" onclick="toggleExpand(this, '${entry.id}')">▶</button>`
      : `<button class="expand-btn no-children">•</button>`;
    
    const timestampDisplay = entry.timestamp 
      ? `<span class="timestamp">${entry.timestamp.toLocaleString([], {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
          timeZoneName: 'short'
        })}</span>`
      : '';
    
    const children = hasChildren 
      ? `<div id="children-${entry.id}" class="children hidden">${this.generateEntries(entry.children)}</div>`
      : '';

    const rowClickHandler = hasChildren ? `onclick="handleRowClick(event, '${entry.id}')"` : '';
    
    return `
      <div class="log-entry">
        <div class="log-row level-${Math.min(entry.level, 4)}" ${rowClickHandler}>
          ${expandBtn}
          ${timestampDisplay}
          <div class="log-text">${this.escapeHtml(entry.text)}</div>
          <button class="copy-btn" onclick="copyToClipboard('${this.escapeForJs(entry.originalText)}')" title="Copy to clipboard">📋</button>
        </div>
        ${children}
      </div>
    `;
  }

  escapeHtml(text) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  escapeForJs(text) {
    return text
      .replace(/\\/g, '\\\\')
      .replace(/'/g, "\\'")
      .replace(/"/g, '\\"')
      .replace(/\n/g, '\\n')
      .replace(/\r/g, '\\r')
      .replace(/\t/g, '\\t');
  }
}

module.exports = HtmlGenerator;