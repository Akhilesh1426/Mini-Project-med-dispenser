import os
import psycopg2
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Get the database URL from environment variables
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

@app.route('/api/events', methods=['GET'])
def get_events():
    """
    Get all dose log events with optional date filtering
    Query params:
    - start_date: YYYY-MM-DD (optional)
    - end_date: YYYY-MM-DD (optional)
    - limit: number of records to return (default: 100)
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        limit = request.args.get('limit', 100)

        conn = get_db_connection()
        cur = conn.cursor()

        query = "SELECT id, event_type, dose_number, timestamp FROM dose_log WHERE 1=1"
        params = []

        if start_date:
            query += " AND timestamp >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND timestamp <= %s"
            params.append(end_date + ' 23:59:59')  # Include entire end date
        
        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()
        
        events = []
        for row in rows:
            events.append({
                'id': row[0],
                'event_type': row[1],
                'dose_number': row[2],
                'timestamp': row[3].isoformat() if row[3] else None
            })
        
        cur.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "count": len(events),
            "events": events
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """
    Get aggregated statistics about dose adherence
    Query params:
    - days: number of days to look back (default: 30)
    """
    try:
        days = int(request.args.get('days', 30))
        
        conn = get_db_connection()
        cur = conn.cursor()

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Get total counts
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN event_type = 'TAKEN' THEN 1 ELSE 0 END) as taken,
                SUM(CASE WHEN event_type = 'MISSED' THEN 1 ELSE 0 END) as missed
            FROM dose_log
            WHERE timestamp >= %s AND timestamp <= %s
        """, (start_date, end_date))
        
        counts = cur.fetchone()
        total = counts[0] or 0
        taken = counts[1] or 0
        missed = counts[2] or 0

        # Calculate adherence percentage
        adherence_percentage = (taken / total * 100) if total > 0 else 0

        # Get daily data for streak calculation
        cur.execute("""
            SELECT 
                DATE(timestamp) as date,
                COUNT(*) as total_doses,
                SUM(CASE WHEN event_type = 'TAKEN' THEN 1 ELSE 0 END) as taken_doses
            FROM dose_log
            WHERE timestamp >= %s AND timestamp <= %s
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
        """, (start_date, end_date))
        
        daily_data = cur.fetchall()

        # Calculate current streak and best streak
        current_streak = 0
        best_streak = 0
        temp_streak = 0

        for day_data in daily_data:
            total_doses = day_data[1]
            taken_doses = day_data[2]
            
            # A day is considered "complete" if all 3 doses were taken
            if taken_doses >= 3:  # Full adherence for the day
                temp_streak += 1
                if temp_streak > best_streak:
                    best_streak = temp_streak
            else:
                temp_streak = 0
        
        # Current streak is the temp_streak if still going
        current_streak = temp_streak

        # Get events by day for visualization
        cur.execute("""
            SELECT 
                DATE(timestamp) as date,
                event_type,
                COUNT(*) as count
            FROM dose_log
            WHERE timestamp >= %s AND timestamp <= %s
            GROUP BY DATE(timestamp), event_type
            ORDER BY date DESC
        """, (start_date, end_date))
        
        daily_events = cur.fetchall()
        
        # Format daily events
        events_by_day = {}
        for row in daily_events:
            date_str = row[0].isoformat()
            event_type = row[1]
            count = row[2]
            
            if date_str not in events_by_day:
                events_by_day[date_str] = {'taken': 0, 'missed': 0}
            
            if event_type == 'TAKEN':
                events_by_day[date_str]['taken'] = count
            elif event_type == 'MISSED':
                events_by_day[date_str]['missed'] = count

        cur.close()
        conn.close()

        return jsonify({
            "status": "success",
            "period_days": days,
            "statistics": {
                "total_doses": total,
                "doses_taken": taken,
                "doses_missed": missed,
                "adherence_percentage": round(adherence_percentage, 2),
                "current_streak": current_streak,
                "best_streak": best_streak
            },
            "daily_breakdown": events_by_day
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/dashboard', methods=['GET'])
def dashboard():
    """Serve the visualization dashboard HTML page"""
    try:
        return send_file('dashboard.html')
    except Exception as e:
        return jsonify({"status": "error", "message": "Dashboard not found"}), 404

@app.route('/', methods=['GET'])
def home():
    """API home page"""
    return jsonify({
        "service": "Medicine Dispenser API",
        "version": "1.0",
        "endpoints": {
            "POST /log_dose": "Log a dose event (TAKEN or MISSED)",
            "GET /api/events": "Retrieve dose log events",
            "GET /api/statistics": "Get adherence statistics",
            "GET /dashboard": "View visualization dashboard"
        }
    }), 200

if __name__ == '__main__':
    app.run()
