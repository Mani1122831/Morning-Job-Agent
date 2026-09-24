
import streamlit as st


def initialize():

    if "user" not in st.session_state:
        st.session_state.user = None


def login(user):
    st.session_state.user = user


def logout():
    st.session_state.user = None


def current_user():
    return st.session_state.user


def is_logged_in():
    return st.session_state.user is not None