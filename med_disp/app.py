import os
import psycopg2
from flask import Flask, request, jsonify

app = Flask(__name__)

# Get the database URL from Heroku's environment variables
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

@app.route('/log_dose', methods=['POST'])
def log_dose():
    data = request.get_json()
    if not data or 'event_type' not in data:
        return jsonify({"status": "error", "message": "Invalid data"}), 400

    event_type = data.get('event_type')
    dose_number = data.get('dose_number')

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO dose_log (event_type, dose_number) VALUES (%s, %s)",
                    (event_type, dose_number))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "success", "message": "Log received"}), 201
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run()