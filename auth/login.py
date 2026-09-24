import streamlit as st

from auth.auth_service import login
from auth.session import login_user

def login_page():
    st.subheader("🔐 Login")

    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")

    if st.button("Login", use_container_width=True):
        user = login(username, password)

        if user:
            login_user(user)
            st.success("Login successful!")
            st.rerun()
        else:
            st.error("Invalid username or password.")