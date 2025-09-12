# Feature Implementation Plan: Modernize Chat UI

## 📋 Todo Checklist
- [ ] Set up static file handling for the Django project.
- [ ] Create a new HTML template for the chat interface.
- [ ] Add CSS for a modern look and feel with dark mode.
- [ ] Implement chat functionality using jQuery in a dedicated JavaScript file.
- [ ] Update the Django view and URL configuration to serve the new UI.
- [ ] Final Review and Testing.

## 🔍 Analysis & Investigation

### Codebase Structure
The project is a standard Django application. The core logic for the agent is within the `adk_bug_ticket_agent` app.
- `adk_bug_ticket_agent/views.py`: Contains the view that handles both rendering the chat page and processing the chat interaction API calls.
- `adk_bug_ticket_agent/templates/adk_agent/interact.html`: The existing HTML template for the chat UI. It uses vanilla JavaScript and inline CSS.
- `web_ui/settings.py`: The main Django settings file. It has `whitenoise` configured for static file serving in production, but lacks a `STATICFILES_DIRS` setting for development.
- `web_ui/urls.py` and `adk_bug_ticket_agent/urls.py`: These files manage the URL routing for the application.

### Current Architecture
The application follows Django's Model-View-Template (MVT) pattern. A single view function `interact_with_agent` serves the HTML page on GET requests and handles the chat logic on POST requests. The frontend is a simple, single-page interface that communicates with the backend via AJAX (`fetch` API).

### Dependencies & Integration Points
- **jQuery:** The Jira ticket explicitly requests the use of jQuery. The current implementation does not use it. It will need to be added, likely via a CDN link in the new HTML template.
- **Django Static Files:** The new CSS and JavaScript files will need to be served by Django's static files system.

### Considerations & Challenges
- **Static File Configuration:** The project is set up for production static file serving with `whitenoise` and `STATIC_ROOT`, but it's missing the `STATICFILES_DIRS` configuration in `settings.py`, which is best practice for managing project-level static files during development. This will need to be added.
- **Dark Mode:** Implementing a dark mode toggle will require CSS variables for colors and a small amount of JavaScript to switch between themes and persist the user's choice (e.g., using `localStorage`).

## 📝 Implementation Plan

### Prerequisites
- No new backend packages are needed.
- A basic understanding of Django's static file handling is required.

### Step-by-Step Implementation
1. **Configure Static Files for Development**
   - **Files to modify:** `web_ui/settings.py`
   - **Changes needed:** Add a `STATICFILES_DIRS` setting to inform Django where to find project-level static files during development. Also, create the main static directory.
   - **Details:**
     - Create a new directory: `adk_bug_ticket_agent/static/`
     - In `web_ui/settings.py`, add the following near the `STATIC_URL` and `STATIC_ROOT` settings:
       ```python
       STATICFILES_DIRS = [BASE_DIR / "adk_bug_ticket_agent/static"]
       ```

2. **Create New CSS and JavaScript Files**
   - **Files to create:**
     - `adk_bug_ticket_agent/static/css/style.css`
     - `adk_bug_ticket_agent/static/js/chat.js`
   - **Changes needed:**
     - The `style.css` file will contain all the styling for the new chat UI, including CSS variables for theming (light/dark modes).
     - The `chat.js` file will contain the jQuery code for handling user input, sending messages to the backend, and displaying the response.

3. **Create the New HTML Template**
   - **Files to create:** `adk_bug_ticket_agent/templates/adk_agent/interact_v2.html`
   - **Changes needed:**
     - Create a new HTML file with a modern structure for the chat interface.
     - Include a link to the jQuery CDN in the `<head>` section.
     - Link the new `style.css` and `chat.js` static files using Django's `{% static %}` template tag.
     - Add a button or toggle for switching between light and dark modes.

4. **Implement the UI Styling (CSS)**
   - **Files to modify:** `adk_bug_ticket_agent/static/css/style.css`
   - **Changes needed:**
     - Define CSS variables for colors to make theme switching easy.
     - Style the chatbox, messages, input area, and buttons for a modern look.
     - Create a `.dark-mode` class that overrides the default color variables for the dark theme.

5. **Implement the Chat Logic (JavaScript)**
   - **Files to modify:** `adk_bug_ticket_agent/static/js/chat.js`
   - **Changes needed:**
     - Use jQuery's `$(document).ready()` to initialize the chat.
     - Write a function to send messages to the `/agent/interact/` endpoint using `$.ajax()`.
     - Write a function to append user and agent messages to the chat conversation.
     - Implement the dark mode toggle functionality, which adds/removes the `.dark-mode` class to the `<body>` and saves the preference in `localStorage`.

6. **Update Django View and URLs**
   - **Files to modify:**
     - `adk_bug_ticket_agent/views.py`
     - `adk_bug_ticket_agent/urls.py`
   - **Changes needed:**
     - In `views.py`, create a new view function, `interact_v2`, that renders the new `interact_v2.html` template.
     - In `urls.py`, add a new URL pattern that maps to the `interact_v2` view, for example: `path('interact_v2/', views.interact_v2, name='interact_with_agent_v2')`.

### Testing Strategy
1. **Manual Testing:**
   - Run the Django development server (`python manage.py runserver`).
   - Navigate to the new URL (e.g., `/agent/interact_v2/`).
   - Verify that the new UI renders correctly.
   - Send messages to the agent and confirm that responses are displayed properly.
   - Test the dark mode toggle to ensure the theme changes and the choice is persisted across page reloads.
   - Check the browser's developer console for any JavaScript errors.
2. **Static File Check:**
   - Ensure that the CSS and JavaScript files are being loaded correctly (HTTP 200 status in the network tab of browser developer tools).
   - Run `python manage.py collectstatic` to ensure that the new static files are collected into the `staticfiles` directory for production.

## 🎯 Success Criteria
- The new chat UI is served from a new template (`interact_v2.html`) at a distinct URL.
- The UI has a modern design, is styled with external CSS, and includes a functional dark mode.
- All chat interaction logic is handled by an external JavaScript file using jQuery for AJAX calls.
- The application remains fully functional, and the user can have a complete conversation with the agent through the new interface.
