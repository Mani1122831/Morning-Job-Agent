
import bcrypt

from database.database import get_connection


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode(),
        bcrypt.gensalt()
    ).decode()


def verify_password(password: str, hashed: str):
    return bcrypt.checkpw(
        password.encode(),
        hashed.encode()
    )


def create_user(name, email, password):

    conn = get_connection()

    try:
        conn.execute(
            """
            INSERT INTO users(name,email,password_hash)
            VALUES(?,?,?)
            """,
            (name, email, hash_password(password)),
        )

        conn.commit()
        return True, "Account created."

    except Exception:
        return False, "Email already exists."

    finally:
        conn.close()


def authenticate(email, password):

    conn = get_connection()

    user = conn.execute(
        "SELECT * FROM users WHERE email=?",
        (email,),
    ).fetchone()

    conn.close()

    if not user:
        return None

    if verify_password(password, user["password_hash"]):
        return dict(user)

    return None