CREATE EXTENSION IF NOT EXISTS google_ml_integration CASCADE;
CREATE EXTENSION IF NOT EXISTS vector CASCADE;
GRANT EXECUTE ON FUNCTION embedding TO postgres;

CREATE TABLE tickets (
    ticket_id SERIAL PRIMARY KEY,             -- PostgreSQL's auto-incrementing integer type (SERIAL is equivalent to INT AUTO_INCREMENT)
    title VARCHAR(255) NOT NULL,              -- A concise summary or title of the bug/issue.
    description TEXT,                         -- A detailed description of the bug.
    assignee VARCHAR(100),                    -- The name or email of the person/team assigned to the ticket.
    priority VARCHAR(50),                     -- The priority level (e.g., 'P0 - Critical', 'P1 - High').
    status VARCHAR(50) DEFAULT 'Open',        -- The current status of the ticket (e.g., 'Open', 'In Progress', 'Resolved'). Default is 'Open'.
    creation_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, -- Timestamp when the ticket was first created. 'WITH TIME ZONE' is recommended for clarity and compatibility.
    updated_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP  -- Timestamp when the ticket was last updated. Will be managed by a trigger.
);
INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('User Profile Update Fails Silently', 'When a user attempts to update their profile information, the system indicates success but the changes are not persisted in the database.', 'david.lee@example.com', 'P2 - Medium', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Incorrect Currency Conversion for International Orders', 'For orders placed with international currencies (e.g., EUR, JPY), the conversion rate applied during checkout is inaccurate, leading to incorrect final prices.', 'susan.chen@example.com', 'P1 - High', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Email Notifications Not Sending for Password Resets', 'Users are reporting that they are not receiving email notifications when they attempt to reset their password, preventing access.', 'robert.jones@example.com', 'P0 - Critical', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Pagination Fails on Product Catalog Page', 'On the product catalog page, clicking on subsequent pagination links (e.g., page 2, 3) always returns to the first page of results.', 'david.lee@example.com', 'P2 - Medium', 'In Progress');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Image Upload Corrupts Files Larger Than 5MB', 'Attempting to upload images exceeding 5MB results in a corrupted file being stored, displaying as a broken link or a blank image.', 'susan.chen@example.com', 'P1 - High', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Search Results Inconsistent with Keyword Queries', 'Performing a search with specific keywords sometimes yields irrelevant results, or fails to show highly relevant items that should match.', 'robert.jones@example.com', 'P3 - Low', 'Resolved');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Shopping Cart Item Quantity Not Updating', 'When a user changes the quantity of an item in the shopping cart, the total price updates, but the item quantity display remains unchanged.', 'david.lee@example.com', 'P1 - High', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Mobile App Crashes on Android 12 Devices', 'The mobile application is consistently crashing on devices running Android 12, particularly when navigating to the settings screen.', 'susan.chen@example.com', 'P0 - Critical', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Admin Panel User Deletion Confirmation Missing', 'When an administrator deletes a user from the admin panel, there is no confirmation dialog, leading to accidental deletions.', 'robert.jones@example.com', 'P2 - Medium', 'In Progress');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Video Playback Buffering Issues on Safari Browser', 'Users watching embedded videos on the platform via Safari are experiencing excessive buffering and frequent interruptions.', 'david.lee@example.com', 'P2 - Medium', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Broken Accessibility Link for Screen Readers', 'A "Skip to Content" link designed for screen readers is not correctly navigating to the main content area.', 'susan.chen@example.com', 'P3 - Low', 'Resolved');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('API Endpoint Returning 500 Error Intermittently', 'The `/api/v1/data_feed` endpoint is sporadically returning a 500 Internal Server Error, affecting data synchronization.', 'robert.jones@example.com', 'P1 - High', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Report Generation Timeouts for Large Datasets', 'Generating reports with more than 10,000 records frequently results in a timeout error before the report is fully generated.', 'david.lee@example.com', 'P1 - High', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('UI Overlap on Dashboard Widgets in Firefox', 'When viewing the dashboard in Firefox, certain widgets (e.g., "Recent Activity") overlap with adjacent elements, distorting the layout.', 'susan.chen@example.com', 'P2 - Medium', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Password Reset Link Expires Too Quickly (1 minute)', 'The password reset link provided in the email is expiring after approximately one minute, making it impossible for users to reset their passwords.', 'robert.jones@example.com', 'P0 - Critical', 'In Progress');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Incorrect Data Displayed in User Activity Log', 'The "Last Login" time in the user activity log is showing incorrect timestamps, often several hours off from the actual login.', 'david.lee@example.com', 'P3 - Low', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Missing Translation for "Add to Cart" Button (French)', 'The "Add to Cart" button on product pages does not display in French when the user selects the French language option.', 'susan.chen@example.com', 'P2 - Medium', 'Resolved');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Broken Image Links in Email Templates', 'Images embedded in automated email templates (e.g., order confirmation) are not loading and appear as broken links.', 'robert.jones@example.com', 'P2 - Medium', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Form Submission Fails with Special Characters in Input', 'Submitting forms containing special characters like `&`, `<`, or `>` in text fields results in a submission error.', 'david.lee@example.com', 'P1 - High', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('User Sessions Not Expiring After Inactivity', 'User sessions are not automatically expiring after the configured inactivity period, posing a security risk.', 'susan.chen@example.com', 'P1 - High', 'In Progress');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Sorting by Price Not Working on Search Results', 'The "Sort by Price" option on the search results page does not correctly reorder the items from lowest to highest or vice versa.', 'robert.jones@example.com', 'P2 - Medium', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('PDF Download Button Unresponsive on Mobile', 'The "Download as PDF" button on report pages is unresponsive when tapped on various mobile devices (iOS and Android).', 'david.lee@example.com', 'P2 - Medium', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('API Rate Limiting Not Functioning Correctly', 'The implemented API rate limiting is not effectively blocking excessive requests, leading to potential abuse and server strain.', 'susan.chen@example.com', 'P0 - Critical', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Duplicate Entries Created on Form Resubmission', 'Submitting a form multiple times due to a slow network or double-clicking results in duplicate entries in the database.', 'robert.jones@example.com', 'P1 - High', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Accessibility: Keyboard Navigation Skips Elements', 'Users relying on keyboard navigation are unable to tab through all interactive elements on the contact form, skipping fields.', 'david.lee@example.com', 'P3 - Low', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('External Link Opens in Same Tab Instead of New Tab', 'Clicking on external links within the application (e.g., links to social media) opens them in the same browser tab, navigating away from the app.', 'susan.chen@example.com', 'P3 - Low', 'Resolved');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Performance: Dashboard Loads Slowly with Many Widgets', 'The main dashboard takes more than 10 seconds to load when a user has a large number of active widgets configured.', 'robert.jones@example.com', 'P1 - High', 'In Progress');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Broken Image Preview in Image Uploader', 'When attempting to upload a new profile picture, the image preview does not render correctly, showing a broken image icon.', 'david.lee@example.com', 'P2 - Medium', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Incorrect Time Zone Display for Scheduled Events', 'Scheduled events are displayed in the wrong time zone for users, not respecting their local time settings or the event''s original time zone.', 'susan.chen@example.com', 'P1 - High', 'Open');

INSERT INTO tickets (title, description, assignee, priority, status) VALUES
('Security Vulnerability: SQL Injection via Search Bar', 'A potential SQL Injection vulnerability has been identified in the application''s public search bar, allowing malicious input to alter queries.', 'robert.jones@example.com', 'P0 - Critical', 'Open');
