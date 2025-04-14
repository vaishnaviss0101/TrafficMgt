import gevent.monkey
gevent.monkey.patch_all()  # Patch for Windows compatibility
from random import random
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_session import Session
from flask_socketio import SocketIO, emit
from flask_cors import CORS  # Import CORS
import datetime
app = Flask(__name__)
app.secret_key = 'acbdffd23'
CORS(app)
# Configure session
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# WebSocket Setup
socketio = SocketIO(app, async_mode="gevent", cors_allowed_origins="*")

app.config['OPENWEATHERMAP_API_KEY'] = '45d2ef85f5b17e7ccfd9bef596e2b2c4'

def get_db_connection():
    return psycopg2.connect(
        dbname="trafficmanagement",
        user="postgres",
        password="supekar@75",
        host="localhost",
        port="5432"
    )

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, first_name, last_name, email, role):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, first_name, last_name, email, role FROM users WHERE id = %s", (user_id,))
    user_data = cur.fetchone()
    cur.close()
    conn.close()
    if user_data:
        return User(*user_data)
    return None

# ----------------------
# Authentication Routes
# ----------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, first_name, last_name, email, password, role FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password_hash(user[4], password):
            user_obj = User(user[0], user[1], user[2], user[3], user[5])
            login_user(user_obj)
            # Store values in session
            session["user_id"] = user_obj.id
            session["role"] = user_obj.role
            session["user_name"] = f"{user_obj.first_name} {user_obj.last_name}"
            flash(f'Welcome {user_obj.first_name} {user_obj.last_name}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name  = request.form['last_name']
        email      = request.form['email']
        phone      = request.form['phone']
        password   = request.form['password']
        role       = request.form['role']
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE email = %s', (email,))
        if cursor.fetchone():
            flash('Email already registered', 'error')
            return render_template('register.html')

        cursor.execute(
            'INSERT INTO users (first_name, last_name, email, phone, password, role) VALUES (%s, %s, %s, %s, %s, %s)',
            (first_name, last_name, email, phone, hashed_password, role)
        )
        conn.commit()
        cursor.close()
        conn.close()

        flash('User registered successfully!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/home')
@login_required
def home():
    return render_template('base.html', user_id=session.get("user_id"), role=session.get("role"))

# ----------------------
# GPS Tracking Routes
# ----------------------
@app.route('/gps')
@login_required
def gps():
    return render_template('gps-tracking.html', user_id=session.get("user_id"))

@app.route('/update-location', methods=['POST'])
@login_required
def update_location():
    data = request.get_json()
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    if not latitude or not longitude:
        return jsonify({"error": "Missing location data"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''INSERT INTO locations (user_id, latitude, longitude, timestamp) 
               VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
               ON CONFLICT (user_id) 
               DO UPDATE SET latitude = EXCLUDED.latitude, 
                             longitude = EXCLUDED.longitude, 
                             timestamp = CURRENT_TIMESTAMP''',
            (session.get("user_id"), latitude, longitude)
        )

        conn.commit()
        # Emit location update to all connected clients
        socketio.emit("location_update", {
            "user_id": session.get("user_id"),
            "latitude": latitude,
            "longitude": longitude
        })
        return jsonify({"status": "success", "message": "Location updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/get-locations')
@login_required
def get_locations():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.user_id, u.first_name, u.last_name, l.latitude, l.longitude
        FROM locations l
        JOIN users u ON l.user_id = u.id
    """)
    locations = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([
        {
            "user_id": loc[0],
            "name": f"{loc[1]} {loc[2]}",
            "latitude": loc[3],
            "longitude": loc[4]
        }
        for loc in locations
    ])

@app.route('/track')
@login_required
def track():
    return render_template('track.html', user_id=session.get("user_id"))

# ----------------------
# Traffic Updates Routes
# ----------------------
# Fetch live traffic data using TomTom Traffic API with dynamic point concatenation
# Route to fetch live traffic data from TomTom
@app.route('/get_traffic_data', methods=['GET'])
def get_traffic_data():
    lat = request.args.get('lat')
    lon = request.args.get('lon')

    # Replace with your actual TomTom API key
    api_key = "xwZEOc3WWeXltxv7Na5aSfhJZCvPs0Ar"
    url = f"https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json?point={lat},{lon}&key={api_key}"

    # Make the request to TomTom API
    response = requests.get(url)

    if response.status_code == 200:
        return jsonify(response.json())  # Send TomTom response to the front-end
    else:
        return jsonify({"error": "Failed to fetch traffic data"}), 500

@app.route("/report-traffic", methods=["POST"])
def report_traffic():
    user_id = session.get("user_id")
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO traffic (origin, destination, congestion_level, road_status, accident_report, user_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (data["origin"], data["destination"], data["congestion_level"], data["road_status"], data["accident_report"], user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Traffic report added successfully"}), 201


@app.route("/get-traffic-updates")
def get_traffic_updates():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Read origin and destination query parameters
    origin = request.args.get("origin")
    destination = request.args.get("destination")

    if origin and destination:
        # Optionally, filter traffic records by origin/destination if desired
        cursor.execute("""
            SELECT origin, destination, congestion_level, road_status, accident_report, id 
            FROM traffic 
            WHERE origin = %s AND destination = %s
        """, (origin, destination))
    else:
        cursor.execute("""
            SELECT origin, destination, congestion_level, road_status, accident_report, id
            FROM traffic
        """)
    db_traffic = cursor.fetchall()
    cursor.close()
    conn.close()

    traffic_data = [
        {"origin": row[0], "destination": row[1], "congestion_level": row[2],
         "road_status": row[3], "accident_report": row[4], "id": row[5]}
        for row in db_traffic
    ]
    # If you don't have live traffic data, you can return an empty object
    live_traffic = {}
    return jsonify({"db_traffic": traffic_data, "live_traffic": live_traffic})

@app.route("/delete-traffic/<int:id>", methods=["DELETE"])
def delete_traffic(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM traffic WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Traffic record deleted successfully"}), 200


@app.route('/traffic-updates')
@login_required
def traffic_updates():
    return render_template('traffic_updates.html', user_id=session.get("user_id"))

@app.route('/route-recommendation')
@login_required
def route_recommendation():
    return render_template('route_recommendation.html', user_id=session.get("user_id"))

# Route to display the contact page
@app.route('/contact')
def contact():
    return render_template("contact.html")

@app.route('/get-support-queries', methods=['GET'])
def get_support_queries():
    """Retrieve submitted support queries based on user role"""
    try:
        user_id = session.get("user_id")

        role = session.get("role")  # Get user role from session

        if not user_id:
            return jsonify({"error": "Unauthorized access"}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        # Query condition: Regular user sees only their own, ADMIN sees all
        if role == "ADMIN":
            cursor.execute("""
                SELECT sq.id, sq.name, sq.email, sq.message, sq.submitted_at, 
                       CONCAT(u.first_name, ', ', u.last_name) AS submitted_by
                FROM support_queries sq
                LEFT JOIN users u ON sq.user_id = u.id
                ORDER BY sq.submitted_at DESC;
            """)
        else:
            cursor.execute("""
                SELECT sq.id, sq.name, sq.email, sq.message, sq.submitted_at, 
                 CONCAT(u.first_name, ', ', u.last_name) AS submitted_by
                FROM support_queries sq
                FROM support_queries sq
                LEFT JOIN users u ON sq.user_id = u.id
                WHERE sq.user_id = %s
                ORDER BY sq.submitted_at DESC;
            """, (user_id,))

        queries = cursor.fetchall()
        conn.close()

        # Manually convert list of tuples to list of dictionaries
        query_list = [
            {
                "id": row[0],
                "name": row[1],
                "email": row[2],
                "message": row[3],
                "submitted_at": row[4].isoformat() if row[4] else None,
                "submitted_by": row[5] if row[5] else "Unknown"
            }
            for row in queries
        ]

        return jsonify(query_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to submit support queries
@app.route('/submit-support', methods=['POST'])
def submit_support():
    """Save user queries to the database"""
    try:
        data = request.get_json()
        name = data.get("name")
        email = data.get("email")
        message = data.get("message")
        user_id = session.get("user_id")  # Fetch user ID from session

        if not name or not email or not message:
            return jsonify({"error": "All fields are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO support_queries (user_id, name, email, message) VALUES (%s, %s, %s, %s)",
            (user_id, name, email, message)
        )
        conn.commit()
        conn.close()

        return jsonify({"success": "Your query has been submitted successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to display transport tracker page
@app.route('/transport-tracker')
def transport_tracker():
    return render_template('transport_tracker.html')

# Function to fetch route data from PostgreSQL
def get_route_from_db(transport_type, route_number):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT start_lat, start_lng, end_lat, end_lng
                   FROM routes
                   WHERE transport_type = %s AND route_number = %s''',
                (transport_type, route_number))
    route = cur.fetchone()
    conn.close()

    if route:
        return {
            "start_lat": route[0],
            "start_lng": route[1],
            "end_lat": route[2],
            "end_lng": route[3]
        }
    else:
        return None

# Route to get transport data from the database and call TomTom API
@app.route('/get_transport_data/<transport_type>/<route_number>')
def get_transport_data(transport_type, route_number):
    route_data = get_route_from_db(transport_type, route_number)

    if not route_data:
        return jsonify({"error": "Route not found for the given transport type."}), 404

    start_lat = route_data["start_lat"]
    start_lng = route_data["start_lng"]
    end_lat = route_data["end_lat"]
    end_lng = route_data["end_lng"]

    tomtom_api_key = "xwZEOc3WWeXltxv7Na5aSfhJZCvPs0Ar"
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_lat},{start_lng}:{end_lat},{end_lng}/json?key={tomtom_api_key}"

    try:
        response = requests.get(url)
        if response.status_code == 200:
            route_data = response.json()

            # Extract coordinates for the route from the response
            route_coordinates = route_data.get("routes", [{}])[0].get("legs", [{}])[0].get("points", [])

            if route_coordinates:
                # Prepare the coordinates in the format expected by frontend (lat, lng)
                coordinates = [{"lat": point["latitude"], "lng": point["longitude"]} for point in route_coordinates]

                # Return the coordinates to frontend
                return jsonify({
                    "coordinates": coordinates,
                    "eta": route_data["routes"][0]["summary"]["arrivalTime"],  # Estimated Arrival Time
                    "status": "On time"  # Example status, could be dynamic
                })
            else:
                return jsonify({"error": "No coordinates found in the route data."}), 404
        else:
            return jsonify(
                {"error": f"Failed to fetch data from TomTom API: {response.status_code}"}), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"error": "An error occurred while fetching data from TomTom API"}), 500

# Route to simulate transport data for testing
@app.route('/simulate_transport_data', methods=['POST'])
def simulate_transport_data():
    transport_type = request.json.get('transport_type')
    route_number = request.json.get('route_number')

    lat = random.uniform(18.50, 18.55)
    lng = random.uniform(73.85, 73.90)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO public_transport (transport_type, route_number, lat, lng)
        VALUES (%s, %s, %s, %s);
    ''', (transport_type, route_number, lat, lng))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Simulated transport data added successfully."})

# Route to fetch all transport data
@app.route('/all_transport_data', methods=['GET'])
def all_transport_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        'SELECT transport_type, route_number, lat, lng, timestamp FROM public_transport ORDER BY timestamp DESC LIMIT 10')
    transport_data = cursor.fetchall()

    cursor.close()
    conn.close()

    if transport_data:
        return jsonify([{
            "transport_type": row[0],
            "route_number": row[1],
            "lat": row[2],
            "lng": row[3],
            "timestamp": row[4]
        } for row in transport_data])
    else:
        return jsonify({"error": "No data available."}), 404



# Fetch weather data from OpenWeatherMap
def get_weather_data(city):
    api_key = app.config['OPENWEATHERMAP_API_KEY']
    url = f'http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric'
    response = requests.get(url)
    data = response.json()
    return data


@app.route('/weather', methods=['GET', 'POST'])
def weather():
    user_id = session.get("user_id")
    role = session.get("role")
    weather_data = None
    weather_history = None

    # Fetch weather history from the database (for displaying in the table)
    conn = get_db_connection()
    cursor = conn.cursor()

    if role == "ADMIN":
        cursor.execute('SELECT * FROM weather_data ORDER BY timestamp DESC LIMIT 10')
    else:
        cursor.execute('SELECT * FROM weather_data WHERE user_id = %s ORDER BY timestamp DESC LIMIT 10', (user_id,))

    weather_history = cursor.fetchall()
    cursor.close()
    conn.close()

    # Handle POST request (when user submits the city)
    if request.method == 'POST':
        city = request.form['city']
        data = get_weather_data(city)

        # If the data is valid (city found)
        if data['cod'] == 200:
            weather_main = data['weather'][0]['main']
            temp = data['main']['temp']
            humidity = data['main']['humidity']
            description = data['weather'][0]['description']
            wind_speed = data['wind']['speed']

            # Weather impact logic (this can be expanded further)
            if weather_main in ['Rain', 'Snow', 'Fog']:
                traffic_signal_change = True
                road_condition = "Hazardous"
            else:
                traffic_signal_change = False
                road_condition = "Clear"

            # Save the weather data in the database
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO weather_data 
                (city, weather_main, description, temperature, humidity, wind_speed, road_condition, timestamp, user_id) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                (city, weather_main, description, temp, humidity, wind_speed, road_condition, datetime.datetime.now(), user_id)
            )
            conn.commit()
            cursor.close()
            conn.close()

            # Set the weather_data to display the result on the page
            weather_data = {
                'city': city,
                'weather_main': weather_main,
                'description': description,
                'temperature': temp,
                'humidity': humidity,
                'wind_speed': wind_speed,
                'road_condition': road_condition,
                'traffic_signal_change': traffic_signal_change
            }
        else:
            weather_data = {'error': 'City not found'}

    # Return the template with weather data and history
    return render_template('weather_history.html', weather_data=weather_data, weather_history=weather_history)


@app.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    try:
        user_id = session.get("user_id")

        # User Profile Data
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT first_name, last_name, email, role FROM users WHERE id = %s', (user_id,))
        user_data = cursor.fetchone()

        if not user_data:
            return jsonify({"error": "User not found"}), 404

        first_name, last_name, email, role = user_data
        location_records = []
        weather_records = []

        # Fetch Location Data with User Join (Based on role)
        if role == "ADMIN":
            cursor.execute("""
                SELECT 
                    locations.latitude, 
                    locations.longitude, 
                    locations.timestamp, 
                    CONCAT(users.first_name, ' ', users.last_name) AS created_by
                FROM 
                    locations
                LEFT JOIN 
                    users ON locations.user_id = users.id
                ORDER BY 
                    locations.timestamp DESC
                LIMIT 5
            """)
        else:
            cursor.execute("""
                SELECT 
                    locations.latitude, 
                    locations.longitude, 
                    locations.timestamp, 
                    CONCAT(users.first_name, ' ', users.last_name) AS created_by
                FROM 
                    locations
                LEFT JOIN 
                    users ON locations.user_id = users.id
                WHERE 
                    locations.user_id = %s
                ORDER BY 
                    locations.timestamp DESC
                LIMIT 5
            """, (user_id,))

        location_data = cursor.fetchall()
        location_records = [{
            "latitude": row[0],
            "longitude": row[1],
            "timestamp": row[2].isoformat() if row[2] else None,
            "created_by": row[3]
        } for row in location_data]

        # Fetch Weather Data with User Join (Based on role)
        if role == "ADMIN":
            cursor.execute("""
                SELECT 
                    weather_data.city, 
                    weather_data.weather_main, 
                    weather_data.description, 
                    weather_data.temperature, 
                    weather_data.humidity, 
                    weather_data.wind_speed, 
                    weather_data.road_condition, 
                    weather_data."timestamp", 
                    CONCAT(users.first_name, ' ', users.last_name) AS created_by
                FROM 
                    weather_data
                LEFT JOIN 
                    users ON weather_data.user_id = users.id
                ORDER BY 
                    weather_data."timestamp" DESC
                LIMIT 5
            """)
        else:
            cursor.execute("""
                SELECT 
                    weather_data.city, 
                    weather_data.weather_main, 
                    weather_data.description, 
                    weather_data.temperature, 
                    weather_data.humidity, 
                    weather_data.wind_speed, 
                    weather_data.road_condition, 
                    weather_data."timestamp", 
                    CONCAT(users.first_name, ' ', users.last_name) AS created_by
                FROM 
                    weather_data
                LEFT JOIN 
                    users ON weather_data.user_id = users.id
                WHERE 
                    weather_data.user_id = %s
                ORDER BY 
                    weather_data."timestamp" DESC
                LIMIT 5
            """, (user_id,))

        weather_data = cursor.fetchall()
        weather_records = [{
            "city": row[0],
            "weather_main": row[1],
            "description": row[2],
            "temperature": row[3],
            "humidity": row[4],
            "wind_speed": row[5],
            "road_condition": row[6],
            "timestamp": row[7].isoformat() if row[7] else None,
            "created_by": row[8]
        } for row in weather_data]

        # Traffic Data (Filtered by user's location or show all if Admin)
        if role == "ADMIN":
            cursor.execute("""
                SELECT 
                    traffic.origin, 
                    traffic.destination, 
                    traffic.congestion_level, 
                    traffic.road_status, 
                    traffic.accident_report, 
                    CONCAT(users.first_name, ' ', users.last_name) AS created_by,
                    traffic.created_at
                FROM 
                    traffic
                JOIN 
                    users ON traffic.user_id = users.id
                ORDER BY 
                    traffic.created_at DESC 
                LIMIT 5
            """)
        else:
            cursor.execute("""
                SELECT 
                    traffic.origin, 
                    traffic.destination, 
                    traffic.congestion_level, 
                    traffic.road_status, 
                    traffic.accident_report, 
                    CONCAT(users.first_name, ' ', users.last_name) AS created_by,
                    traffic.created_at
                FROM 
                    traffic
                JOIN 
                    users ON traffic.user_id = users.id
                WHERE 
                    traffic.user_id = %s
                ORDER BY 
                    traffic.created_at DESC 
                LIMIT 5
            """, (user_id,))

        traffic_data = cursor.fetchall()
        traffic_updates = [{
            "origin": row[0],
            "destination": row[1],
            "congestion_level": row[2],
            "road_status": row[3],
            "accident_report": row[4],
            "created_by": row[5],
            "created_at": row[6].isoformat() if row[6] else None
        } for row in traffic_data]

        # Support Queries (Filtered by user role and user ID)
        if role == "ADMIN":
            cursor.execute("""
                SELECT 
                    support_queries.id, 
                    support_queries.name, 
                    support_queries.email, 
                    support_queries.message, 
                    support_queries.submitted_at,
                    CONCAT(users.first_name, ' ', users.last_name) AS created_by
                FROM 
                    support_queries
                LEFT JOIN 
                    users ON support_queries.user_id = users.id
                ORDER BY 
                    support_queries.submitted_at DESC 
                LIMIT 5
            """)
        else:
            cursor.execute("""
                SELECT 
                    support_queries.id, 
                    support_queries.name, 
                    support_queries.email, 
                    support_queries.message, 
                    support_queries.submitted_at,
                    CONCAT(users.first_name, ' ', users.last_name) AS created_by
                FROM 
                    support_queries
                LEFT JOIN 
                    users ON support_queries.user_id = users.id
                WHERE 
                    support_queries.user_id = %s
                ORDER BY 
                    support_queries.submitted_at DESC 
                LIMIT 5
            """, (user_id,))

        support_queries = cursor.fetchall()
        support_query_data = [{
            "id": row[0],
            "name": row[1],
            "created_by": row[5],
            "email": row[2],
            "message": row[3],
            "submitted_at": row[4].isoformat() if row[4] else None
        } for row in support_queries]

        # Consolidate all data
        dashboard_data = {
            "user_info": {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "role": role
            },
            "location": location_records,
            "weather_data": weather_records,
            "traffic_updates": traffic_updates,
            "support_queries": support_query_data
        }

        return render_template('dashboard.html', dashboard_data=dashboard_data)

    except Exception as e:
        # Log the error
        print(f"An error occurred: {e}")
        return jsonify({"error": "An error occurred while processing your request."}), 500


if __name__ == '__main__':
    socketio.run(app, debug=True)
