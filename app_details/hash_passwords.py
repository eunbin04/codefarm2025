import pandas as pd
import hashlib

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

def main():
    df = pd.read_csv("data/users.csv")

    df["password_hash"] = df["password_hash"].apply(hash_password)

    df.to_csv("data/users.csv", index=False)
    print("비밀번호 암호화 완료!")

if __name__ == "__main__":
    main()
