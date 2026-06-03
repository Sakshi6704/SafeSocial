import pandas as pd
import re
import string
import pickle

from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report


def clean_text(text):
    text = str(text).lower()
    text = re.sub(r"http\S+|www\S+|https\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"\d+", "", text)
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_text_column(df):
    possible_cols = ["tweet", "text", "comment", "message", "content"]
    for col in possible_cols:
        if col in df.columns:
            return col
    return None


def get_label_column(df):
    possible_cols = ["class", "label", "target", "hate_speech"]
    for col in possible_cols:
        if col in df.columns:
            return col
    return None


def convert_label(value):
    """
    Final binary labels:
    1 = hate
    0 = neutral

    Common mapping:
    labeled_data.csv:
        0 = hate speech
        1 = offensive language
        2 = neither
    So:
        0 or 1 -> 1 (hate)
        2 -> 0 (neutral)
    """
    try:
        value = int(value)
        if value in [0, 1]:
            return 1
        else:
            return 0
    except:
        value = str(value).strip().lower()
        if value in ["hate", "hateful", "offensive", "abusive", "toxic", "1"]:
            return 1
        return 0


def prepare_dataset(file_name):
    df = pd.read_csv(file_name)

    text_col = get_text_column(df)
    label_col = get_label_column(df)

    if text_col is None or label_col is None:
        raise ValueError(
            f"Columns not found in {file_name}. Available columns: {list(df.columns)}"
        )

    df = df[[text_col, label_col]].copy()
    df.columns = ["text", "label"]

    df.dropna(inplace=True)
    df["text"] = df["text"].astype(str).apply(clean_text)
    df = df[df["text"] != ""]

    df["label"] = df["label"].apply(convert_label)

    return df


def main():
    print("Loading datasets...")

    df1 = prepare_dataset("labeled_data.csv")
    df2 = prepare_dataset("train.csv")

    final_df = pd.concat([df1, df2], ignore_index=True)
    final_df.drop_duplicates(subset=["text"], inplace=True)

    print("Final dataset shape:", final_df.shape)
    print("\nLabel counts:")
    print(final_df["label"].value_counts())

    final_df.to_csv("final_dataset.csv", index=False)
    print("\nSaved final_dataset.csv")

    X = final_df["text"]
    y = final_df["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)

    model = LogisticRegression(max_iter=1000, class_weight="balanced")
    model.fit(X_train_vec, y_train)

    y_pred = model.predict(X_test_vec)

    print("\nAccuracy:", accuracy_score(y_test, y_pred))
    print("\nClassification Report:\n")
    print(classification_report(y_test, y_pred))

    with open("vectorizer.pkl", "wb") as f:
        pickle.dump(vectorizer, f)

    with open("model.pkl", "wb") as f:
        pickle.dump(model, f)

    print("Saved vectorizer.pkl")
    print("Saved model.pkl")
    print("\nText model training complete.")


if __name__ == "__main__":
    main()