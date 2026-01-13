# Specification: Recent Tickets Summary Feature

## 1. Overview
The "Recent Tickets Summary" feature will be a new section on the main agent dashboard (Web UI). It will display a list of the 5 most recently updated or created bug tickets. This allows IT Support Representatives to quickly access active issues without needing to perform a manual search.

## 2. Goals
- **Efficiency:** Reduce the time it takes for support staff to access their most relevant active tickets.
- **Visibility:** Provide immediate visibility into the latest activity in the bug tracking system.

## 3. User Stories
- As an IT Support Representative, I want to see a list of the most recent tickets on my dashboard so that I can quickly jump back into active issues.
- As an IT Support Representative, I want to see key details (ID, Title, Status, Priority, Updated Time) for each recent ticket to decide which one needs attention.

## 4. Functional Requirements
- **Backend:**
    - Create a new Django view or update the existing dashboard view to query the PostgreSQL database.
    - The query should retrieve the 5 most recently updated tickets (sorted by `updated_time` DESC).
    - Ensure the query efficiently fetches only necessary fields: ID, Title, Status, Priority, and Updated Time.
- **Frontend:**
    - Update the main dashboard HTML template to include a "Recent Tickets" section.
    - Display the tickets in a clean, responsive table or list format.
    - Each ticket entry should be clickable, linking to the ticket's detail view (if available) or opening a modal with details.
    - Handle the case where there are no tickets gracefully (display a "No recent tickets" message).

## 5. Non-Functional Requirements
- **Performance:** The database query must be optimized to not slow down the dashboard load time.
- **UI/UX:** The design should match the existing "Minimalist & Modern" style of the application.
- **Security:** Ensure that standard Django security practices are followed (e.g., using the ORM to prevent SQL injection).

## 6. API/Data Structure Changes
- No schema changes are expected.
- **Data Query (Python/Django ORM):**
  ```python
  Ticket.objects.order_by('-updated_time')[:5]
  ```

