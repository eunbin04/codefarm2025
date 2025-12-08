import pandas as pd
import hashlib


def load_users():
    return pd.read_csv("data/users.csv")


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def authenticate(username, password, user_df):
    user = user_df[
        (user_df["username"] == username) &
        (user_df["is_active"] == 1)
    ]

    if user.empty:
        return None

    stored_hash = user.iloc[0]["password_hash"]

    if stored_hash == hash_password(password):
        return {
            "username": user.iloc[0]["username"],
            "name": user.iloc[0]["name"],
            "role": user.iloc[0]["role"],
        }

    else:
        return None
