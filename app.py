import streamlit as st
import boto3
import requests
import os
import json
from datetime import datetime
from PIL import Image
import base64

# ----------- CONFIG -----------
AWS_REGION = "us-east-1"
API_GATEWAY_URL = "https://your-api-gateway-url.execute-api.region.amazonaws.com/prod/chat"
DYNAMODB_TABLE = "ChatHistory"
LOCAL_LOG_DIR = "chat_logs"

# ----------- AUTH STATE -----------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.username = ""

# ----------- AUTH -----------
if not st.session_state.authenticated:
    st.title("🔐 Login")
    with st.form("login_form"):
        user = st.text_input("Username")
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if user in ["alice", "bob"] and pw == f"{user}123":
                st.session_state.authenticated = True
                st.session_state.username = user
                st.experimental_rerun()
            else:
                st.error("Incorrect username/password")
    st.stop()

# ----------- USER AND MODE -----------
username = st.session_state.username
USE_LOCAL_ONLY = st.sidebar.checkbox("🧪 Local Testing Mode", value=True)

# AWS Clients
if not USE_LOCAL_ONLY:
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = dynamodb.Table(DYNAMODB_TABLE)

# ----------- HELPERS -----------
def logo_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def load_chat_history(session_id):
    local_path = os.path.join(LOCAL_LOG_DIR, f"{session_id}.json")
    if os.path.exists(local_path):
        with open(local_path, "r") as f:
            return json.load(f)
    if not USE_LOCAL_ONLY:
        response = table.get_item(Key={"SessionId": session_id})
        return response.get("Item", {}).get("ChatHistory", [])
    return []

def save_chat_history(session_id, chat_history):
    os.makedirs(LOCAL_LOG_DIR, exist_ok=True)
    local_path = os.path.join(LOCAL_LOG_DIR, f"{session_id}.json")
    with open(local_path, "w") as f:
        json.dump(chat_history, f)
    if not USE_LOCAL_ONLY:
        table.put_item(Item={"SessionId": session_id, "ChatHistory": chat_history})

# ----------- INIT STATE -----------
if "session_id" not in st.session_state:
    st.session_state.session_id = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
if "chat_history" not in st.session_state:
    st.session_state.chat_history = load_chat_history(st.session_state.session_id)

# ----------- SIDEBAR -----------
with st.sidebar:
    logo_path = os.path.join(os.path.dirname(__file__), "dataops_logo.png")
    if os.path.exists(logo_path):
        st.markdown(
            f"<img src='data:image/png;base64,{logo_base64(logo_path)}' width='120' />",
            unsafe_allow_html=True,
        )
    st.markdown(f"### 👤 {username}")

    if st.button("🚪 Logout"):
        st.session_state.clear()
        st.experimental_rerun()

    st.markdown("---")
    st.markdown("### 📂 Previous chats")

    session_files = {}
    os.makedirs(LOCAL_LOG_DIR, exist_ok=True)
    local_files = [f for f in os.listdir(LOCAL_LOG_DIR) if f.endswith(".json")]

    for fname in sorted(local_files):
        session_id = fname[:-5]
        try:
            chat = load_chat_history(session_id)
            first_msg = next((m["content"] for m in chat if m["role"] == "user"), "New Chat")
            session_files[f"{session_id} - {first_msg[:30]}"] = session_id
        except Exception:
            continue

    selected = st.selectbox("Sessions", [""] + list(session_files))
    if selected:
        session_id = session_files[selected]
        st.session_state.chat_history = load_chat_history(session_id)
        st.session_state.session_id = session_id

# ----------- MAIN UI -----------
st.title("💬 DataOps Chat")

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Your message")
if prompt:
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    lambda_response = requests.post(API_GATEWAY_URL, json={"prompt": prompt}).json()
    reply = lambda_response.get("response", "Sorry, something went wrong.")

    st.session_state.chat_history.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.markdown(reply)

    save_chat_history(st.session_state.session_id, st.session_state.chat_history)

    st.experimental_rerun()
