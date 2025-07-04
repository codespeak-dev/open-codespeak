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
        <div class="header">
            <div class="file-info">
                <span><strong>File:</strong> ${logFilePath}</span>
                <span><strong>Size:</strong> ${fileStats ? fileStats.fileSizeBytes.toLocaleString() : 'N/A'} bytes</span>
                <span><strong>Records:</strong> ${fileStats ? fileStats.totalRecords.toLocaleString() : 'N/A'}</span>
            </div>
        </div>
        <div class="filter-section">
            <div class="filter-container">
                <label for="text-filter">Filter:</label>
                <input type="text" id="text-filter" placeholder="Type to filter entries. ⌘+K to focus, Esc to clear">
                <div class="header-buttons">
                    <button id="collapse-all" class="mode-toggle" onclick="collapseAll()">
                        Collapse All
                    </button>
                    <button id="mode-toggle" class="mode-toggle" onclick="toggleViewMode()">
                        <span id="mode-text">Plain</span>
                    </button>
                </div>
            </div>
            <div class="filter-info">
                <span><strong>Time Window:</strong> Last ${timeWindowMinutes} minutes</span>
                <span><strong>Records in Window:</strong> <span id="total-entries">${fileStats ? fileStats.recordsPassedCutoff.toLocaleString() : 'N/A'}</span></span>
                <span><strong>Filtered:</strong> <span id="filtered-entries">${fileStats ? fileStats.recordsPassedCutoff.toLocaleString() : 'N/A'}</span></span>
            </div>
        </div>
        <div id="log-container" class="log-table">
            ${this.generateEntries(entries)}
        </div>
    </div>
    <script>
        // State management for collapsed/expanded sections and view modes
        const STATE_KEY = 'logParserState';
        let currentMode = 'structured'; // 'structured' or 'plain'
        
        function getStoredState() {
            try {
                const stored = localStorage.getItem(STATE_KEY);
                return stored ? JSON.parse(stored) : { expandedSections: {}, scrollPosition: 0, viewMode: 'structured', filterText: '' };
            } catch (e) {
                return { expandedSections: {}, scrollPosition: 0, viewMode: 'structured', filterText: '' };
            }
        }
        
        function saveState() {
            try {
                const state = {
                    expandedSections: {},
                    scrollPosition: window.pageYOffset || document.documentElement.scrollTop,
                    viewMode: currentMode,
                    filterText: document.getElementById('text-filter')?.value || ''
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
            
            // Restore view mode
            currentMode = state.viewMode || 'structured';
            updateModeDisplay();
            applyViewMode();
            
            // Clear filter and collapse all on page refresh
            const filterInput = document.getElementById('text-filter');
            if (filterInput) {
                filterInput.value = '';
                applyFilter();
            } else {
                updateFilterCount();
            }
            
            // Collapse all sections on page refresh
            document.querySelectorAll('.children').forEach(children => {
                children.classList.add('hidden');
                const btn = children.parentElement.querySelector('.expand-btn');
                if (btn && !btn.classList.contains('no-children')) {
                    btn.textContent = '▶';
                }
            });
            
            // Reset scroll position to top
            setTimeout(() => {
                window.scrollTo(0, 0);
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
            
            // If clicking directly on expand button, handle it
            if (event.target.classList.contains('expand-btn') && !event.target.classList.contains('no-children')) {
                toggleExpand(event.target, entryId);
                return;
            }
            
            // Find the expand button and trigger toggle
            const expandBtn = event.currentTarget.querySelector('.expand-btn');
            if (expandBtn && !expandBtn.classList.contains('no-children')) {
                toggleExpand(expandBtn, entryId);
            }
        }

        function toggleViewMode() {
            currentMode = currentMode === 'structured' ? 'plain' : 'structured';
            updateModeDisplay();
            applyViewMode();
            saveState();
        }

        function updateModeDisplay() {
            const modeText = document.getElementById('mode-text');
            if (modeText) {
                modeText.textContent = currentMode === 'structured' ? 'Plain' : 'Structured';
            }
        }

        function applyViewMode() {
            const container = document.getElementById('log-container');
            const collapseBtn = document.getElementById('collapse-all');
            if (!container) return;

            if (currentMode === 'plain') {
                container.classList.add('plain-mode');
                // Disable collapse all button in plain mode
                if (collapseBtn) {
                    collapseBtn.disabled = true;
                    collapseBtn.style.opacity = '0.5';
                }
                // Create flat representation
                createPlainView();
            } else {
                container.classList.remove('plain-mode');
                // Enable collapse all button in structured mode
                if (collapseBtn) {
                    collapseBtn.disabled = false;
                    collapseBtn.style.opacity = '1';
                }
                // Restore structured view
                restoreStructuredView();
            }
        }

        function createPlainView() {
            // Store the original structured HTML for restoration
            if (!window.originalStructuredHTML) {
                window.originalStructuredHTML = document.getElementById('log-container').innerHTML;
            }

            // Collect all entries in depth-first order
            const flatEntries = [];
            
            function collectEntriesFlat(element) {
                const entries = element.children;
                for (let entry of entries) {
                    if (entry.classList.contains('log-entry')) {
                        const logRow = entry.querySelector('.log-row');
                        if (logRow) {
                            // Clone the entire entry to preserve filtering state
                            const clonedEntry = entry.cloneNode(true);
                            const clonedRow = clonedEntry.querySelector('.log-row');
                            
                            // Hide expand button in plain mode
                            const expandBtn = clonedRow.querySelector('.expand-btn');
                            if (expandBtn) {
                                expandBtn.style.display = 'none';
                            }
                            
                            // Remove click handler for plain mode
                            clonedRow.removeAttribute('onclick');
                            
                            // Remove children from cloned entry
                            const childrenDiv = clonedEntry.querySelector('.children');
                            if (childrenDiv) {
                                childrenDiv.remove();
                            }
                            
                            flatEntries.push(clonedEntry);
                        }
                        
                        // Process children
                        const children = entry.querySelector('.children');
                        if (children) {
                            collectEntriesFlat(children);
                        }
                    }
                }
            }
            
            collectEntriesFlat(document.getElementById('log-container'));
            
            // Replace container content with flat entries
            const container = document.getElementById('log-container');
            container.innerHTML = '';
            
            flatEntries.forEach(entry => {
                container.appendChild(entry);
            });
            
            // Re-apply current filter
            applyFilter();
        }

        function restoreStructuredView() {
            if (window.originalStructuredHTML) {
                document.getElementById('log-container').innerHTML = window.originalStructuredHTML;
                
                // Re-apply expand/collapse state
                const state = getStoredState();
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
                
                // Re-apply current filter
                applyFilter();
            }
        }

        function applyFilter() {
            const filterInput = document.getElementById('text-filter');
            const filterText = filterInput ? filterInput.value.toLowerCase() : '';
            
            // Get all log entries
            const allEntries = document.querySelectorAll('.log-entry');
            let visibleCount = 0;
            
            // First pass: check which entries match the filter directly
            const matchingEntries = new Set();
            allEntries.forEach(entry => {
                const logRow = entry.querySelector('.log-row');
                if (!logRow) return;
                
                // Get the original text from the copy button's data attribute
                const copyBtn = logRow.querySelector('.copy-btn');
                let originalText = '';
                
                if (copyBtn) {
                    originalText = copyBtn.getAttribute('data-original-text') || '';
                }
                
                // Check if this entry matches the filter
                const matches = !filterText || originalText.toLowerCase().includes(filterText);
                
                if (matches) {
                    matchingEntries.add(entry);
                }
            });
            
            // Second pass: determine visibility including parent entries
            allEntries.forEach(entry => {
                let shouldBeVisible = false;
                
                // Entry is visible if it matches directly
                if (matchingEntries.has(entry)) {
                    shouldBeVisible = true;
                } else {
                    // Entry is visible if any descendant matches
                    const descendants = entry.querySelectorAll('.log-entry');
                    for (const descendant of descendants) {
                        if (matchingEntries.has(descendant)) {
                            shouldBeVisible = true;
                            break;
                        }
                    }
                }
                
                if (shouldBeVisible) {
                    entry.classList.remove('filtered-hidden');
                    visibleCount++;
                } else {
                    entry.classList.add('filtered-hidden');
                }
            });
            
            // Update the filtered entries counter
            updateFilterCount(visibleCount);
            
            // Save state including filter text
            saveState();
        }

        function updateFilterCount(visibleCount) {
            const filteredCountElement = document.getElementById('filtered-entries');
            if (filteredCountElement) {
                if (visibleCount !== undefined) {
                    filteredCountElement.textContent = visibleCount.toLocaleString();
                } else {
                    // Count visible entries
                    const visibleEntries = document.querySelectorAll('.log-entry:not(.filtered-hidden)');
                    filteredCountElement.textContent = visibleEntries.length.toLocaleString();
                }
            }
        }

        function collapseAll() {
            // Find all children divs and collapse them
            document.querySelectorAll('.children').forEach(children => {
                children.classList.add('hidden');
                const btn = children.parentElement.querySelector('.expand-btn');
                if (btn && !btn.classList.contains('no-children')) {
                    btn.textContent = '▶';
                }
            });
            saveState();
        }

        
        // Save state before page unload
        window.addEventListener('beforeunload', saveState);
        
        // Restore state when page loads
        window.addEventListener('load', restoreState);
        
        // Set up filter input event listener when DOM is ready
        window.addEventListener('DOMContentLoaded', function() {
            const filterInput = document.getElementById('text-filter');
            if (filterInput) {
                filterInput.addEventListener('input', applyFilter);
            }
        });

        // Add global keyboard shortcuts
        document.addEventListener('keydown', function(event) {
            const filterInput = document.getElementById('text-filter');
            
            // Escape: clear filter
            if (event.key === 'Escape') {
                if (filterInput && filterInput.value !== '') {
                    filterInput.value = '';
                    applyFilter();
                    event.preventDefault();
                }
            }
            
            // Meta+K (Cmd+K on Mac): focus filter input
            if (event.key === 'k' && event.metaKey) {
                if (filterInput) {
                    filterInput.focus();
                    filterInput.select();
                    event.preventDefault();
                }
            }
        });
        
        // Setup Server-Sent Events for file watching
        function setupFileWatcher() {
            const eventSource = new EventSource('/events');
            
            eventSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'fileChanged') {
                        console.log('File changed, refreshing page...');
                        saveState(); // Save current state including view mode
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
      ? `<button class="expand-btn" onclick="event.stopPropagation(); toggleExpand(this, '${entry.id}')">▶</button>`
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
    
    const logLevelDisplay = entry.logLevel
      ? `<span class="log-level log-level-${entry.logLevel.toLowerCase()}">${entry.logLevel}</span>`
      : '';
    
    const loggerDisplay = entry.loggerName
      ? `<span class="logger-name">${entry.loggerName}</span>`
      : '';
    
    const children = hasChildren 
      ? `<div id="children-${entry.id}" class="children hidden">${this.generateEntries(entry.children)}</div>`
      : '';

    const rowClickHandler = hasChildren ? `onclick="handleRowClick(event, '${entry.id}')"` : '';
    const leafNodeClass = hasChildren ? '' : ' leaf-node';
    
    return `
      <div class="log-entry">
        <div class="log-row level-${Math.min(entry.level, 4)}${leafNodeClass}" ${rowClickHandler}>
          ${expandBtn}
          ${timestampDisplay}
          ${logLevelDisplay}
          ${loggerDisplay}
          <div class="log-text">${this.escapeHtml(entry.text)}</div>
          <button class="copy-btn" data-original-text="${this.escapeForDataAttribute(entry.originalText)}" onclick="copyToClipboard(this.getAttribute('data-original-text')); return false;">📋</button>
        </div>
        ${children}
      </div>
    `;
  }

  escapeHtml(text) {
    return this.parseAnsiColors(text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/\\\\n/g, '<br>')
      .replace(/\\n/g, '<br>')
      .replace(/\\t/g, '&nbsp;&nbsp;&nbsp;&nbsp;'));
  }

  parseAnsiColors(text) {
    // ANSI color codes mapping
    const colorMap = {
      '30': 'black',
      '31': 'red', 
      '32': 'green',
      '33': 'yellow',
      '34': 'blue',
      '35': 'magenta',
      '36': 'cyan',
      '37': 'white',
      '90': 'gray',
      '91': 'lightred',
      '92': 'lightgreen', 
      '93': 'lightyellow',
      '94': 'lightblue',
      '95': 'lightmagenta',
      '96': 'lightcyan',
      '97': 'lightwhite'
    };

    const cssColorMap = {
      'black': '#000000',
      'red': '#CC0000',
      'green': '#00CC00', 
      'yellow': '#CCCC00',
      'blue': '#0000CC',
      'magenta': '#CC00CC',
      'cyan': '#00CCCC',
      'white': '#CCCCCC',
      'gray': '#808080',
      'lightred': '#FF6666',
      'lightgreen': '#66FF66',
      'lightyellow': '#FFFF66', 
      'lightblue': '#6666FF',
      'lightmagenta': '#FF66FF',
      'lightcyan': '#66FFFF',
      'lightwhite': '#FFFFFF'
    };

    let result = '';
    let currentColor = null;
    let inSpan = false;
    
    // Replace literal escape sequences like \033 with actual escape character
    text = text.replace(/\\033/g, '\u001b');
    
    // Split by ANSI escape sequences
    const parts = text.split(/(\u001b\[[0-9;]*m)/);
    
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      
      if (part.match(/\u001b\[[0-9;]*m/)) {
        // This is an ANSI escape sequence
        const codes = part.match(/\u001b\[([0-9;]*)m/);
        if (codes && codes[1]) {
          const codeNumbers = codes[1].split(';');
          
          for (const code of codeNumbers) {
            if (code === '0' || code === '') {
              // Reset - close any open span
              if (inSpan) {
                result += '</span>';
                inSpan = false;
              }
              currentColor = null;
            } else if (colorMap[code]) {
              // Color code found
              if (inSpan) {
                result += '</span>';
              }
              currentColor = cssColorMap[colorMap[code]];
              result += `<span style="color: ${currentColor}">`;
              inSpan = true;
            }
          }
        }
      } else {
        // Regular text
        result += part;
      }
    }
    
    // Close any remaining open span
    if (inSpan) {
      result += '</span>';
    }
    
    return result;
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

  escapeForDataAttribute(text) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
}

module.exports = HtmlGenerator;