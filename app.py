from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from bs4 import BeautifulSoup
import pickle
import joblib
import re
import string
import sqlite3
import os
import pytesseract
import requests
import pandas

from io import BytesIO
from PIL import Image
import numpy as np
import requests
import pdfplumber
import docx
from io import BytesIO
from datetime import datetime
from PIL import Image
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from docx import Document

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

app = Flask(__name__)
app.secret_key = "safesocial_secret_key_123"

DB_FOLDER = r"D:\SafeSocialDB"
DB_PATH = r"D:\SafeSocialDB\database.db"


# ---------------- DATABASE ----------------
# ---------------- DATABASE ----------------

def get_db_connection():

    os.makedirs(DB_FOLDER, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db_connection()

    cursor = conn.cursor()

    # ---------------- USERS TABLE ----------------

    cursor.execute("""

        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT NOT NULL,

            email TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL,

            profile TEXT,

            is_admin INTEGER DEFAULT 0

        )

    """)

    # ---------------- RESULTS TABLE ----------------

    cursor.execute("""

        CREATE TABLE IF NOT EXISTS results (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            input_text TEXT,

            image_name TEXT,

            prediction TEXT NOT NULL,

            hate_confidence REAL,

            neutral_confidence REAL,

            created_at TEXT NOT NULL,

            FOREIGN KEY (user_id) REFERENCES users(id)

        )

    """)

    # ---------------- POSTS TABLE ----------------

    cursor.execute("""

        CREATE TABLE IF NOT EXISTS posts (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT,

            profile TEXT,

            text TEXT,

            image TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP

        )

    """)
    
    # ---------------- REELS TABLE ----------------

    cursor.execute("""

    CREATE TABLE IF NOT EXISTS reels (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT,

        profile TEXT,

        caption TEXT,

        video_path TEXT,

        created_at TEXT DEFAULT CURRENT_TIMESTAMP

    )

""")

    # ---------------- REPORTS TABLE ----------------

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        message TEXT,
        file_path TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
""")
    # ---------------- SAFE ALTERS ----------------
    
    try:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN profile TEXT"
        )
    except:
        pass

    try:
        cursor.execute(
            "ALTER TABLE posts ADD COLUMN username TEXT"
        )
    except:
        pass

    try:
        cursor.execute(
            "ALTER TABLE posts ADD COLUMN profile TEXT"
        )
    except:
        pass

    conn.commit()

    conn.close()


# ---------------- DEFAULT ADMIN ----------------

def create_default_admin():

    conn = get_db_connection()

    cursor = conn.cursor()

    # DELETE old admin

    cursor.execute("""

        DELETE FROM users

        WHERE email = ?

    """, ("admin@gmail.com",))

    # HASH PASSWORD

    hashed_password = generate_password_hash(

        "admin123",

        method="pbkdf2:sha256"

    )

    # DEFAULT PROFILE

    profile = "https://i.pravatar.cc/150?u=admin"

    # CREATE ADMIN

    cursor.execute("""

        INSERT INTO users

        (username, email, password, profile, is_admin)

        VALUES (?, ?, ?, ?, ?)

    """, (

        "admin",

        "admin@gmail.com",

        hashed_password,

        profile,

        1

    ))

    conn.commit()

    conn.close()

    print("Fresh admin created")

# ---------------- TEXT CLEANING ----------------
def clean_text(text):
    text = str(text).lower()
    text = re.sub(r"http\S+|www\S+|https\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"\d+", "", text)
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------- TOXICITY / HIGHLIGHT / EXPLANATION ----------------
BAD_WORDS = [

    "hate",
    "stupid",
    "idiot",
    "kill",
    "ugly",
    "fool",
    "trash",
    "useless",
    "disgusting",
    "worst",
    "die",
    "bad",
    "nonsense",

    "fuck",
    "fucking",
    "bitch",
    "bastard",
    "moron",
    "loser",
    "asshole",
    "shit",
    "fucker",

    "वाईट",
    "मूर्ख",
    "निरुपयोगी",
    "घाणेरडा",
    "तिरस्कार",
    "बेवकूफ",
    "मर",
    "नालायक",
    "मार",
    "मारून"
]

def get_toxicity_level(hate_conf):
    if hate_conf >= 70:
        return "High Toxicity"
    elif hate_conf >= 30:
        return "Medium Toxicity"
    else:
        return "Low Toxicity"


def highlight_bad_words(text):
    words = text.split()
    highlighted = []

    for word in words:
        clean_word = re.sub(r"[^\w\u0900-\u097F]", "", word.lower())

        if clean_word in BAD_WORDS:
            highlighted.append(
                f"<span style='color:#ef4444;font-weight:bold;background:rgba(239,68,68,0.15);padding:2px 5px;border-radius:5px;'>{word}</span>"
            )
        else:
            highlighted.append(word)

    return " ".join(highlighted)


def get_ai_explanation(prediction):
    if prediction == "Hate":
        return "Detected because the content contains harmful or toxic patterns."
    elif prediction == "Neutral":
        return "Detected as neutral because the text does not strongly match harmful patterns."
    return "The system is not fully confident, so this content may need manual review."


def get_threat_severity(prediction, hate_conf, text):
    text_lower = text.lower()
    violent_words = ["kill", "die", "attack", "murder", "मर", "मार", "मारून"]

    if any(word in text_lower for word in violent_words):
        return "Violent Threat"
    elif prediction == "Hate" and hate_conf >= 70:
        return "Dangerous"
    elif prediction == "Hate":
        return "Offensive"
    else:
        return "Safe"


def generate_safe_reply(prediction, severity):
    if prediction == "Hate":
        if severity == "Violent Threat":
            return "Please avoid threatening language. Let’s keep the conversation safe and respectful."
        return "Please use respectful language. Let’s keep the conversation positive."
    return "No reply needed. The content appears safe."

def sanitize_hate_text(text):

    replacements = {

        "hate": "dislike",
        "idiot": "person",
        "stupid": "unwise",
        "ugly": "not appropriate",
        "fool": "person",
        "trash": "not good",
        "useless": "not helpful",
        "disgusting": "unpleasant",
        "worst": "not good",
        "kill": "avoid",
        "die": "stop",

        "वाईट": "योग्य नाही",
        "मूर्ख": "व्यक्ती",
        "निरुपयोगी": "उपयोगी नाही",
        "घाणेरडा": "अयोग्य",
        "तिरस्कार": "नापसंती",
        "बेवकूफ": "व्यक्ती",
        "नालायक": "योग्य नाही",
        "मर": "थांब",
        "मार": "थांब"

    }

    words = text.split()

    sanitized_words = []

    for word in words:

        clean_word = re.sub(
            r"[^\w\u0900-\u097F]",
            "",
            word.lower()
        )

        if clean_word in replacements:

            sanitized_words.append(
                replacements[clean_word]
            )

        else:

            sanitized_words.append(word)

    return " ".join(sanitized_words)


# ---------------- LOAD MODELS ----------------
# ---------------- LOAD MODELS ----------------

# ---------------- LOAD MODELS ----------------

# ---------------- LOAD MODELS ----------------

# text_model = joblib.load("model.pkl")
# vectorizer = joblib.load("vectorizer.pkl")

text_model = joblib.load("model.pkl")
vectorizer = joblib.load("vectorizer.pkl")

print("✅ Lightweight OCR Mode Active")

# ---------------- EXTRACT IMAGE FROM URL ----------------

def extract_image_from_url(page_url):

    try:

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            page_url,
            headers=headers,
            timeout=10
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        img_tag = soup.find("img")

        if not img_tag:
            return None

        img_url = img_tag.get("src")

        return img_url

    except Exception as e:

        print("Image extraction error:", e)

        return None

# ---------------- PAGE ROUTES ----------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not email or not password:
            return render_template("signup.html", message="All fields are required")

        hashed_password = generate_password_hash(password)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (username, email, password, is_admin)
                VALUES (?, ?, ?, ?)
            """, (username, email, hashed_password, 0))
            conn.commit()
            conn.close()
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            return render_template("signup.html", message="Email already exists")

    return render_template("signup.html", message=None)


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip()

        password = request.form.get("password", "").strip()

        conn = get_db_connection()

        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        )

        user = cursor.fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]

            session["username"] = user["username"]

            session["profile"] = "https://i.pravatar.cc/150?img=32"

            session["is_admin"] = user["is_admin"]

            if user["is_admin"] == 1:

                return redirect(
                    url_for("admin_dashboard")
                )

            return redirect(
                url_for("dashboard")
            )

        return render_template(
            "login.html",
            message="Invalid email or password"
        )

    return render_template(
        "login.html",
        message=None
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") == 1:
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT prediction, COUNT(*) as count
        FROM results
        WHERE user_id = ?
        GROUP BY prediction
    """, (session["user_id"],))
    data = cursor.fetchall()
    conn.close()

    hate_count = neutral_count = uncertain_count = 0

    for row in data:
        if row["prediction"] == "Hate":
            hate_count = row["count"]
        elif row["prediction"] == "Neutral":
            neutral_count = row["count"]
        elif row["prediction"] == "Uncertain":
            uncertain_count = row["count"]

    return render_template(
        "dashboard.html",
        username=session["username"],
        hate_count=hate_count,
        neutral_count=neutral_count,
        uncertain_count=uncertain_count
    )


@app.route("/admin")
def admin_dashboard():

    if "user_id" not in session or session.get("is_admin") != 1:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # ---------------- USERS COUNT ----------------
    cursor.execute("SELECT COUNT(*) as total FROM users")
    total_users = cursor.fetchone()["total"]

    # ---------------- RESULTS COUNT ----------------
    cursor.execute("SELECT COUNT(*) as total FROM results")
    total_results = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM results WHERE prediction = 'Hate'")
    hate_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM results WHERE prediction = 'Neutral'")
    neutral_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM results WHERE prediction = 'Uncertain'")
    uncertain_count = cursor.fetchone()["total"]

    # ---------------- RECENT DETECTIONS ----------------
    cursor.execute("""
        SELECT user_id, input_text, image_name, prediction,
               hate_confidence, neutral_confidence, created_at
        FROM results
        ORDER BY id DESC
        LIMIT 10
    """)
    recent_results = cursor.fetchall()

    # ---------------- REPORTS (NEW FEATURE) ----------------
    cursor.execute("""
        SELECT *
        FROM reports
        ORDER BY id DESC
        LIMIT 20
    """)
    reports = cursor.fetchall()

    conn.close()

    return render_template(
        "admin.html",

        total_users=total_users,
        total_results=total_results,
        hate_count=hate_count,
        neutral_count=neutral_count,
        uncertain_count=uncertain_count,

        recent_results=recent_results,
        reports=reports
    )


@app.route("/detect")
def detect():
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("detect.html", username=session["username"])


@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT input_text, image_name, prediction, hate_confidence, neutral_confidence, created_at
        FROM results
        WHERE user_id = ?
        ORDER BY id DESC
    """, (session["user_id"],))
    records = cursor.fetchall()
    conn.close()

    return render_template("history.html", records=records)

@app.route("/feed_home")
def feed_home():

    return render_template(
        "feed_home.html"
    )
    
@app.route("/feed")
def feed():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM posts ORDER BY id DESC")
    posts = cursor.fetchall()

    conn.close()

    return render_template("feed.html", posts=posts)

# ---------------- TEXT PREDICTION ----------------
# ---------------- TEXT PREDICTION ----------------
@app.route("/predict", methods=["POST"])
def predict():
    try:
        if "user_id" not in session:
            return jsonify({"error": "Please login first"}), 401

        data = request.get_json()

        if not data or "text" not in data:
            return jsonify({"error": "No text provided"}), 400

        user_text = data["text"].strip()

        if not user_text:
            return jsonify({"error": "Empty text"}), 400

        cleaned_text = clean_text(user_text)
        vectorized_text = vectorizer.transform([cleaned_text])

        prediction = text_model.predict(vectorized_text)[0]

        if hasattr(text_model, "predict_proba"):
            probabilities = text_model.predict_proba(vectorized_text)[0]
            neutral_conf = round(float(probabilities[0]) * 100, 2)
            hate_conf = round(float(probabilities[1]) * 100, 2)
        else:
            if prediction == 1:
                hate_conf = 100.0
                neutral_conf = 0.0
            else:
                hate_conf = 0.0
                neutral_conf = 100.0

        result = "Hate" if prediction == 1 else "Neutral"

        toxicity = get_toxicity_level(hate_conf)
        highlighted_text = highlight_bad_words(user_text)
        explanation = get_ai_explanation(result)
        severity = get_threat_severity(result, hate_conf, user_text)
        safe_reply = generate_safe_reply(result, severity)
        sanitized_text = sanitize_hate_text(user_text)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO results
            (user_id, input_text, image_name, prediction, hate_confidence, neutral_confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            user_text,
            None,
            result,
            hate_conf,
            neutral_conf,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()

        return jsonify({
            "prediction": result,
            "toxicity": toxicity,
            "severity": severity,
            "highlighted_text": highlighted_text,
            "explanation": explanation,
            "safe_reply": safe_reply,
            "hate_confidence": hate_conf,
            "neutral_confidence": neutral_conf,
            "sanitized_text": sanitized_text,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
# # ---------------- IMAGE UPLOAD PREDICTION ----------------
# @app.route("/predict_image", methods=["POST"])
# def predict_image():

#     try:

#         if "user_id" not in session:
#             return jsonify({
#                 "error": "Please login first"
#             }), 401

#         if "image" not in request.files:
#             return jsonify({
#                 "error": "No image uploaded"
#             }), 400

#         file = request.files["image"]

#         if file.filename == "":
#             return jsonify({
#                 "error": "No selected image"
#             }), 400

#         img = Image.open(file)

#         extracted_text = pytesseract.image_to_string(img)

#         cleaned_text = clean_text(extracted_text)

#         result = "Neutral"

#         for word in BAD_WORDS:

#             if word.lower() in cleaned_text.lower():

#                 result = "Hate"
#                 break

#         if result == "Hate":

#             hate_conf = 95
#             neutral_conf = 5

#         else:

#             hate_conf = 5
#             neutral_conf = 95

#         toxicity = get_toxicity_level(hate_conf)

#         severity = get_threat_severity(
#             result,
#             hate_conf,
#             extracted_text
#         )

#         safe_reply = generate_safe_reply(
#             result,
#             severity
#         )

#         conn = get_db_connection()
#         cursor = conn.cursor()

#         cursor.execute("""
#             INSERT INTO results
#             (
#                 user_id,
#                 input_text,
#                 image_name,
#                 prediction,
#                 hate_confidence,
#                 neutral_confidence,
#                 created_at
#             )
#             VALUES (?, ?, ?, ?, ?, ?, ?)
#         """, (
#             session["user_id"],
#             extracted_text,
#             file.filename,
#             result,
#             hate_conf,
#             neutral_conf,
#             datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         ))

#         conn.commit()
#         conn.close()

#         return jsonify({

#             "prediction": result,

#             "extracted_text": extracted_text,

#             "toxicity": toxicity,

#             "severity": severity,

#             "safe_reply": safe_reply

#         })

#     except Exception as e:

#         return jsonify({
#             "error": str(e)
#         }), 500
# # ---------------- IMAGE URL PREDICTION ----------------

# @app.route("/predict_document", methods=["POST"])
# def predict_document():

#     try:

#         if "document" not in request.files:

#             return jsonify({
#                 "error": "No document uploaded"
#             })

#         file = request.files["document"]

#         text = ""

#         # TXT
#         if file.filename.endswith(".txt"):

#             text = file.read().decode("utf-8")

#         # PDF
#         elif file.filename.endswith(".pdf"):

#             with pdfplumber.open(file) as pdf:

#                 for page in pdf.pages:

#                     extracted = page.extract_text()

#                     if extracted:

#                         text += extracted + " "

#         # DOCX
#         elif file.filename.endswith(".docx"):

#             doc = Document(file)

#             for para in doc.paragraphs:

#                 text += para.text + " "

#         else:

#             return jsonify({
#                 "error": "Unsupported file format"
#             })

#         cleaned_text = clean_text(text)

#         # Rule-based bad word detection
#         found_bad_words = []

#         for word in BAD_WORDS:

#             if word.lower() in text.lower():

#                 found_bad_words.append(word)

#         if len(found_bad_words) > 0:

#             result = "Hate"
#             hate_conf = 90

#         else:

#             vectorized = vectorizer.transform([cleaned_text])

#             prediction = text_model.predict(vectorized)[0]

#             if prediction == 1:

#                 result = "Hate"
#                 hate_conf = 80

#             else:

#                 result = "Neutral"
#                 hate_conf = 10

#         toxicity = get_toxicity_level(hate_conf)

#         severity = get_threat_severity(
#             result,
#             hate_conf,
#             text
#         )

#         highlighted = highlight_bad_words(text[:1000])

#         explanation = get_ai_explanation(result)

#         safe_reply = generate_safe_reply(
#             result,
#             severity
#         )

#         sanitized_text = sanitize_hate_text(text)

#         return jsonify({

#             "prediction": result,

#             "toxicity": toxicity,

#             "severity": severity,

#             "highlighted_text": highlighted,

#             "explanation": explanation,

#             "safe_reply": safe_reply,

#             "sanitized_text": sanitized_text

#         })

#     except Exception as e:

#         return jsonify({
#             "error": str(e)
#         })
        
@app.route("/detect_feed_image", methods=["POST"])
def detect_feed_image():

    try:

        data = request.get_json()

        image_path = data["image"]

        print("IMAGE PATH:", image_path)

        # URL IMAGE
        if "http" in image_path:

            response = requests.get(image_path)

            img = Image.open(
                BytesIO(response.content)
            )

        # UPLOADED IMAGE
        else:

            local_path = os.path.join(
                "static",
                image_path
            )

            print("LOCAL PATH:", local_path)

            img = Image.open(local_path)

            # OCR IMPROVEMENT
            img = img.convert("L")

            img = img.point(
    lambda x: 0 if x < 140 else 255,
    '1'
)
        # OCR
        extracted_text = pytesseract.image_to_string(
    img,
    config='--psm 6'
)

        print("EXTRACTED TEXT:", extracted_text)

        if extracted_text.strip() == "":

         return jsonify({
        "prediction": "Neutral",
        "extracted_text": ""
    })

        cleaned = clean_text(extracted_text)

        print("CLEANED TEXT:", cleaned)

        return jsonify({
                "prediction": "Neutral",
                "extracted_text": ""
            })

        cleaned = clean_text(extracted_text)

        result = "Neutral"

        for word in BAD_WORDS:

            if word.lower() in cleaned.lower():

                result = "Hate"
                break

        return jsonify({

            "prediction": result,

            "extracted_text": extracted_text

        })

    except Exception as e:

        print("ERROR:", e)

        return jsonify({
            "error": str(e)
        }), 500

@app.route("/add_post", methods=["POST"])
def add_post():

    try:

        text = request.form.get("text")
        image_url = request.form.get("image_url")

        image_path = ""

        # IMAGE FILE
        if "image_file" in request.files:

            file = request.files["image_file"]

            if file.filename != "":

                upload_folder = os.path.join(
                    "static",
                    "uploads"
                )

                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)

                filename = secure_filename(file.filename)

                save_path = os.path.join(
                    upload_folder,
                    filename
                )

                file.save(save_path)

                # SAVE PATH IN DATABASE
                image_path = "uploads/" + filename

        # IMAGE URL
        elif image_url:

            response = requests.get(image_url)

            if response.status_code == 200:

                upload_folder = os.path.join(
                    "static",
                    "uploads"
                )

                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)

                filename = "url_image_" + str(
                    int(datetime.now().timestamp())
                ) + ".jpg"

                save_path = os.path.join(
                    upload_folder,
                    filename
                )

                with open(save_path, "wb") as f:
                    f.write(response.content)

                # SAVE LOCAL PATH
                image_path = "uploads/" + filename

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO posts
            (text, image, created_at)
            VALUES (?, ?, ?)
        """, (
            text,
            image_path,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()

        return jsonify({
            "message": "Post added successfully"
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        })
        
        
@app.route("/delete_post/<int:post_id>", methods=["DELETE"])
def delete_post(post_id):

    try:

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM posts WHERE id=?",
            (post_id,)
        )

        conn.commit()
        conn.close()

        return jsonify({
            "success": True
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        })
 
@app.route("/search")
def search():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, username
        FROM users
        ORDER BY id DESC
    """)

    users = cursor.fetchall()

    conn.close()

    return render_template(
        "search.html",
        users=users
    )
    
@app.route("/search_user")
def search_user():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, username
        FROM users
        ORDER BY id DESC
    """)

    users = cursor.fetchall()

    conn.close()

    return render_template(
        "search_user.html",
        users=users
    )
    
@app.route("/create_post", methods=["GET", "POST"])
def create_post():

    if request.method == "POST":

        text = request.form.get("text")

        image = request.files.get("image")

        username = session.get("username")

        profile = session.get("profile")

        image_path = ""

        # IMAGE SAVE
        if image and image.filename != "":

            upload_folder = os.path.join(
                "static",
                "uploads"
            )

            os.makedirs(upload_folder, exist_ok=True)

            filename = secure_filename(image.filename)

            save_path = os.path.join(
                upload_folder,
                filename
            )

            image.save(save_path)

            image_path = "uploads/" + filename

        # DATABASE
        conn = get_db_connection()

        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO posts
            (username, profile, text, image)
            VALUES (?, ?, ?, ?)
        """, (
            username,
            profile,
            text,
            image_path
        ))

        conn.commit()

        conn.close()

        return redirect("/feed")

    return render_template("create_post.html")

@app.route("/like_post/<int:post_id>", methods=["POST"])
def like_post(post_id):

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        "SELECT likes FROM posts WHERE id=?",
        (post_id,)
    )

    post = cur.fetchone()

    likes = post["likes"] + 1

    cur.execute(
        "UPDATE posts SET likes=? WHERE id=?",
        (likes, post_id)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "liked": True,
        "likes": likes
    })
    
@app.route("/report", methods=["GET", "POST"])
def report():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        message = request.form.get("message")
        file = request.files.get("file")

        file_path = ""

        # optional file save
        if file and file.filename != "":

            folder = os.path.join("static", "reports")
            os.makedirs(folder, exist_ok=True)

            filename = secure_filename(file.filename)
            save_path = os.path.join(folder, filename)

            file.save(save_path)

            file_path = "reports/" + filename

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO reports (user_id, username, message, file_path)
            VALUES (?, ?, ?, ?)
        """, (
            session["user_id"],
            session["username"],
            message,
            file_path
        ))

        conn.commit()
        conn.close()

        return render_template("report.html", success="Report submitted successfully!")

    return render_template("report.html")    

@app.route("/admin_reports")
def admin_reports():

    if "user_id" not in session or session.get("is_admin") != 1:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM reports
        ORDER BY id DESC
    """)

    reports = cursor.fetchall()
    conn.close()

    return render_template("admin_reports.html", reports=reports)

@app.route("/delete_report/<int:report_id>", methods=["POST"])
def delete_report(report_id):

    if "user_id" not in session or session.get("is_admin") != 1:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM reports WHERE id=?", (report_id,))

    conn.commit()
    conn.close()

    return redirect("/admin_reports")
@app.route("/report_problem", methods=["POST"])
def report_problem():

    message = request.form.get("message")
    image = request.files.get("image")

    image_path = ""

    if image and image.filename:

        upload_folder = os.path.join(
            "static",
            "reports"
        )

        os.makedirs(upload_folder, exist_ok=True)

        filename = secure_filename(image.filename)

        image.save(
            os.path.join(upload_folder, filename)
        )

        image_path = "reports/" + filename

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO reports
        (username,message,image,created_at)
        VALUES (?,?,?,?)
    """,(
        session.get("username"),
        message,
        image_path,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True
    })
    
@app.route("/reels")
def reels():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM reels
        ORDER BY id DESC
    """)

    reels = cursor.fetchall()

    conn.close()

    return render_template(
        "reels.html",
        reels=reels
    )    
    
@app.route("/create_reel", methods=["GET"])
def create_reel():
    return render_template("create_reel.html")
    
# ---------------- RUN APP ----------------
if __name__ == "__main__":

    init_db()

    create_default_admin()

    app.run(
        debug=True,
        use_reloader=False
    )