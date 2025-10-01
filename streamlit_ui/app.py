
import streamlit as st
import requests
import json
import os
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="IT Bug Assistant",
    page_icon="🐛",
    layout="centered"
)

# Agent URL
AGENT_URL = os.environ.get('AGENT_URL', 'http://127.0.0.1:8000')
st.sidebar.markdown("### ⚙️ Agent Settings")
st.sidebar.markdown(f"**Agent URL:** `{AGENT_URL}`")

# Sidebar toggles
show_raw_json = st.sidebar.checkbox("📦 Show raw JSON response", value=False)
verbose_mode = st.sidebar.checkbox("🔁 Verbose logging", value=True)

# Session state
if 'session_id' not in st.session_state:
    session_id = f"streamlit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    st.session_state.session_id = session_id
    st.sidebar.markdown("### 🧾 Session Info")
    st.sidebar.markdown("🆕 **New Session Created:**")
    st.sidebar.code(session_id)
else:
    st.sidebar.markdown("### 🧾 Session Info")
    st.sidebar.markdown("📂 **Resuming Session:**")
    st.sidebar.code(st.session_state.session_id)


if 'messages' not in st.session_state:
    st.session_state.messages = []

# Title and UI header
st.title("IT Bug Assistant")
st.markdown("I can help you triage, manage, and resolve software issues.")


# Display previous messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# === Main Chat Input Handling ===
if prompt := st.chat_input("How can I help with your IT ticket?"):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Agent response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                # Send user ID, session, and prompt to agent
                response = requests.post(
                    f"{AGENT_URL}/agent/interact/",
                    json={
                        "appName": "it_bug_assistant_agent",
                        "userId": "streamlit_user",
                        "sessionId": st.session_state.session_id,
                        "newMessage": {
                            "parts": [{"text": prompt}]
                        }
                    },
                    timeout=300
                )

                if response.status_code == 200:
                    result = response.json()
                    
                    if show_raw_json:
                        st.sidebar.markdown("### 📦 Full Response JSON")
                        st.sidebar.json(result)

                    agent_message = result.get("content", {}).get("parts", [{}])[0].get("text", "Sorry, I encountered an error.")
                    st.markdown(agent_message)
                    st.session_state.messages.append({"role": "assistant", "content": agent_message})

                else:
                    st.error(f"Error: {response.status_code} from agent.")

            except Exception as e:
                st.error(f"Error communicating with the agent: {e}")

# Footer
st.markdown("---")
st.markdown("*Powered by Google Cloud ADK and Gemini*")
