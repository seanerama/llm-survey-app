from flask import Flask, render_template, request, redirect, url_for, jsonify
import json
import os
import uuid
import base64
import threading
from datetime import datetime
from io import BytesIO

# Database imports
import psycopg2
from psycopg2.extras import RealDictCursor

# Gemini API
from google import genai
from google.genai import types

# Resend for email
import resend

app = Flask(__name__)

# Database connection
DATABASE_URL = os.environ.get('DATABASE_URL')

# API Keys
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY')
APP_URL = os.environ.get('APP_URL', 'https://llm-survey-app.onrender.com')

# Initialize Resend
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# Survey configuration
SURVEY_CONFIG = {
    'title': 'Pre-Presentation Knowledge Assessment',
    'subtitle': 'LLMs and Vibe Coding',
    'intro': 'Please rate your current confidence level on each topic before the presentation.',
    'rating_scale': [
        {'value': 1, 'label': "I have no idea what it is"},
        {'value': 3, 'label': "I've heard the term but unsure what it means"},
        {'value': 5, 'label': "I know the acronym and have an idea of what it is"},
        {'value': 7, 'label': "I know what it is and have a general idea of how it works"},
        {'value': 10, 'label': "I know how it works and feel comfortable teaching others"},
    ],
    'questions': [
        {
            'id': 'llm_slm_fm',
            'type': 'rating',
            'label': 'LLM, SLM, FM — do you know the differences?',
            'max_rating': 10,
            'required': True
        },
        {
            'id': 'rag',
            'type': 'rating',
            'label': 'What is RAG and how it\'s used with LLMs?',
            'max_rating': 10,
            'required': True
        },
        {
            'id': 'mcp',
            'type': 'rating',
            'label': 'What is MCP (Model Context Protocol)?',
            'max_rating': 10,
            'required': True
        },
        {
            'id': 'fine_tuning',
            'type': 'rating',
            'label': 'What is fine-tuning?',
            'max_rating': 10,
            'required': True
        },
        {
            'id': 'temperature',
            'type': 'rating',
            'label': 'What is temperature (in AI context)?',
            'max_rating': 10,
            'required': True
        },
        {
            'id': 'vector_database',
            'type': 'rating',
            'label': 'What is a vector database?',
            'max_rating': 10,
            'required': True
        },
        {
            'id': 'vibe_coding',
            'type': 'rating',
            'label': 'Building software by describing what you want to an AI ("vibe coding")?',
            'max_rating': 10,
            'required': True
        },
        {
            'id': 'ai_assistant_used',
            'type': 'multiple_choice',
            'label': 'Have you used an AI coding assistant?',
            'options': ['Yes', 'No', 'Tried once'],
            'required': True
        },
        {
            'id': 'wishlist_app',
            'type': 'textarea',
            'label': 'What\'s one platform/app you use daily that you wish you could just chat with or automate?',
            'required': False
        }
    ]
}

MAX_AVATARS_PER_EMAIL = 3


def get_db():
    """Get database connection."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn


def init_db():
    """Initialize database tables."""
    if not DATABASE_URL:
        print("Warning: DATABASE_URL not set, skipping database initialization")
        return

    conn = get_db()
    cur = conn.cursor()

    # Create responses table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS responses (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255),
            data JSONB NOT NULL,
            selfie_data TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create avatars table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS avatars (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL,
            response_id INTEGER REFERENCES responses(id),
            image_data TEXT,
            status VARCHAR(50) DEFAULT 'pending',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    ''')

    # Create index for email lookups
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_avatars_email ON avatars(email)
    ''')

    conn.commit()
    cur.close()
    conn.close()
    print("Database initialized successfully")


def get_avatar_count(email):
    """Get the number of avatars created for an email."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) as count FROM avatars WHERE email = %s', (email,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result['count'] if result else 0


def generate_avatar_async(avatar_id, email, selfie_base64):
    """Background task to generate avatar using Gemini."""
    try:
        if not GEMINI_API_KEY:
            raise Exception("Gemini API key not configured")

        # Initialize Gemini client
        client = genai.Client(api_key=GEMINI_API_KEY)

        # Decode the selfie image
        image_data = base64.b64decode(selfie_base64.split(',')[1] if ',' in selfie_base64 else selfie_base64)

        # Create the prompt for avatar generation
        prompt = """Transform this photo into a stylized illustrated avatar of a mystical "Vibe Coding Network Wizard".

The avatar should:
- Keep the person's likeness recognizable but stylized as digital art
- Show them as a modern tech wizard with a hoodie or robes
- Have glowing circuit patterns and code symbols floating around them
- Include a magical aura with binary/hex codes as sparkles
- Feature a cosmic/digital background with neural network nodes
- Have a friendly, confident expression
- Style: Semi-realistic digital illustration, vibrant colors, fantasy-tech aesthetic

Make it fun and shareable - something they'd be proud to use as a profile picture!"""

        # Upload the image and generate
        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_bytes(data=image_data, mime_type="image/jpeg"),
                        types.Part.from_text(text=prompt)
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                response_modalities=['image', 'text']
            )
        )

        # Extract the generated image
        generated_image = None
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                generated_image = base64.b64encode(part.inline_data.data).decode('utf-8')
                break

        if not generated_image:
            raise Exception("No image generated in response")

        # Update database with success
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''
            UPDATE avatars
            SET image_data = %s, status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (generated_image, avatar_id))
        conn.commit()
        cur.close()
        conn.close()

        # Send email notification
        send_avatar_email(email, avatar_id)

    except Exception as e:
        print(f"Avatar generation error: {e}")
        # Update database with error
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''
            UPDATE avatars
            SET status = 'failed', error_message = %s, completed_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (str(e), avatar_id))
        conn.commit()
        cur.close()
        conn.close()


def send_avatar_email(email, avatar_id):
    """Send email notification when avatar is ready."""
    try:
        if not RESEND_API_KEY:
            print("Resend API key not configured, skipping email")
            return

        avatar_url = f"{APP_URL}/avatar/{avatar_id}"

        resend.Emails.send({
            "from": "Vibe Coding Survey <onboarding@resend.dev>",
            "to": email,
            "subject": "Your Vibe Coding Wizard Avatar is Ready!",
            "html": f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #667eea; text-align: center;">Your Avatar is Ready!</h1>
                <p style="font-size: 16px; color: #333;">
                    Thank you for completing the Pre-Presentation Knowledge Assessment!
                </p>
                <p style="font-size: 16px; color: #333;">
                    Your personalized <strong>Vibe Coding Network Wizard</strong> avatar has been generated.
                </p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{avatar_url}"
                       style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                              color: white;
                              padding: 15px 30px;
                              text-decoration: none;
                              border-radius: 8px;
                              font-weight: bold;
                              display: inline-block;">
                        View Your Avatar
                    </a>
                </div>
                <p style="font-size: 14px; color: #666; text-align: center;">
                    Feel free to download and share it!
                </p>
            </div>
            """
        })
        print(f"Email sent to {email}")
    except Exception as e:
        print(f"Email send error: {e}")


@app.route('/')
def survey():
    return render_template('survey.html', config=SURVEY_CONFIG, max_avatars=MAX_AVATARS_PER_EMAIL)


@app.route('/check-email', methods=['POST'])
def check_email():
    """Check if email has reached avatar limit."""
    email = request.json.get('email', '').lower().strip()
    if not email:
        return jsonify({'allowed': False, 'message': 'Email required'})

    count = get_avatar_count(email)
    allowed = count < MAX_AVATARS_PER_EMAIL
    remaining = MAX_AVATARS_PER_EMAIL - count

    return jsonify({
        'allowed': allowed,
        'remaining': remaining,
        'message': f'You have {remaining} avatar(s) remaining' if allowed else 'Maximum avatars reached for this email'
    })


@app.route('/submit', methods=['POST'])
def submit():
    # Get survey responses
    responses = {}
    for question in SURVEY_CONFIG['questions']:
        qid = question['id']
        if question['type'] == 'checkbox':
            responses[qid] = request.form.getlist(qid)
        else:
            responses[qid] = request.form.get(qid, '')

    # Get email and selfie
    email = request.form.get('email', '').lower().strip()
    selfie_data = request.form.get('selfie_data', '')

    # Save response to database
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO responses (email, data, selfie_data) VALUES (%s, %s, %s) RETURNING id',
        (email, json.dumps(responses), selfie_data if selfie_data else None)
    )
    response_id = cur.fetchone()['id']
    conn.commit()

    # Check if we should generate an avatar
    avatar_queued = False
    if email and selfie_data:
        avatar_count = get_avatar_count(email)
        if avatar_count < MAX_AVATARS_PER_EMAIL:
            # Create avatar record
            avatar_id = str(uuid.uuid4())
            cur.execute(
                'INSERT INTO avatars (id, email, response_id, status) VALUES (%s, %s, %s, %s)',
                (avatar_id, email, response_id, 'pending')
            )
            conn.commit()
            avatar_queued = True

            # Start background generation
            thread = threading.Thread(
                target=generate_avatar_async,
                args=(avatar_id, email, selfie_data)
            )
            thread.daemon = True
            thread.start()

    cur.close()
    conn.close()

    return render_template('thanks.html', avatar_queued=avatar_queued, email=email)


@app.route('/avatar/<uuid:avatar_id>')
def view_avatar(avatar_id):
    """Public page to view a generated avatar."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM avatars WHERE id = %s', (str(avatar_id),))
    avatar = cur.fetchone()
    cur.close()
    conn.close()

    if not avatar:
        return render_template('avatar.html', error='Avatar not found'), 404

    return render_template('avatar.html', avatar=avatar)


@app.route('/admin')
def admin():
    conn = get_db()
    cur = conn.cursor()

    # Get responses
    cur.execute('SELECT * FROM responses ORDER BY submitted_at DESC')
    rows = cur.fetchall()

    responses = []
    for row in rows:
        responses.append({
            'id': row['id'],
            'email': row['email'],
            'data': row['data'] if isinstance(row['data'], dict) else json.loads(row['data']),
            'submitted_at': row['submitted_at']
        })

    # Get avatars
    cur.execute('SELECT * FROM avatars ORDER BY created_at DESC')
    avatars = cur.fetchall()

    cur.close()
    conn.close()

    # Calculate statistics for charts
    stats = {}
    mc_stats = {}
    text_responses = []

    for question in SURVEY_CONFIG['questions']:
        qid = question['id']

        if question['type'] == 'rating':
            values = []
            for resp in responses:
                val = resp['data'].get(qid)
                if val:
                    try:
                        values.append(int(val))
                    except (ValueError, TypeError):
                        pass
            if values:
                stats[qid] = {
                    'average': round(sum(values) / len(values), 1),
                    'count': len(values),
                    'min': min(values),
                    'max': max(values)
                }
            else:
                stats[qid] = {'average': 0, 'count': 0, 'min': 0, 'max': 0}

        elif question['type'] == 'multiple_choice':
            counts = {opt: 0 for opt in question['options']}
            for resp in responses:
                val = resp['data'].get(qid)
                if val in counts:
                    counts[val] += 1
            mc_stats[qid] = counts

        elif question['type'] == 'textarea':
            for resp in responses:
                val = resp['data'].get(qid, '').strip()
                if val:
                    text_responses.append(val)

    return render_template('admin.html', responses=responses, config=SURVEY_CONFIG,
                          stats=stats, mc_stats=mc_stats, text_responses=text_responses,
                          avatars=avatars)


@app.route('/admin/delete/<int:response_id>', methods=['POST'])
def delete_response(response_id):
    conn = get_db()
    cur = conn.cursor()
    # Delete associated avatars first
    cur.execute('DELETE FROM avatars WHERE response_id = %s', (response_id,))
    cur.execute('DELETE FROM responses WHERE id = %s', (response_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin'))


# Initialize database on import (for production with gunicorn)
if DATABASE_URL:
    init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
