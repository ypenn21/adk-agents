# Feature Implementation Plan: UI Modernization (OPS-11)

## 📋 Todo Checklist
Provide an action-oriented list of high-level tasks and files to be created/modified. Each item should have a checklist box (`- [ ]`).
- [x] Task 1: Complete and modernize the HTML template `adk_bug_ticket_agent/templates/adk_agent/interact.html` with theme toggle, chat history container, markdown rendering, auto-scrolling, and responsive layout.
- [x] Task 2: Implement jQuery-based chat interaction logic in `interact.html` to manage persistent session IDs (`sessionStorage`), assemble the ADK JSON payload, call `/agent/interact/` via AJAX POST, render markdown responses with `marked.js`, and display loading/disabled states.
- [x] Task 3: Implement CSS styling supporting light and dark modes with CSS custom properties (variables), accessible contrast, sleek message bubbles, code block styling, and responsive mobile/desktop layouts.
- [x] Task 4: Ensure Django view `interact_with_agent` in `adk_bug_ticket_agent/views.py` and route definitions in `adk_bug_ticket_agent/urls.py` and `web/urls.py` correctly serve the template on `GET` and handle chat requests on `POST`.
- [x] Task 5: Add automated unit/integration tests in `tests/test_ui_views.py` using Django's test client to test GET rendering, POST chat interactions, bad request validation, and URL reversibility.
- [x] Task 6: Execute verification test suite via `uv run pytest` and perform curl sanity tests on `/`, `/agent/`, and `/agent/interact/`.

---

## 🔍 Analysis & Investigation

### Codebase Structure
List all files related to this feature, indicating their current responsibility and physical location:
- `adk_bug_ticket_agent/templates/adk_agent/interact.html`: Primary UI template. Currently truncated/incomplete (ends abruptly at line 42 with an unclosed `<header>` and missing `<body>`/`</html>` closing tags). Needs full restoration and modernization.
- `adk_bug_ticket_agent/views.py`: Django async view `interact_with_agent`. Handles `GET` by rendering `adk_agent/interact.html` and `POST` by parsing ADK chat payload (`appName`, `userId`, `sessionId`, `newMessage`), running the Google ADK `Runner`, and returning JSON.
- `adk_bug_ticket_agent/urls.py`: Defines routes `""` (`name="interact_root"`), `"interact/"` (`name="interact_with_agent"`), and `"chat/"` (`name="chat"`).
- `web/urls.py`: Main URL configuration. Routes `""` directly to `agent_views.interact_with_agent` and `"agent/"` to include `adk_bug_ticket_agent.urls`.
- `web/settings.py`: Django project settings. Configures `TEMPLATES` with `APP_DIRS: True` and static file handling with WhiteNoise.
- `tests/test_ui_views.py`: Dedicated UI and view test suite to create for automated regression verification.

### Current Architecture
1. **Django MVC Layer**:
   - `web/urls.py` maps the root path `""` and `/agent/` to `adk_bug_ticket_agent/views.py::interact_with_agent`.
   - On HTTP `GET`, `interact_with_agent` calls `render(request, 'adk_agent/interact.html')`.
   - On HTTP `POST`, `interact_with_agent` receives a JSON payload conforming to the Google ADK chat schema:
     ```json
     {
       "appName": "AgentBugAssistant",
       "userId": "user_123",
       "sessionId": "<uuid>",
       "newMessage": {
         "role": "user",
         "parts": [{ "text": "<user_query>" }]
       },
       "streaming": false
     }
     ```
   - It validates the structure, retrieves or creates the ADK session via `_service_manager.session_service`, executes `runner.run_async()`, and returns:
     ```json
     {
       "content": {
         "parts": [{ "text": "<model_response>" }],
         "role": "model"
       },
       "timestamp": 1773499600.0
     }
     ```
2. **Current Defect / Incompleteness**:
   - Commit `133b757` left `adk_bug_ticket_agent/templates/adk_agent/interact.html` truncated after line 40 without message container, chat input box, send button, dark mode toggle button, or JavaScript controller logic.

### Dependencies & Integration Points
- **jQuery 3.7.1**: Loaded via CDN (`https://code.jquery.com/jquery-3.7.1.min.js`) to handle DOM events, AJAX communication (`$.ajax`), DOM manipulation, and theme toggle state.
- **Marked.js**: Loaded via CDN (`https://cdn.jsdelivr.net/npm/marked/marked.min.js`) for rendering markdown responses (tables, code snippets, lists, bold text) produced by Gemini.
- **Inter Font**: Loaded via Google Fonts for modern typography.
- **Session Management**: Client-side `sessionStorage` generates and retains a UUID (`adk_chat_session_id`) across queries within the tab, enabling multi-turn conversation memory with the ADK `DatabaseSessionService`.
- **Backend Endpoint**: Dispatched to `{% url 'interact_with_agent' %}` (`/agent/interact/` or `/`).

### Considerations & Challenges
- **FOUC (Flash of Unstyled Content) & Theme Persistence**: The dark mode preference should be stored in `localStorage.getItem('theme')` with fallback to `prefers-color-scheme: dark`. An inline script in `<head>` must set `document.documentElement.setAttribute('data-theme', theme)` immediately before DOM render to prevent flashing.
- **XSS Prevention**: Model responses parsed by `marked.js` should ensure markdown is rendered safely without inline script execution.
- **Asynchronous AJAX & Loading States**: During agent execution (which can take 1-5 seconds for tool invocations/search), the UI must disable the input box and send button, display a typing/spinner indicator, and re-enable controls on completion or error.
- **Responsive Layout**: The chat box should provide an app-like container with a scrollable conversation viewport (`overflow-y: auto`), sticky header with dark mode toggle, and sticky bottom input bar.

---

## 📐 Technical Specification & Design

### Component Architecture

```
+-----------------------------------------------------------------------------------+
|                                  Browser (Client)                                 |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | Header: Logo / App Name | Status Pill | Dark Mode Toggle (Moon/Sun)         |  |
|  +-----------------------------------------------------------------------------+  |
|  | Conversation Viewport (#conversation):                                      |  |
|  |   - Welcome Bubble (Agent)                                                  |  |
|  |   - User Message Bubbles (Right-aligned, accent color)                      |  |
|  |   - Agent Message Bubbles (Left-aligned, rendered Markdown / tables / code) |  |
|  |   - Typing / Thinking Spinner Indicator (#loadingIndicator)                 |  |
|  +-----------------------------------------------------------------------------+  |
|  | Input Area (#inputContainer):                                               |  |
|  |   - <textarea> / <input> (#messageInput)                                    |  |
|  |   - Send Button (#sendButton) with paper-plane / send icon                  |  |
|  +-----------------------------------------------------------------------------+  |
|                                                                                   |
|  jQuery Controller:                                                               |
|    - Theme Switcher -> updates localStorage & data-theme attribute                |
|    - Event Handlers: Enter keypress & #sendButton click                           |
|    - Session Handler: crypto.randomUUID() saved in sessionStorage                 |
|    - AJAX: $.ajax({ url: '/agent/interact/', method: 'POST', data: ... })        |
+------------------------------------------+----------------------------------------+
                                           | JSON POST
                                           v
+-----------------------------------------------------------------------------------+
|                        Django Backend: interact_with_agent                        |
|   1. GET  -> renders interact.html                                                |
|   2. POST -> receives payload, executes ADK Runner, returns response JSON         |
+-----------------------------------------------------------------------------------+
```

### Mermaid Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser as Browser (interact.html)
    participant jQuery as jQuery Script
    participant View as Django View (interact_with_agent)
    participant ADK as ADK Runner & Gemini

    User->>Browser: Opens / or /agent/interact/
    Browser->>View: GET /
    View-->>Browser: Render interact.html
    Note over Browser,jQuery: Check localStorage for theme;<br/>Initialize session UUID in sessionStorage

    User->>Browser: Enters query & clicks "Send" (or presses Enter)
    Browser->>jQuery: Submit event triggered
    jQuery->>Browser: Append user message bubble, clear input, show spinner, disable button
    jQuery->>View: POST /agent/interact/ (JSON payload: appName, userId, sessionId, newMessage)
    View->>ADK: runner.run_async(user_id, session_id, message)
    ADK-->>View: Stream events -> final text response
    View-->>jQuery: 200 OK JSON: { content: { parts: [{ text: "..." }] } }
    jQuery->>jQuery: marked.parse(text)
    jQuery->>Browser: Hide spinner, append agent message bubble, re-enable input, scroll to bottom
    User->>Browser: Clicks Dark/Light theme toggle
    Browser->>jQuery: Click #themeToggle
    jQuery->>Browser: Toggle data-theme ("light" <-> "dark") & update localStorage
```

### Schemas & Models

#### 1. Request Payload Schema (Sent via jQuery AJAX to `/agent/interact/`)
```json
{
  "appName": "AgentBugAssistant",
  "userId": "user_123",
  "sessionId": "4b684c98-1111-4040-9999-4a9238914b10",
  "newMessage": {
    "role": "user",
    "parts": [
      {
        "text": "What are the high-priority open bugs in our system?"
      }
    ]
  },
  "streaming": false
}
```

#### 2. Success Response Payload Schema (From `/agent/interact/`)
```json
{
  "content": {
    "parts": [
      {
        "text": "Here are the high-priority bugs currently tracked in the database:\n\n| Bug ID | Title | Priority | Status |\n|---|---|---|---|\n| BUG-101 | Authentication timeout | High | Open |\n"
      }
    ],
    "role": "model"
  },
  "timestamp": 1773499600.05
}
```

#### 3. Error Response Payload Schema
```json
{
  "error": "Error message description",
  "traceback": "Optional traceback for debugging"
}
```

### API & Code Signatures

#### Django View Signature
- Function: `async def interact_with_agent(request: HttpRequest) -> HttpResponse`
- Handled methods:
  - `GET`: Returns rendered `adk_agent/interact.html`.
  - `POST`: Parses JSON body, interacts with ADK, returns `JsonResponse`.
  - Other: Returns `JsonResponse({'error': 'Unsupported method'}, status=405)`.

#### JavaScript / jQuery Functions to Specify
- `initTheme()`: Reads `localStorage.getItem('adk_theme')` or system preference (`prefers-color-scheme`) and sets `document.documentElement.dataset.theme`.
- `toggleTheme()`: Toggles between `'light'` and `'dark'`, sets attribute, stores in `localStorage`, and swaps the theme toggle icon.
- `getSessionId() -> string`: Retrieves or generates a valid UUID4 using `window.crypto.randomUUID()` and caches it in `sessionStorage`.
- `appendMessage(role: 'user'|'agent'|'error', content: string)`: Appends a styled message bubble to `#conversation` container. For agent messages, parses markdown via `marked.parse(content)`.
- `sendMessage()`: Reads `#messageInput`, validates non-empty, calls `appendMessage('user', text)`, activates loading indicator, triggers `$.ajax`, handles response/error, and restores focus.
- `scrollToBottom()`: Smoothly or directly scrolls `#conversation` to `scrollHeight`.

---

## 📝 Step-by-Step Implementation Steps

### Step 1: Complete and Polish `interact.html` Template
1. **Files to modify/create**: `adk_bug_ticket_agent/templates/adk_agent/interact.html`
2. **Changes needed**:
   - Restore the missing DOM hierarchy from line 40 onwards.
   - Add theme toggle button in header with Moon and Sun SVG icons.
   - Add container layout: `#app-container`, `#conversation`, `#pendingIndicator`, `#inputArea`.
   - Embed CSS styles with modern design system:
     - Color tokens for light and dark themes using `:root[data-theme="light"]` and `:root[data-theme="dark"]`.
     - Clean typography using Inter font family.
     - Styled message cards with distinct user (accent blue background, right-aligned) and agent (neutral card background, left-aligned) bubbles.
     - Markdown tables with crisp borders, headers, and zebra striping.
     - Code blocks with monospace styling and dark backgrounds.
     - Animated typing/loading indicator with bouncing dots or rotating spinner.
     - Responsive input group with text input, send button, and focus outlines.
3. **Implementation Notes**:
   - Ensure `marked.js` and `jQuery 3.7.1` CDNs are correctly referenced.
   - Include the FOUC prevention snippet directly in `<head>`:
     ```javascript
     (function() {
       const savedTheme = localStorage.getItem('adk_theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
       document.documentElement.setAttribute('data-theme', savedTheme);
     })();
     ```
4. **Status**: Pending

### Step 2: Implement jQuery Chat & Theme Controller Script
1. **Files to modify/create**: `adk_bug_ticket_agent/templates/adk_agent/interact.html`
2. **Changes needed**:
   - Wrap client-side script inside `$(document).ready(function() { ... });`.
   - Wire `#themeToggle` click event to switch theme between light and dark, persisting in `localStorage`.
   - Maintain `sessionId` in `sessionStorage`.
   - Implement `sendMessage()`:
     - Read and trim `#messageInput.val()`.
     - Disable `#sendButton` and `#messageInput`.
     - Display `#pendingIndicator`.
     - Post JSON via `$.ajax`:
       ```javascript
       $.ajax({
         url: '{% url "interact_with_agent" %}',
         type: 'POST',
         contentType: 'application/json',
         data: JSON.stringify(payload),
         success: function(data) { ... },
         error: function(xhr, status, error) { ... },
         complete: function() { ... }
       });
       ```
     - On success: Extract `data.content.parts[0].text`, parse with `marked.parse()`, and append to `#conversation`.
     - On error: Extract error message and display helpful notification bubble.
     - Bind `keypress` (Enter key) on `#messageInput` to trigger `sendMessage()`.
3. **Implementation Notes**:
   - Prevent empty messages from being sent.
   - Ensure conversation scrolls down automatically upon new message arrival.
4. **Status**: Pending

### Step 3: Verify Django Views and URLs
1. **Files to modify/create**: `adk_bug_ticket_agent/views.py`, `adk_bug_ticket_agent/urls.py`, `web/urls.py`
2. **Changes needed**:
   - Verify that `interact_with_agent` properly handles both `GET` and `POST`.
   - Check if CSRF exemption is in place (`@csrf_exempt`) or if `X-CSRFToken` header should be passed. Since `@csrf_exempt` is already on `interact_with_agent`, both session-based and stateless REST clients can post directly.
   - Ensure all URL names (`interact_root`, `interact_with_agent`, `chat`) resolve cleanly without reverse-lookup errors.
3. **Implementation Notes**:
   - No modifications to ADK model or agent configuration needed.
4. **Status**: Pending

### Step 4: Write Comprehensive Automated View & UI Tests
1. **Files to modify/create**: `tests/test_ui_views.py`
2. **Changes needed**:
   - Create tests using Django's test client (`django.test.Client` or `django.test.AsyncClient`):
     - `test_get_interact_page`: GET `/` and GET `/agent/interact/` return status code 200, use template `adk_agent/interact.html`, and contain crucial DOM elements (`#conversation`, `#messageInput`, `#sendButton`, `#themeToggle`, jQuery script tag, `marked.min.js`).
     - `test_post_invalid_json`: POST invalid JSON returns 400 with `'error': 'Invalid JSON in request'`.
     - `test_post_missing_fields`: POST missing required ADK fields returns 400 `'Invalid payload structure.'`.
     - `test_unsupported_http_method`: PUT or DELETE requests return 405 Method Not Allowed.
     - `test_urls_reverse`: Verify `reverse('interact_with_agent')` and `reverse('root')` resolve as expected.
3. **Implementation Notes**:
   - Set `DJANGO_SETTINGS_MODULE="web.settings"` and call `django.setup()` if running directly with pytest.
4. **Status**: Pending

### Step 5: Execute Sanity Checks and Curl Verification
1. **Files to modify/create**: Execution via shell / pytest.
2. **Changes needed**:
   - Run `uv run pytest tests/` to confirm all existing and new tests pass.
   - Run `python manage.py check` to verify Django configurations.
   - Run `python manage.py test` or pytest.
   - Perform curl verification commands against local endpoints.
3. **Implementation Notes**:
   - Test both `/` and `/agent/interact/`.
4. **Status**: Pending

---

## 🧪 Verification & Testing Strategy

### Unit / Integration Tests
Test file: `tests/test_ui_views.py`
- Test cases:
  1. `test_ui_get_root_status_and_content`: Validates that `GET /` returns 200 with HTML content including modern UI elements and CDNs (jQuery 3.7.1, marked.min.js, Inter font).
  2. `test_ui_get_agent_interact_status_and_content`: Validates `GET /agent/interact/` returns 200.
  3. `test_post_missing_payload`: Validates `POST /agent/interact/` with `{}` returns 400.
  4. `test_post_invalid_json`: Validates `POST /agent/interact/` with malformed JSON string returns 400.
  5. `test_unsupported_methods`: Validates `PUT /agent/interact/` returns 405.

### Shell & Curl Commands
1. Run pytest suite:
   ```bash
   uv run pytest tests/
   ```
2. Verify Django system checks:
   ```bash
   uv run python manage.py check
   ```
3. Curl sanity test on GET endpoint:
   ```bash
   curl -I -s http://127.0.0.1:8000/
   curl -I -s http://127.0.0.1:8000/agent/interact/
   ```
4. Curl sanity test on POST endpoint (validation):
   ```bash
   curl -s -X POST http://127.0.0.1:8000/agent/interact/ \
     -H "Content-Type: application/json" \
     -d '{}'
   ```
   Expected response: `{"error": "Invalid payload structure."}` (Status 400).

### Expected Results
- HTML response contains modern CSS layout, dark mode toggle buttons, jQuery inclusion, marked.js inclusion, and the chat container.
- Switching dark mode sets `data-theme="dark"` on `<html>` and updates `localStorage`.
- All automated pytest tests pass with 0 failures.

---

## 🎯 Success Criteria
1. **Modern Responsive UI**: `interact.html` is fully formed with a responsive, modern container layout, dark/light mode toggle with persistent state in `localStorage`, clean typography, and styled chat bubbles.
2. **Interactive Chat Input**: Input field and send button are responsive, support Enter-key submissions, disable during request execution with an animated pending indicator, and re-enable upon receipt.
3. **Markdown & Table Formatting**: Agent responses containing Markdown (lists, bold text, code blocks, and markdown tables) are parsed and rendered via `marked.js`.
4. **jQuery Integration**: Client-side logic utilizes jQuery for event listeners, DOM manipulation, and AJAX POST requests to `/agent/interact/` conforming to the ADK payload schema.
5. **Clean Verification**: All automated test cases in `tests/test_ui_views.py` and `tests/test_database_session.py` pass without errors.
