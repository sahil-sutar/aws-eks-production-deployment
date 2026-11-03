import os
import mysql.connector
from mysql.connector import Error
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)

MYSQL_HOST = os.getenv("MYSQL_HOST", "mysql-service")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "password")
MYSQL_DB = os.getenv("MYSQL_DB", "devopsdb")

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB,
            connection_timeout=3
        )
        return conn
    except Error as e:
        print(f"Database connection error: {e}")
        return None

def init_db():
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DB}")
        cursor.execute(f"USE {MYSQL_DB}")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                content VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
    except Error as e:
        print(f"DB Init Warning: {e}")

# Kubernetes Readiness and Liveness Probes
@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        content = request.form.get("content")
        if content:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO messages (content) VALUES (%s)", (content,))
                conn.commit()
                cursor.close()
                conn.close()
        return redirect(url_for("index"))

    # Fetch messages
    messages = []
    db_status = "Disconnected"
    conn = get_db_connection()
    if conn:
        db_status = "Connected"
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT content, created_at FROM messages ORDER BY id DESC")
        messages = cursor.fetchall()
        cursor.close()
        conn.close()

    return render_template("index.html", messages=messages, db_status=db_status)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)