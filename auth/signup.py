
import streamlit as st

from auth.auth_service import create_user


def show_signup():

    st.title("✨ Create Account")

    name = st.text_input("Full Name")

    email = st.text_input("Email")

    password = st.text_input(
        "Password",
        type="password",
    )

    confirm = st.text_input(
        "Confirm Password",
        type="password",
    )

    if st.button("Create Account"):

        if password != confirm:
            st.error("Passwords do not match.")
            return

        ok, msg = create_user(name, email, password)

        if ok:
            st.success(msg)
        else:
            st.error(msg)