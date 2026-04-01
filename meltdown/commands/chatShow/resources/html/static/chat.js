(function() {
    'use strict';

    var messagesContainer = document.getElementById('messages');
    var typingIndicator = document.getElementById('typing-indicator');
    var userInput = document.getElementById('user-input');
    var uploadBtn = document.getElementById('upload-btn');
    var fileInput = document.getElementById('file-input');
    var imagePreview = document.getElementById('image-preview');
    var previewImg = document.getElementById('preview-img');
    var removeImageBtn = document.getElementById('remove-image');
    var autocompleteDropdown = document.getElementById('autocomplete-dropdown');
    var slashDropdown = document.getElementById('slash-dropdown');
    var configOverlay = document.getElementById('config-overlay');
    var configBack = document.getElementById('config-back');
    var configSave = document.getElementById('config-save');
    var configCancel = document.getElementById('config-cancel');

    // History overlay DOM references
    var historyOverlay = document.getElementById('history-overlay');
    var historyBack = document.getElementById('history-back');
    var historyList = document.getElementById('history-list');
    var historyEmpty = document.getElementById('history-empty');

    // Debug panel DOM references
    var debugPanel = document.getElementById('debug-panel');
    var debugHandle = document.getElementById('debug-handle');
    var debugLogEntries = document.getElementById('debug-log-entries');
    var debugScrollBtn = document.getElementById('debug-scroll-btn');
    var debugClearBtn = document.getElementById('debug-clear-btn');
    var debugCloseBtn = document.getElementById('debug-close-btn');

    // Track the current AI bubble for streaming narration
    var currentAIBubble = null;

    // Image state
    var pendingImage = null;  // base64 data URI of attached image

    // Debug panel state
    var LOG_MAX = 500;     // Ring buffer size (D-11)
    var logEntryCount = 0; // Track entries for ring buffer
    var debugAutoScroll = true;  // Auto-scroll state (DBUG-04)
    var currentFilterLevel = 'DEBUG';  // Default filter level -- matches "ALL" button (D-10)

    // Autocomplete state
    var designCache = null;  // Cached design names from Python
    var selectedAcIndex = -1;  // Currently selected autocomplete item index

    // Slash command state (separate from autocomplete per Research Pitfall 1)
    var slashCommands = null;  // Cached command list from Python
    var selectedSlashIndex = -1;  // Currently selected slash menu item

    // ******** Send messages to Python via Fusion bridge ********

    function sendMessage(text) {
        if (!text.trim() && !pendingImage) return;

        // Show user message in UI (except commands)
        if (!text.startsWith('/')) {
            appendUserMessage(text.trim(), pendingImage);
        }

        var payload = { text: text.trim() };
        if (pendingImage) {
            payload.image = pendingImage;
        }
        adsk.fusionSendData('user_message', JSON.stringify(payload));

        // Clear pending image after send
        clearPendingImage();
    }

    // ******** Receive messages from Python via fusionJavaScriptHandler ********

    window.fusionJavaScriptHandler = {
        handle: function(action, data) {
            try {
                var parsed = JSON.parse(data);
                switch (action) {
                    case 'narration':
                        handleNarration(parsed.text);
                        break;
                    case 'agent_response':
                        handleAgentResponse(parsed.text);
                        break;
                    case 'typing_indicator':
                        showTypingIndicator(parsed.show);
                        break;
                    case 'restore_history':
                        restoreHistory(parsed.messages);
                        break;
                    case 'clear_chat':
                        clearAllMessages();
                        break;
                    case 'system_message':
                        appendMessage('system', parsed.text);
                        break;
                    case 'design_names':
                        designCache = parsed;
                        checkAutocomplete();  // Retry with cached data
                        break;
                    case 'file_dialog_result':
                        if (parsed.image) {
                            setPendingImage(parsed.image);
                        }
                        break;
                    case 'command_list':
                        slashCommands = parsed.commands;
                        checkSlashMenu();  // Retry with cached data
                        break;
                    case 'show_config':
                        showConfigOverlay();
                        break;
                    case 'settings_data':
                        populateConfig(parsed);
                        break;
                    case 'settings_saved':
                        hideConfigOverlay();
                        appendMessage('system', 'Settings saved.');
                        break;
                    case 'tool_call_start':
                        handleToolCallStart(parsed);
                        break;
                    case 'tool_call_end':
                        handleToolCallEnd(parsed);
                        break;
                    case 'debug_log':
                        handleDebugLog(parsed);
                        break;
                    case 'toggle_debug':
                        toggleDebugPanel();
                        break;
                    case 'show_history':
                        showHistoryOverlay();
                        break;
                    case 'hide_history':
                        hideHistoryOverlay();
                        break;
                    case 'session_list':
                        renderSessionList(parsed.sessions);
                        break;
                }
            } catch (e) {
                console.log('Handler error:', e);
            }
            return 'OK';
        }
    };

    // ******** Message rendering ********

    function appendMessage(role, text) {
        var div = document.createElement('div');
        div.className = 'message ' + role;
        div.textContent = text;
        messagesContainer.appendChild(div);
        scrollToBottom();
    }

    function appendUserMessage(text, imageDataUri) {
        var div = document.createElement('div');
        div.className = 'message user';
        if (text) {
            var textNode = document.createElement('span');
            textNode.textContent = text;
            div.appendChild(textNode);
        }
        if (imageDataUri) {
            var img = document.createElement('img');
            img.className = 'msg-image';
            img.src = imageDataUri;
            img.alt = 'Reference image';
            div.appendChild(img);
        }
        messagesContainer.appendChild(div);
        scrollToBottom();
    }

    function handleNarration(text) {
        // Hide typing indicator on first narration
        showTypingIndicator(false);

        // Append to current AI bubble, or create one
        if (!currentAIBubble) {
            currentAIBubble = document.createElement('div');
            currentAIBubble.className = 'message assistant';
            messagesContainer.appendChild(currentAIBubble);
        }

        // Append narration as a div element (preserves sibling tool cards)
        var textDiv = document.createElement('div');
        textDiv.className = 'narration-text';
        textDiv.textContent = text;
        currentAIBubble.appendChild(textDiv);
        scrollToBottom();
    }

    function handleAgentResponse(text) {
        // Hide typing indicator
        showTypingIndicator(false);

        if (currentAIBubble) {
            // Finalize: append response as div element (preserves tool cards)
            var textDiv = document.createElement('div');
            textDiv.className = 'narration-text agent-response';
            textDiv.textContent = text;
            currentAIBubble.appendChild(textDiv);
        } else {
            // No narration preceded this -- create fresh bubble
            appendMessage('assistant', text);
        }

        // Reset streaming state
        currentAIBubble = null;
        designCache = null;  // Invalidate so next autocomplete refreshes
        scrollToBottom();
    }

    function showTypingIndicator(show) {
        typingIndicator.style.display = show ? 'block' : 'none';
        if (show) scrollToBottom();
    }

    function restoreHistory(messages) {
        // Clear current UI first
        messagesContainer.innerHTML = '';
        currentAIBubble = null;

        // Render each historical message (text-only, no tool cards in history)
        if (messages && messages.length > 0) {
            messages.forEach(function(msg) {
                appendMessage(msg.role, msg.text);
            });
        }
        scrollToBottom();
    }

    function clearAllMessages() {
        messagesContainer.innerHTML = '';
        currentAIBubble = null;
    }

    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // ******** Tool card rendering (TOOL-01, TOOL-02, TOOL-03, TOOL-04) ********

    function handleToolCallStart(data) {
        // Ensure an AI bubble exists for tool cards
        if (!currentAIBubble) {
            currentAIBubble = document.createElement('div');
            currentAIBubble.className = 'message assistant';
            messagesContainer.appendChild(currentAIBubble);
        }

        var card = document.createElement('div');
        card.className = 'tool-card running';
        card.id = 'tc-' + data.call_id;
        card.dataset.args = data.args || '{}';
        card.innerHTML = '<span class="tool-icon">&#x23F3;</span>'
            + '<span class="tool-name">' + escapeHtml(data.tool_name) + '</span>';
        currentAIBubble.appendChild(card);
        scrollToBottom();
    }

    function handleToolCallEnd(data) {
        var card = document.getElementById('tc-' + data.call_id);
        if (!card) return;

        // Update status class (removes 'running', adds 'success' or 'error')
        card.className = 'tool-card ' + data.status;

        // Store result or error data for expand/collapse
        if (data.status === 'success') {
            card.dataset.result = data.result || '';
        } else {
            card.dataset.error = data.error || '';
            card.dataset.errorType = data.error_type || 'Error';
        }

        // Update icon: checkmark for success, X for error (D-03, D-04)
        var iconEl = card.querySelector('.tool-icon');
        if (iconEl) {
            iconEl.innerHTML = data.status === 'success' ? '&#x2705;' : '&#x274C;';
        }

        // Add duration span (TOOL-03)
        var dur = document.createElement('span');
        dur.className = 'tool-duration';
        dur.textContent = data.duration + 's';
        card.appendChild(dur);

        // Enable click-to-expand (D-05, TOOL-02)
        card.addEventListener('click', function(e) {
            // Prevent toggle when clicking links inside details
            if (e.target.closest('.tool-card-details')) return;
            toggleToolExpand(this);
        });

        scrollToBottom();
    }

    function toggleToolExpand(card) {
        // If already expanded, collapse
        var existing = card.querySelector('.tool-card-details');
        if (existing) {
            card.removeChild(existing);
            return;
        }

        // Build expanded details (D-05, D-06)
        var details = document.createElement('div');
        details.className = 'tool-card-details';

        // Parameters section
        var argsStr = card.dataset.args || '{}';
        try {
            var argsObj = JSON.parse(argsStr);
            if (typeof argsObj === 'object' && argsObj !== null) {
                var paramSection = document.createElement('div');
                paramSection.className = 'tool-detail-section';
                var paramLabel = document.createElement('div');
                paramLabel.className = 'tool-detail-label';
                paramLabel.textContent = 'Parameters';
                paramSection.appendChild(paramLabel);

                var paramContent = document.createElement('div');
                paramContent.className = 'tool-detail-content';
                var keys = Object.keys(argsObj);
                for (var i = 0; i < keys.length; i++) {
                    var paramDiv = document.createElement('div');
                    paramDiv.className = 'tool-param';
                    var keySpan = document.createElement('span');
                    keySpan.className = 'tool-param-key';
                    keySpan.textContent = keys[i] + ':';
                    var valSpan = document.createElement('span');
                    valSpan.className = 'tool-param-value';
                    var val = argsObj[keys[i]];
                    valSpan.textContent = ' ' + (typeof val === 'object' ? JSON.stringify(val) : String(val));
                    paramDiv.appendChild(keySpan);
                    paramDiv.appendChild(valSpan);
                    paramContent.appendChild(paramDiv);
                }
                paramSection.appendChild(paramContent);
                details.appendChild(paramSection);
            }
        } catch (e) {
            // Args not parseable as JSON, show raw
            var rawSection = document.createElement('div');
            rawSection.className = 'tool-detail-section';
            var rawLabel = document.createElement('div');
            rawLabel.className = 'tool-detail-label';
            rawLabel.textContent = 'Parameters';
            rawSection.appendChild(rawLabel);
            var rawContent = document.createElement('div');
            rawContent.className = 'tool-detail-content';
            rawContent.textContent = argsStr;
            rawSection.appendChild(rawContent);
            details.appendChild(rawSection);
        }

        // Result or Error section
        if (card.dataset.error) {
            var errSection = document.createElement('div');
            errSection.className = 'tool-detail-section';
            var errLabel = document.createElement('div');
            errLabel.className = 'tool-detail-label';
            errLabel.textContent = 'Error';
            errSection.appendChild(errLabel);
            var errContent = document.createElement('div');
            errContent.className = 'tool-detail-content tool-detail-error';
            errContent.textContent = (card.dataset.errorType || 'Error') + ': ' + card.dataset.error;
            errSection.appendChild(errContent);
            details.appendChild(errSection);
        } else if (card.dataset.result) {
            var resSection = document.createElement('div');
            resSection.className = 'tool-detail-section';
            var resLabel = document.createElement('div');
            resLabel.className = 'tool-detail-label';
            resLabel.textContent = 'Result';
            resSection.appendChild(resLabel);
            var resContent = document.createElement('div');
            resContent.className = 'tool-detail-content';
            resContent.textContent = card.dataset.result;
            resSection.appendChild(resContent);
            details.appendChild(resSection);
        }

        card.appendChild(details);
        scrollToBottom();
    }

    // ******** Debug panel (DBUG-01, DBUG-02, DBUG-03, DBUG-04, D-07, D-08, D-10, D-11) ********

    function toggleDebugPanel() {
        var isVisible = debugPanel.classList.toggle('visible');
        debugHandle.classList.toggle('visible');
        if (isVisible) {
            debugLogEntries.className = 'filter-' + currentFilterLevel;
            debugAutoScroll = true;
            debugScrollBtn.classList.remove('visible');
        }
    }

    function handleDebugLog(data) {
        // Enforce ring buffer: remove oldest if at capacity (D-11)
        if (logEntryCount >= LOG_MAX) {
            if (debugLogEntries.firstChild) {
                debugLogEntries.removeChild(debugLogEntries.firstChild);
            }
            logEntryCount--;
        }

        var entry = document.createElement('div');
        entry.className = 'log-entry level-' + data.level;

        var ts = document.createElement('span');
        ts.className = 'log-ts';
        ts.textContent = data.timestamp ? data.timestamp.substring(11, 23) : '';

        var level = document.createElement('span');
        level.className = 'log-level';
        level.textContent = data.level;

        var src = document.createElement('span');
        src.className = 'log-src';
        src.textContent = '[' + data.source + ']';

        var msg = document.createElement('span');
        msg.className = 'log-msg';
        msg.textContent = data.message;

        entry.appendChild(ts);
        entry.appendChild(level);
        entry.appendChild(src);
        entry.appendChild(msg);
        debugLogEntries.appendChild(entry);
        logEntryCount++;

        // Auto-scroll to bottom if active (DBUG-04)
        if (debugAutoScroll) {
            debugLogEntries.scrollTop = debugLogEntries.scrollHeight;
        }
    }

    // Filter button click handlers (DBUG-03)
    var filterBtns = document.querySelectorAll('.debug-filter-btn');
    for (var fi = 0; fi < filterBtns.length; fi++) {
        filterBtns[fi].addEventListener('click', function() {
            for (var fj = 0; fj < filterBtns.length; fj++) {
                filterBtns[fj].classList.remove('active');
            }
            this.classList.add('active');
            currentFilterLevel = this.getAttribute('data-level');
            debugLogEntries.className = 'filter-' + currentFilterLevel;
        });
    }

    // Auto-scroll detection (DBUG-04)
    debugLogEntries.addEventListener('scroll', function() {
        var atBottom = this.scrollTop + this.clientHeight >= this.scrollHeight - 20;
        debugAutoScroll = atBottom;
        debugScrollBtn.classList.toggle('visible', !atBottom);
    });

    // Scroll-to-bottom button handler
    debugScrollBtn.addEventListener('click', function() {
        debugLogEntries.scrollTop = debugLogEntries.scrollHeight;
        debugAutoScroll = true;
        this.classList.remove('visible');
    });

    // Clear button handler (D-11)
    debugClearBtn.addEventListener('click', function() {
        debugLogEntries.innerHTML = '';
        logEntryCount = 0;
    });

    // Close button handler -- hides debug panel
    debugCloseBtn.addEventListener('click', function() {
        toggleDebugPanel();
    });

    // Drag handle for resizing (D-07)
    var isDragging = false;
    debugHandle.addEventListener('mousedown', function(e) {
        isDragging = true;
        debugHandle.classList.add('dragging');
        document.addEventListener('mousemove', onDragMove);
        document.addEventListener('mouseup', onDragEnd);
        e.preventDefault();
    });

    function onDragMove(e) {
        if (!isDragging) return;
        var bodyHeight = document.body.clientHeight;
        var newPanelHeight = bodyHeight - e.clientY;
        newPanelHeight = Math.max(80, Math.min(newPanelHeight, bodyHeight - 100));
        debugPanel.style.height = newPanelHeight + 'px';
    }

    function onDragEnd() {
        isDragging = false;
        debugHandle.classList.remove('dragging');
        document.removeEventListener('mousemove', onDragMove);
        document.removeEventListener('mouseup', onDragEnd);
    }

    // ******** Image upload handling (D-07, D-08, D-09, D-12) ********

    // File picker (D-07)
    uploadBtn.addEventListener('click', function() {
        fileInput.click();
    });

    fileInput.addEventListener('change', function(e) {
        var file = e.target.files[0];
        if (!file) return;
        if (!file.type.match(/^image\/(png|jpe?g|webp)$/)) {
            appendMessage('system', 'Unsupported image format. Use PNG, JPG, or WebP.');
            fileInput.value = '';
            return;
        }
        // Must match config.MAX_IMAGE_SIZE_BYTES (10MB)
        if (file.size > 10 * 1024 * 1024) {
            appendMessage('system', 'Image too large (>10MB). Please use a smaller image.');
            fileInput.value = '';
            return;
        }
        var reader = new FileReader();
        reader.onload = function(ev) {
            setPendingImage(ev.target.result);
        };
        reader.readAsDataURL(file);
        fileInput.value = '';  // Reset so same file can be re-selected
    });

    // Clipboard paste (D-08)
    document.addEventListener('paste', function(e) {
        var items = e.clipboardData && e.clipboardData.items;
        if (!items) return;
        for (var i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                e.preventDefault();
                var blob = items[i].getAsFile();
                // Must match config.MAX_IMAGE_SIZE_BYTES (10MB)
                if (blob.size > 10 * 1024 * 1024) {
                    appendMessage('system', 'Pasted image too large (>10MB).');
                    return;
                }
                var reader = new FileReader();
                reader.onload = function(ev) {
                    setPendingImage(ev.target.result);
                };
                reader.readAsDataURL(blob);
                break;  // One image per message (D-09)
            }
        }
    });

    function setPendingImage(dataUri) {
        pendingImage = dataUri;
        previewImg.src = dataUri;
        imagePreview.style.display = 'block';
        userInput.focus();
    }

    function clearPendingImage() {
        pendingImage = null;
        previewImg.src = '';
        imagePreview.style.display = 'none';
    }

    removeImageBtn.addEventListener('click', function() {
        clearPendingImage();
        userInput.focus();
    });

    // ******** Autocomplete logic (D-18, D-19, D-20) ********

    var acDebounceTimer = null;

    function checkAutocomplete() {
        var text = userInput.value;
        var cursorPos = userInput.selectionStart;
        var beforeCursor = text.substring(0, cursorPos);
        var atMatch = beforeCursor.match(/@(\w*)$/);

        if (atMatch) {
            var query = atMatch[1].toLowerCase();
            if (!designCache) {
                // Request design state from Python (one-time, cached)
                adsk.fusionSendData('get_design_names', '{}');
                return;
            }
            showAutocomplete(query);
        } else {
            hideAutocomplete();
        }
    }

    function showAutocomplete(query) {
        var items = buildSuggestions(query);
        if (items.length === 0) {
            hideAutocomplete();
            return;
        }
        selectedAcIndex = -1;
        autocompleteDropdown.innerHTML = '';
        items.forEach(function(item, idx) {
            var div = document.createElement('div');
            div.className = 'autocomplete-item';
            div.innerHTML = '<span class="ac-label">' + escapeHtml(item.label) + '</span>'
                + (item.type ? '<span class="ac-type">' + escapeHtml(item.type) + '</span>' : '');
            div.addEventListener('mousedown', function(e) {
                e.preventDefault();  // Prevent blur
                insertAutocomplete(item.insert);
            });
            autocompleteDropdown.appendChild(div);
        });
        autocompleteDropdown.style.display = 'block';
    }

    function buildSuggestions(query) {
        var items = [
            { label: '@selection', insert: '@selection ', type: 'current selection' },
        ];

        // Standard views (D-19)
        ['front', 'back', 'top', 'bottom', 'left', 'right', 'iso'].forEach(function(v) {
            items.push({ label: '@view("' + v + '")', insert: '@view("' + v + '") ', type: 'camera view' });
        });

        if (designCache) {
            // Components (D-19)
            (designCache.components || []).forEach(function(c) {
                items.push({ label: '@component("' + c + '")', insert: '@component("' + c + '") ', type: 'component' });
            });
            // Bodies and other named entities
            (designCache.bodies || []).forEach(function(b) {
                items.push({ label: '@' + b.replace(/\//g, '_'), insert: '@' + b.split('/').pop() + ' ', type: 'body' });
            });
            (designCache.sketches || []).forEach(function(s) {
                items.push({ label: '@' + s.replace(/\//g, '_'), insert: '@' + s.split('/').pop() + ' ', type: 'sketch' });
            });
        }

        // Filter by query
        if (query) {
            items = items.filter(function(item) {
                return item.label.toLowerCase().indexOf(query) !== -1;
            });
        }

        return items.slice(0, 15);  // Limit to 15 suggestions
    }

    function insertAutocomplete(text) {
        var cursorPos = userInput.selectionStart;
        var value = userInput.value;
        var beforeCursor = value.substring(0, cursorPos);
        var afterCursor = value.substring(cursorPos);

        // Find the @ position to replace from
        var atPos = beforeCursor.lastIndexOf('@');
        if (atPos === -1) return;

        userInput.value = value.substring(0, atPos) + text + afterCursor;
        var newPos = atPos + text.length;
        userInput.setSelectionRange(newPos, newPos);
        hideAutocomplete();
        userInput.focus();
    }

    function hideAutocomplete() {
        autocompleteDropdown.style.display = 'none';
        autocompleteDropdown.innerHTML = '';
        selectedAcIndex = -1;
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function updateAcSelection(items) {
        for (var i = 0; i < items.length; i++) {
            items[i].classList.toggle('selected', i === selectedAcIndex);
        }
        if (selectedAcIndex >= 0 && items[selectedAcIndex]) {
            items[selectedAcIndex].scrollIntoView({ block: 'nearest' });
        }
    }

    // ******** Slash command menu (SLSH-01, SLSH-02, SLSH-03, D-01 through D-04) ********

    function checkSlashMenu() {
        var text = userInput.value;

        // Only trigger when / is at position 0 (D-09)
        if (text.charAt(0) !== '/') {
            hideSlashMenu();
            return;
        }

        // Hide @ autocomplete when slash menu is active (D-10)
        hideAutocomplete();

        if (!slashCommands) {
            adsk.fusionSendData('get_commands', '{}');
            return;  // Will retry when command_list arrives
        }

        var query = text.substring(1).toLowerCase();
        var filtered = slashCommands.filter(function(cmd) {
            return cmd.name.indexOf(query) !== -1 ||
                   cmd.description.toLowerCase().indexOf(query) !== -1;
        });

        if (filtered.length === 0) {
            hideSlashMenu();
            return;
        }

        selectedSlashIndex = -1;
        slashDropdown.innerHTML = '';
        filtered.forEach(function(cmd) {
            var div = document.createElement('div');
            div.className = 'autocomplete-item';
            div.innerHTML = '<span class="ac-label">/' + escapeHtml(cmd.name)
                + '</span><span class="ac-type">'
                + escapeHtml(cmd.description) + '</span>';
            div.addEventListener('mousedown', function(e) {
                e.preventDefault();
                userInput.value = '/' + cmd.name;
                hideSlashMenu();
                userInput.focus();
            });
            slashDropdown.appendChild(div);
        });
        slashDropdown.style.display = 'block';
    }

    function hideSlashMenu() {
        slashDropdown.style.display = 'none';
        slashDropdown.innerHTML = '';
        selectedSlashIndex = -1;
    }

    function updateSlashSelection(items) {
        for (var i = 0; i < items.length; i++) {
            items[i].classList.toggle('selected', i === selectedSlashIndex);
        }
        if (selectedSlashIndex >= 0 && items[selectedSlashIndex]) {
            items[selectedSlashIndex].scrollIntoView({ block: 'nearest' });
        }
    }

    // ******** Config overlay (CONF-01, CONF-02, CONF-03, D-05 through D-08) ********

    var configOriginalValues = null;  // Snapshot for dirty checking

    var providerDefaults = {
        gemini: 'gemini-3.1-pro-preview',
        claude: 'claude-sonnet-4-5',
        openai: 'gpt-4o',
    };

    var configValidation = {
        'cfg-max-iterations': { min: 1, max: 50, type: 'int', label: 'Max Visual Iterations' },
        'cfg-viewport-width': { min: 640, max: 3840, type: 'int', label: 'Capture Width' },
        'cfg-viewport-height': { min: 480, max: 2160, type: 'int', label: 'Capture Height' },
        'cfg-timeout': { min: 10, max: 300, type: 'int', label: 'Agent Timeout' },
    };

    function showConfigOverlay() {
        // Request current settings from Python
        adsk.fusionSendData('load_settings', '{}');
        configOverlay.style.display = 'flex';
        document.getElementById('chat-container').style.display = 'none';
        userInput.disabled = true;
    }

    function hideConfigOverlay() {
        configOverlay.style.display = 'none';
        document.getElementById('chat-container').style.display = 'flex';
        userInput.disabled = false;
        userInput.focus();
        // Clear validation errors
        var fields = configOverlay.querySelectorAll('.config-field');
        for (var i = 0; i < fields.length; i++) {
            fields[i].classList.remove('invalid');
            var err = fields[i].querySelector('.field-error');
            if (err) err.style.display = 'none';
        }
    }

    function populateConfig(data) {
        var apiKeys = data.api_keys || {};
        document.getElementById('cfg-provider').value = data.ai_provider || 'gemini';
        document.getElementById('cfg-model-name').value = data.ai_model_name || 'gemini-3.1-pro-preview';
        document.getElementById('cfg-api-key-gemini').value = apiKeys.gemini || '';
        document.getElementById('cfg-api-key-claude').value = apiKeys.claude || '';
        document.getElementById('cfg-api-key-openai').value = apiKeys.openai || '';
        document.getElementById('cfg-max-iterations').value = data.max_visual_iterations || 5;
        document.getElementById('cfg-timeout').value = data.agent_dispatch_timeout || 60;
        document.getElementById('cfg-debug').checked = data.debug !== false;
        document.getElementById('cfg-viewport-width').value = data.viewport_capture_width || 1920;
        document.getElementById('cfg-viewport-height').value = data.viewport_capture_height || 1080;

        // Snapshot for dirty tracking
        configOriginalValues = {
            ai_provider: data.ai_provider || 'gemini',
            ai_model_name: data.ai_model_name || 'gemini-3.1-pro-preview',
            api_key_gemini: apiKeys.gemini || '',
            api_key_claude: apiKeys.claude || '',
            api_key_openai: apiKeys.openai || '',
            max_visual_iterations: String(data.max_visual_iterations || 5),
            agent_dispatch_timeout: String(data.agent_dispatch_timeout || 60),
            debug: data.debug !== false,
            viewport_capture_width: String(data.viewport_capture_width || 1920),
            viewport_capture_height: String(data.viewport_capture_height || 1080),
        };
        configSave.disabled = true;
    }

    function validateConfigField(inputEl) {
        var fieldId = inputEl.id;
        var rules = configValidation[fieldId];
        var parentField = inputEl.closest('.config-field');
        var errorEl = parentField ? parentField.querySelector('.field-error') : null;

        // Model name: must not be empty
        if (fieldId === 'cfg-model-name') {
            var modelVal = inputEl.value.trim();
            if (!modelVal) {
                if (parentField) parentField.classList.add('invalid');
                if (errorEl) {
                    errorEl.textContent = 'Model name is required';
                    errorEl.style.display = 'block';
                }
                return false;
            } else {
                if (parentField) parentField.classList.remove('invalid');
                if (errorEl) errorEl.style.display = 'none';
                return true;
            }
        }

        if (!rules) return true;  // No validation rules (checkbox, api key, select)

        var value = inputEl.value.trim();
        var num = parseInt(value, 10);
        var errorMsg = '';

        if (value === '' || isNaN(num)) {
            errorMsg = rules.label + ' must be a number';
        } else if (num < rules.min) {
            errorMsg = 'Minimum: ' + rules.min;
        } else if (num > rules.max) {
            errorMsg = 'Maximum: ' + rules.max;
        }

        if (errorMsg) {
            if (parentField) parentField.classList.add('invalid');
            if (errorEl) {
                errorEl.textContent = errorMsg;
                errorEl.style.display = 'block';
            }
            return false;
        } else {
            if (parentField) parentField.classList.remove('invalid');
            if (errorEl) errorEl.style.display = 'none';
            return true;
        }
    }

    function validateAllConfig() {
        var allValid = true;
        var inputs = configOverlay.querySelectorAll('input[type="number"]');
        for (var i = 0; i < inputs.length; i++) {
            if (!validateConfigField(inputs[i])) {
                allValid = false;
            }
        }
        // Also validate model name
        var modelInput = document.getElementById('cfg-model-name');
        if (modelInput && !validateConfigField(modelInput)) {
            allValid = false;
        }
        return allValid;
    }

    function isConfigDirty() {
        if (!configOriginalValues) return false;
        return (
            document.getElementById('cfg-provider').value !== configOriginalValues.ai_provider ||
            document.getElementById('cfg-model-name').value !== configOriginalValues.ai_model_name ||
            document.getElementById('cfg-api-key-gemini').value !== configOriginalValues.api_key_gemini ||
            document.getElementById('cfg-api-key-claude').value !== configOriginalValues.api_key_claude ||
            document.getElementById('cfg-api-key-openai').value !== configOriginalValues.api_key_openai ||
            document.getElementById('cfg-max-iterations').value !== configOriginalValues.max_visual_iterations ||
            document.getElementById('cfg-timeout').value !== configOriginalValues.agent_dispatch_timeout ||
            document.getElementById('cfg-debug').checked !== configOriginalValues.debug ||
            document.getElementById('cfg-viewport-width').value !== configOriginalValues.viewport_capture_width ||
            document.getElementById('cfg-viewport-height').value !== configOriginalValues.viewport_capture_height
        );
    }

    function updateSaveButton() {
        var dirty = isConfigDirty();
        var valid = validateAllConfig();
        configSave.disabled = !(dirty && valid);
    }

    function saveConfig() {
        if (!validateAllConfig()) return;

        var payload = {
            ai_provider: document.getElementById('cfg-provider').value,
            ai_model_name: document.getElementById('cfg-model-name').value.trim(),
            max_visual_iterations: parseInt(document.getElementById('cfg-max-iterations').value, 10),
            viewport_capture_width: parseInt(document.getElementById('cfg-viewport-width').value, 10),
            viewport_capture_height: parseInt(document.getElementById('cfg-viewport-height').value, 10),
            agent_dispatch_timeout: parseInt(document.getElementById('cfg-timeout').value, 10),
            debug: document.getElementById('cfg-debug').checked,
        };

        // Only send API keys that changed from masked display (sentinel pattern)
        var apiKeys = {};
        var geminiKey = document.getElementById('cfg-api-key-gemini').value;
        var claudeKey = document.getElementById('cfg-api-key-claude').value;
        var openaiKey = document.getElementById('cfg-api-key-openai').value;
        if (geminiKey && !geminiKey.startsWith('****')) apiKeys.gemini = geminiKey;
        if (claudeKey && !claudeKey.startsWith('****')) apiKeys.claude = claudeKey;
        if (openaiKey && !openaiKey.startsWith('****')) apiKeys.openai = openaiKey;
        payload.api_keys = apiKeys;

        adsk.fusionSendData('save_settings', JSON.stringify(payload));
    }

    // Config overlay event listeners
    configBack.addEventListener('click', function() {
        hideConfigOverlay();
    });

    configCancel.addEventListener('click', function() {
        hideConfigOverlay();
    });

    configSave.addEventListener('click', function() {
        saveConfig();
    });

    // Provider change: auto-suggest default model name
    document.getElementById('cfg-provider').addEventListener('change', function(e) {
        var newProvider = e.target.value;
        var modelInput = document.getElementById('cfg-model-name');
        var currentModel = modelInput.value.trim();

        // Only auto-fill if model name is empty or matches a known provider default
        var isDefault = !currentModel;
        if (!isDefault) {
            for (var p in providerDefaults) {
                if (providerDefaults.hasOwnProperty(p) && currentModel === providerDefaults[p]) {
                    isDefault = true;
                    break;
                }
            }
        }

        if (isDefault && providerDefaults[newProvider]) {
            modelInput.value = providerDefaults[newProvider];
        }

        updateSaveButton();
    });

    // Inline validation on field change (D-07)
    configOverlay.addEventListener('input', function(e) {
        if (e.target.matches('input[type="number"], input[type="password"], input[type="text"]')) {
            validateConfigField(e.target);
            updateSaveButton();
        }
    });

    configOverlay.addEventListener('change', function(e) {
        if (e.target.matches('input[type="checkbox"]')) {
            updateSaveButton();
        }
    });

    // ******** History overlay (SESS-02, SESS-03, D-01 through D-04, D-11 through D-13) ********

    function showHistoryOverlay() {
        // Request session list from Python
        adsk.fusionSendData('load_sessions', '{}');
        historyOverlay.style.display = 'flex';
        document.getElementById('chat-container').style.display = 'none';
        userInput.disabled = true;
    }

    function hideHistoryOverlay() {
        historyOverlay.style.display = 'none';
        document.getElementById('chat-container').style.display = 'flex';
        userInput.disabled = false;
        userInput.focus();
    }

    function renderSessionList(sessions) {
        historyList.innerHTML = '';

        if (!sessions || sessions.length === 0) {
            historyEmpty.style.display = 'block';
            historyList.style.display = 'none';
            return;
        }

        historyEmpty.style.display = 'none';
        historyList.style.display = 'block';

        sessions.forEach(function(session) {
            var card = document.createElement('div');
            card.className = 'session-card' + (session.is_current ? ' current' : '');

            // Header row: timestamp + badge (D-11)
            var header = document.createElement('div');
            header.className = 'session-card-header';

            var timeEl = document.createElement('span');
            timeEl.className = 'session-card-time';
            timeEl.textContent = formatSessionTime(session.updated_at);
            header.appendChild(timeEl);

            if (session.is_current) {
                var badge = document.createElement('span');
                badge.className = 'session-card-badge';
                badge.textContent = 'Current';
                header.appendChild(badge);
            }

            card.appendChild(header);

            // Preview text (D-11)
            var preview = document.createElement('div');
            preview.className = 'session-card-preview';
            preview.textContent = session.preview || '(empty session)';
            card.appendChild(preview);

            // Delete button (only for non-current sessions)
            if (!session.is_current) {
                var actions = document.createElement('div');
                actions.className = 'session-card-actions';
                var delBtn = document.createElement('button');
                delBtn.className = 'session-delete-btn';
                delBtn.textContent = 'Delete';
                delBtn.addEventListener('click', function(e) {
                    e.stopPropagation();  // Don't trigger card click
                    adsk.fusionSendData('delete_session', JSON.stringify({ session_id: session.id }));
                });
                actions.appendChild(delBtn);
                card.appendChild(actions);
            }

            // Click to resume (D-03: immediate, no confirmation)
            card.addEventListener('click', function() {
                adsk.fusionSendData('resume_session', JSON.stringify({ session_id: session.id }));
            });

            historyList.appendChild(card);
        });
    }

    function formatSessionTime(isoString) {
        if (!isoString) return '';
        try {
            var d = new Date(isoString);
            var now = new Date();
            var diffMs = now - d;
            var diffMins = Math.floor(diffMs / 60000);
            var diffHours = Math.floor(diffMs / 3600000);
            var diffDays = Math.floor(diffMs / 86400000);

            if (diffMins < 1) return 'Just now';
            if (diffMins < 60) return diffMins + 'm ago';
            if (diffHours < 24) return diffHours + 'h ago';
            if (diffDays < 7) return diffDays + 'd ago';

            // Older than a week: show date
            var month = d.toLocaleString('default', { month: 'short' });
            return month + ' ' + d.getDate();
        } catch (e) {
            return isoString.substring(0, 10);  // Fallback: show date part
        }
    }

    // History back button handler
    historyBack.addEventListener('click', function() {
        hideHistoryOverlay();
    });

    // ******** Input handling (D-03: auto-expand, Enter sends, Shift+Enter newline) ********

    userInput.addEventListener('input', function() {
        // Auto-grow logic
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 96) + 'px';

        // Menu check (D-09, D-10, SLSH-05)
        clearTimeout(acDebounceTimer);
        acDebounceTimer = setTimeout(function() {
            var text = userInput.value;
            if (text.charAt(0) === '/') {
                checkSlashMenu();
            } else {
                hideSlashMenu();
                checkAutocomplete();
            }
        }, 200);
    });

    userInput.addEventListener('keydown', function(e) {
        // Overlay guard -- do not process keys when overlays are visible
        if (configOverlay.style.display !== 'none' ||
            historyOverlay.style.display !== 'none') {
            return;
        }

        // Slash menu keyboard navigation (SLSH-03)
        if (slashDropdown.style.display === 'block') {
            var slashItems = slashDropdown.querySelectorAll('.autocomplete-item');
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedSlashIndex = Math.min(selectedSlashIndex + 1, slashItems.length - 1);
                updateSlashSelection(slashItems);
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedSlashIndex = Math.max(selectedSlashIndex - 1, -1);
                updateSlashSelection(slashItems);
                return;
            }
            if (e.key === 'Enter' && selectedSlashIndex >= 0) {
                e.preventDefault();
                slashItems[selectedSlashIndex].dispatchEvent(new MouseEvent('mousedown'));
                return;
            }
            if (e.key === 'Escape') {
                hideSlashMenu();
                return;
            }
        }

        // Autocomplete keyboard navigation
        if (autocompleteDropdown.style.display === 'block') {
            var items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedAcIndex = Math.min(selectedAcIndex + 1, items.length - 1);
                updateAcSelection(items);
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedAcIndex = Math.max(selectedAcIndex - 1, -1);
                updateAcSelection(items);
                return;
            }
            if ((e.key === 'Enter' || e.key === 'Tab') && selectedAcIndex >= 0) {
                e.preventDefault();
                items[selectedAcIndex].dispatchEvent(new MouseEvent('mousedown'));
                return;
            }
            if (e.key === 'Escape') {
                hideAutocomplete();
                return;
            }
        }

        // Normal Enter sends message
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            var text = this.value.trim();
            if (text || pendingImage) {
                sendMessage(text);
                this.value = '';
                this.style.height = 'auto';
            }
        }
    });

    userInput.addEventListener('blur', function() {
        // Delay to allow mousedown on dropdown items to fire first
        setTimeout(function() {
            hideSlashMenu();
        }, 150);
    });

    // ******** Palette ready signal (Research Pitfall 1) ********

    document.addEventListener('DOMContentLoaded', function() {
        adsk.fusionSendData('palette_ready', '{}');
    });

})();
