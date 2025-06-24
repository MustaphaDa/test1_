from flask import Flask, jsonify, request
import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# PostgreSQL connection details (use environment variables for security)
DB_HOST = os.environ.get('DB_HOST') or os.environ.get('DATABASE_HOST', 'centerbeam.proxy.rlwy.net')
DB_PORT = os.environ.get('DB_PORT') or os.environ.get('DATABASE_PORT', '43742')
DB_NAME = os.environ.get('DB_NAME') or os.environ.get('DATABASE_NAME', 'railway')
DB_USER = os.environ.get('DB_USER') or os.environ.get('DATABASE_USER', 'postgres')
DB_PASS = os.environ.get('DB_PASS') or os.environ.get('DATABASE_PASSWORD', 'HPrpLUmYHcScrLfeZZDjAXUcpKHpfHJs')

def test_database_connection():
    """Test if we can connect to the database"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        cur.execute('SELECT version()')
        version = cur.fetchone()
        cur.close()
        conn.close()
        return True, f"Connected to PostgreSQL: {version[0]}"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"

@app.route('/test', methods=['GET'])
def test_endpoint():
    """Test endpoint to check if Flask and database are working"""
    db_connected, db_message = test_database_connection()
    return jsonify({
        'message': 'Flask API is running!',
        'database_connected': db_connected,
        'database_message': db_message,
        'environment_vars': {
            'DB_HOST': DB_HOST,
            'DB_PORT': DB_PORT,
            'DB_NAME': DB_NAME,
            'DB_USER': DB_USER,
            'DB_PASS': '***' if DB_PASS else 'NOT SET'
        }
    }), 200

@app.route('/people', methods=['GET'])
def get_people():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        cur.execute('''
            SELECT p.id, p.first_name, p.last_name, p.email, g.gender_name, 
                   p.contact, p.mother_name, p.created_at
            FROM people p
            LEFT JOIN gender g ON p.gender_id = g.gender_id
            ORDER BY p.id
            LIMIT 50
        ''')
        columns = [desc[0] for desc in cur.description]
        people = [dict(zip(columns, row)) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({
            'people': people, 
            'count': len(people),
            'message': f'Successfully retrieved {len(people)} people'
        }), 200
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Failed to retrieve people from database'
        }), 500

@app.route('/people', methods=['POST'])
def add_person():
    try:
        data = request.get_json()
        # Required fields
        required_fields = ['first_name', 'last_name', 'email']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        first_name = data['first_name']
        last_name = data['last_name']
        email = data['email']
        gender = data.get('gender')
        contact = data.get('contact')
        mother_name = data.get('mother_name')
        
        # Connect to DB
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        
        # Get gender_id if gender is provided
        gender_id = None
        if gender:
            cur.execute('SELECT gender_id FROM gender WHERE gender_name = %s', (gender,))
            gender_result = cur.fetchone()
            if gender_result:
                gender_id = gender_result[0]
        
        # Insert person
        cur.execute("""
            INSERT INTO people (first_name, last_name, email, gender_id, contact, mother_name)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (first_name, last_name, email, gender_id, contact, mother_name))
        
        person_id = cur.fetchone()[0]
        
        # Insert default activities record
        cur.execute("""
            INSERT INTO activities (person_id, activity1, activity2, transport)
            VALUES (%s, FALSE, FALSE, FALSE)
        """, (person_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'message': 'Person added successfully', 'person_id': person_id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/people/<int:person_id>', methods=['PUT'])
def update_person(person_id):
    """Update a person by ID"""
    print(f"PUT request received for person_id: {person_id}")
    print("Headers received:", dict(request.headers))
    print("Body received:", request.get_data())
    
    try:
        data = request.get_json()
        print("Parsed JSON data:", data)
        
        # List of fields you allow to update
        allowed_fields = [
            'first_name', 'last_name', 'email', 'gender', 'contact', 'mother_name'
        ]
        
        # Build the SET part of the SQL dynamically
        set_clauses = []
        values = []
        
        for field in allowed_fields:
            if field in data:
                value = data[field]
                # Convert empty strings to None (NULL in SQL)
                if value == "":
                    value = None
                
                # Handle gender field specially (convert to gender_id)
                if field == 'gender' and value:
                    conn = psycopg2.connect(
                        host=DB_HOST,
                        port=DB_PORT,
                        dbname=DB_NAME,
                        user=DB_USER,
                        password=DB_PASS
                    )
                    cur = conn.cursor()
                    cur.execute('SELECT gender_id FROM gender WHERE gender_name = %s', (value,))
                    gender_result = cur.fetchone()
                    if gender_result:
                        value = gender_result[0]
                    else:
                        value = None
                    cur.close()
                    conn.close()
                    set_clauses.append("gender_id = %s")
                else:
                    set_clauses.append(f"{field} = %s")
                
                values.append(value)
        
        if not set_clauses:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        values.append(person_id)
        set_clause = ', '.join(set_clauses)
        sql = f"UPDATE people SET {set_clause} WHERE id = %s"
        print("Executing SQL:", sql)
        print("With values:", values)
        
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        cur.execute(sql, values)
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'message': f'Person {person_id} updated successfully'}), 200
    except Exception as e:
        print("Database error:", str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/people/<int:person_id>', methods=['GET'])
def get_person(person_id):
    """Get a specific person by ID"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        cur.execute('''
            SELECT p.id, p.first_name, p.last_name, p.email, g.gender_name, 
                   p.contact, p.mother_name, p.created_at
            FROM people p
            LEFT JOIN gender g ON p.gender_id = g.gender_id
            WHERE p.id = %s
        ''', (person_id,))
        
        person_data = cur.fetchone()
        
        if not person_data:
            cur.close()
            conn.close()
            return jsonify({'error': f'Person with ID {person_id} not found'}), 404
        
        columns = [desc[0] for desc in cur.description]
        person = dict(zip(columns, person_data))
        cur.close()
        conn.close()
        
        return jsonify({
            'person': person,
            'message': f'Successfully retrieved person {person_id}'
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': f'Failed to retrieve person {person_id} from database'
        }), 500

@app.route('/people/<int:person_id>', methods=['DELETE'])
def delete_person(person_id):
    """Delete a person by ID"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        
        # Check if person exists
        cur.execute('SELECT id FROM people WHERE id = %s', (person_id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': f'Person with ID {person_id} not found'}), 404
        
        # Delete person (activities will be deleted automatically due to CASCADE)
        cur.execute('DELETE FROM people WHERE id = %s', (person_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': f'Person {person_id} deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/activities', methods=['GET'])
def get_activities():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        cur.execute('''
            SELECT a.activity_id, a.person_id, p.first_name, p.last_name,
                   a.activity1, a.activity2, a.transport, a.created_at
            FROM activities a
            JOIN people p ON a.person_id = p.id
            ORDER BY a.activity_id
            LIMIT 50
        ''')
        columns = [desc[0] for desc in cur.description]
        activities = [dict(zip(columns, row)) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({
            'activities': activities, 
            'count': len(activities),
            'message': f'Successfully retrieved {len(activities)} activities'
        }), 200
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Failed to retrieve activities from database'
        }), 500

@app.route('/activities/person/<int:person_id>', methods=['GET'])
def get_activities_by_person(person_id):
    """Get activities for a specific person"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        cur.execute('''
            SELECT a.activity_id, a.person_id, p.first_name, p.last_name,
                   a.activity1, a.activity2, a.transport, a.created_at
            FROM activities a
            JOIN people p ON a.person_id = p.id
            WHERE a.person_id = %s
        ''', (person_id,))
        
        columns = [desc[0] for desc in cur.description]
        activities = [dict(zip(columns, row)) for row in cur.fetchall()]
        cur.close()
        conn.close()
        
        return jsonify({
            'activities': activities,
            'count': len(activities),
            'message': f'Successfully retrieved activities for person {person_id}'
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': f'Failed to retrieve activities for person {person_id}'
        }), 500

@app.route('/activities/<int:activity_id>', methods=['PUT'])
def update_activities(activity_id):
    """Update activities for a person"""
    try:
        data = request.get_json()
        
        allowed_fields = ['activity1', 'activity2', 'transport']
        set_clauses = []
        values = []
        
        for field in allowed_fields:
            if field in data:
                set_clauses.append(f"{field} = %s")
                values.append(data[field])
        
        if not set_clauses:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        values.append(activity_id)
        set_clause = ', '.join(set_clauses)
        sql = f"UPDATE activities SET {set_clause} WHERE activity_id = %s"
        
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        cur.execute(sql, values)
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': f'Activities {activity_id} updated successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/activity1', methods=['GET'])
def get_activity1_people():
    """Get all people who have activity1 = true"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        cur.execute('''
            SELECT id, first_name, last_name, email, gender, contact, mother_name,
                   activity1, activity2, transport, created_at
            FROM activity1
            ORDER BY id
            LIMIT 50
        ''')
        columns = [desc[0] for desc in cur.description]
        activity1_people = [dict(zip(columns, row)) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({
            'activity1_people': activity1_people, 
            'count': len(activity1_people),
            'message': f'Successfully retrieved {len(activity1_people)} people with activity1 = true'
        }), 200
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Failed to retrieve activity1 people from database'
        }), 500

@app.route('/transport', methods=['GET'])
def get_transport_people():
    """Get all people who have transport = true"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        cur.execute('''
            SELECT id, first_name, last_name, email, gender, contact, mother_name,
                   activity1, activity2, transport, created_at
            FROM transport
            ORDER BY id
            LIMIT 50
        ''')
        columns = [desc[0] for desc in cur.description]
        transport_people = [dict(zip(columns, row)) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({
            'transport_people': transport_people, 
            'count': len(transport_people),
            'message': f'Successfully retrieved {len(transport_people)} people with transport = true'
        }), 200
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Failed to retrieve transport people from database'
        }), 500

@app.route('/gender', methods=['GET'])
def get_genders():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        cur.execute('SELECT gender_id, gender_name FROM gender ORDER BY gender_id')
        columns = [desc[0] for desc in cur.description]
        genders = [dict(zip(columns, row)) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({
            'genders': genders, 
            'count': len(genders),
            'message': f'Successfully retrieved {len(genders)} gender types'
        }), 200
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Failed to retrieve genders from database'
        }), 500

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'message': 'People Management API is running!',
        'endpoints': {
            'home': '/',
            'test': '/test (test database connection)',
            'debug': '/debug (debug environment variables)',
            'people': '/people (get people data)',
            'person_by_id': '/people/<id> (get/update/delete specific person)',
            'activities': '/activities (get activities data)',
            'activities_by_person': '/activities/person/<id> (get activities for person)',
            'update_activities': '/activities/<id> (update activities)',
            'activity1': '/activity1 (get people with activity1 = true)',
            'transport': '/transport (get people with transport = true)',
            'gender': '/gender (get gender types)',
            'routes': '/routes (list all routes)'
        },
        'status': 'API is ready to use'
    }), 200

@app.route('/routes', methods=['GET'])
def list_routes():
    """List all available routes"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': str(rule)
        })
    return jsonify({
        'message': 'Available routes',
        'routes': routes
    }), 200

@app.route('/debug', methods=['GET'])
def debug_info():
    """Debug endpoint to check environment variables"""
    return jsonify({
        'message': 'Debug information',
        'environment_vars': {
            'PORT': os.environ.get('PORT', 'NOT SET'),
            'DB_HOST': os.environ.get('DB_HOST', 'NOT SET'),
            'DB_PORT': os.environ.get('DB_PORT', 'NOT SET'),
            'DB_NAME': os.environ.get('DB_NAME', 'NOT SET'),
            'DB_USER': os.environ.get('DB_USER', 'NOT SET'),
            'DB_PASS': '***' if os.environ.get('DB_PASS') else 'NOT SET',
            'DATABASE_HOST': os.environ.get('DATABASE_HOST', 'NOT SET'),
            'DATABASE_PORT': os.environ.get('DATABASE_PORT', 'NOT SET'),
            'DATABASE_NAME': os.environ.get('DATABASE_NAME', 'NOT SET'),
            'DATABASE_USER': os.environ.get('DATABASE_USER', 'NOT SET'),
            'DATABASE_PASSWORD': '***' if os.environ.get('DATABASE_PASSWORD') else 'NOT SET'
        },
        'all_env_vars': {k: v for k, v in os.environ.items() if 'DB' in k or 'DATABASE' in k or 'PORT' in k}
    }), 200

if __name__ == '__main__':
    print("Starting Flask app...")
    print("Available endpoints:")
    print("- / (home)")
    print("- /test (test database connection)")
    print("- /people (get people data)")
    print("- /people/<id> (get/update/delete specific person)")
    print("- /activities (get activities data)")
    print("- /activities/person/<id> (get activities for person)")
    print("- /activities/<id> (update activities)")
    print("- /activity1 (get people with activity1 = true)")
    print("- /transport (get people with transport = true)")
    print("- /gender (get gender types)")
    print("- /routes (list all routes)")
    print("- /debug (debug information)")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True) 