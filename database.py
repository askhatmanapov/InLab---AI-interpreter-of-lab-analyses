import psycopg2
import urllib.parse as urlparse
from decouple import config
from dotenv import load_dotenv

load_dotenv()

# Get a database connection
def get_db_connection():
    DATABASE_URL = config("DATABASE_URL")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not provided. Cannot connect to the database.")

    urlparse.uses_netloc.append("postgres")
    url = urlparse.urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
    return conn

# Initialize the database
def initialize_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_points (
              user_id BIGINT PRIMARY KEY, 
              points BIGINT,
              name VARCHAR(255),
              phone VARCHAR(225),
              language VARCHAR(10),
              first_time TIMESTAMP DEFAULT NULL,
              last_time TIMESTAMP DEFAULT NULL,
              user_state BIGINT DEFAULT 0
            );
              
            
            CREATE TABLE IF NOT EXISTS specialists (
                id SERIAL PRIMARY KEY,          -- Unique ID for the specialization
                name VARCHAR(255) NOT NULL,     -- Name of the specialization
                rec_count INT DEFAULT 0         -- Recommendation counter
            );

            
            CREATE TABLE IF NOT EXISTS doctors (
                id BIGSERIAL PRIMARY KEY, -- Unique identifier for each doctor
                specialist_id INT REFERENCES specialists(id),
                name VARCHAR(255),               -- Doctor's full name
                position VARCHAR(255),           -- Doctor's job title
                phone VARCHAR(20),        -- Doctor's contact number
                medical_center VARCHAR(255) DEFAULT NULL,    -- The organization the doctor works for
                address VARCHAR(255) DEFAULT NULL,           -- The address of the medical center
                price INT DEFAULT NULL
            );
              
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_id BIGINT PRIMARY KEY,  -- Unique invoice ID
                user_id BIGINT REFERENCES user_points(user_id) ON DELETE CASCADE,
                product_id VARCHAR(255),
                points BIGINT,
                price INT,
                processed BOOLEAN DEFAULT FALSE,
                time TIMESTAMP DEFAULT NULL
            );
            
        ''')
    conn.commit()
    conn.close()

#Read name
def read_name(user_id, name):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE user_points SET name = %s WHERE user_id = %s', (name, user_id))
    conn.commit()
    c.close()
    conn.close()

def get_name(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT name FROM user_points WHERE user_id = %s', (user_id,))
    result = c.fetchone()
    conn.close()
    if result and result[0] is not None:
        return result[0]
    else:
        return 0 

#Read phone number
def read_phone_number(user_id, phone_number):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE user_points SET phone_number = %s WHERE user_id = %s', (phone_number, user_id))
    conn.commit()
    c.close()
    conn.close()

# Registration 
def register_user(user_id, points_to_add):
    conn = get_db_connection()
    # print(f"Registering user: {user_id}, Points to add: {points_to_add}, Name: {name}, Phone Number: {phone_number}")
    c = conn.cursor()
    sql = """
    INSERT INTO user_points (user_id, points) VALUES (%s, %s)
    ON CONFLICT (user_id) DO UPDATE SET
        points = COALESCE(user_points.points, 0) + EXCLUDED.points;
    """
    c.execute(sql, (user_id, points_to_add))
    conn.commit()
    c.close()
    conn.close()

# Add points
def add_points(user_id, points_to_add):
    conn = get_db_connection()
    c = conn.cursor()
    sql = """
    INSERT INTO user_points (user_id, points) VALUES (%s, %s)
    ON CONFLICT (user_id) DO UPDATE SET points = COALESCE(user_points.points, 0) + EXCLUDED.points;
    """
    c.execute(sql, (user_id, points_to_add))
    conn.commit()
    c.close()
    conn.close()

# Subtract points
def subtract_points(user_id, points_to_subtract):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT points FROM user_points WHERE user_id = %s', (user_id,))
    result = c.fetchone()
    if result and result[0] >= points_to_subtract:
        c.execute('UPDATE user_points SET points = points - %s WHERE user_id = %s', (points_to_subtract, user_id))
        conn.commit()
        conn.close()
        return True  # Successfully subtracted points
    else:
        conn.close()
        return False  # Not enough points or user not found

# Get user points
def get_points(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT points FROM user_points WHERE user_id = %s', (user_id,))
    result = c.fetchone()
    conn.close()
    if result and result[0] is not None:
        return result[0]
    else:
        return 0  # Return 0 points if user is not found or points are NULL

# Check if user exists
def user_exists(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    with conn.cursor() as cursor:
        cursor.execute('SELECT name, phone_number, user_state FROM user_points WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
    conn.close()
    if result:
        return {'name': result[0], 'phone_number': result[1], 'user_state': result[2]}
    return None

# Add user language
def add_user_language(user_id, language_code):
    conn = get_db_connection()
    c = conn.cursor()
    sql = """
    INSERT INTO user_points (user_id, language) VALUES (%s, %s)
    ON CONFLICT (user_id) DO UPDATE SET language = EXCLUDED.language;
    """
    c.execute(sql, (user_id, language_code))
    conn.commit()
    c.close()
    conn.close()

# Get user language
def get_user_language(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT language FROM user_points WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            if result:
                return result[0]  # Return the language code stored in the database
            else:
                return 'en'  # Default to English if no language is set
    except Exception as e:
        print(f"Database error: {e}")
        return 'en'  # Default to English in case of any error
    finally:
        conn.close()

# Timestamp
def record_timestamp(user_id):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        # Use INSERT ON CONFLICT to handle the unique constraint on user_id
        c.execute('''
            INSERT INTO user_points (user_id, first_time, last_time)
            VALUES (%s, CURRENT_TIMESTAMP AT TIME ZONE 'UTC' AT TIME ZONE 'UTC+5', CURRENT_TIMESTAMP AT TIME ZONE 'UTC' AT TIME ZONE 'UTC+5')
            ON CONFLICT (user_id) DO UPDATE
            SET last_time = EXCLUDED.last_time
            ''', (user_id,))
        conn.commit()
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        c.close()
        conn.close()

def get_all_specialists():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT Name FROM specialists')
    result = [row[0] for row in c.fetchall()]  # Extract the first column from each tuple
    c.close()
    conn.close()
    return result

def increment_rec_count(specialist_name):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE specialists SET rec_count = rec_count + 1 WHERE Name = %s;", (specialist_name,))
        conn.commit()
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        c.close()
        conn.close()

def store_invoice_in_db(invoice_id, user_id, product_id, points, price):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO invoices (invoice_id, user_id, product_id, points, price, processed, time)
        VALUES (%s, %s, %s, %s, %s, FALSE, CURRENT_TIMESTAMP AT TIME ZONE 'UTC' AT TIME ZONE 'UTC+5')
        """,
        (invoice_id, user_id, product_id, points, price),
    )
    conn.commit()
    c.close()
    conn.close()

def get_invoice_from_db(invoice_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, points, processed FROM invoices WHERE invoice_id = %s", (invoice_id,))
    result = c.fetchone()
    c.close()
    conn.close()
    return result

def set_user_state(user_id, state):
    conn = get_db_connection()
    c = conn.cursor()
    sql = """
    INSERT INTO user_points (user_id, user_state) VALUES (%s, %s)
    ON CONFLICT (user_id) DO UPDATE SET user_state = EXCLUDED.user_state;
    """
    c.execute(sql, (user_id, state))
    conn.commit()
    c.close()
    conn.close()

def get_user_state(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_state FROM user_points WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            if result:
                return result[0]  # Return the user_state stored in the database
            else:
                return '0'  # Default to English if no language is set
    except Exception as e:
        print(f"Database error: {e}")
        return 'en'  # Default to English in case of any error
    finally:
        conn.close()