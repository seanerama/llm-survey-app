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

# Anthropic (Claude) API
import anthropic

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

# Claude API client (lazy initialization)
_claude_client = None


def get_claude_client():
    """Get or create Claude API client."""
    global _claude_client
    if _claude_client is None:
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if api_key:
            _claude_client = anthropic.Anthropic(api_key=api_key)
        else:
            print("Warning: ANTHROPIC_API_KEY not set, Claude features disabled")
    return _claude_client

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
        },
        {
            'id': 'avatar_universe',
            'type': 'single_select',
            'label': 'Pick your universe',
            'description': 'Choose the aesthetic world for your avatar',
            'options': [
                {'value': 'scifi', 'label': 'Sci-Fi'},
                {'value': 'fantasy', 'label': 'Fantasy'},
                {'value': 'cyberpunk', 'label': 'Cyberpunk'},
                {'value': 'retro', 'label': 'Retro/Arcade'},
                {'value': 'nature', 'label': 'Nature'},
                {'value': 'steampunk', 'label': 'Steampunk'},
                {'value': 'cosmic', 'label': 'Space/Cosmic'},
                {'value': 'postapoc', 'label': 'Post-Apocalyptic'},
                {'value': 'noir', 'label': 'Noir/Detective'},
                {'value': 'underwater', 'label': 'Underwater'},
            ],
            'required': False
        },
        {
            'id': 'avatar_fuels',
            'type': 'multi_select_exact',
            'label': 'What fuels you?',
            'description': 'Select exactly 3 interests',
            'select_count': 3,
            'options': [
                {'value': 'gaming', 'label': 'Gaming'},
                {'value': 'music', 'label': 'Music'},
                {'value': 'sports', 'label': 'Sports'},
                {'value': 'coffee', 'label': 'Coffee'},
                {'value': 'code', 'label': 'Code'},
                {'value': 'movies', 'label': 'Movies/Film'},
                {'value': 'travel', 'label': 'Travel'},
                {'value': 'art', 'label': 'Art/Design'},
                {'value': 'fitness', 'label': 'Fitness'},
                {'value': 'books', 'label': 'Books/Reading'},
            ],
            'required': False
        },
        {
            'id': 'avatar_element',
            'type': 'single_select',
            'label': 'Your element?',
            'description': 'Choose your magical power source',
            'options': [
                {'value': 'fire', 'label': 'Fire'},
                {'value': 'lightning', 'label': 'Lightning'},
                {'value': 'ice', 'label': 'Ice'},
                {'value': 'earth', 'label': 'Earth'},
                {'value': 'digital', 'label': 'Digital/Glitch'},
                {'value': 'shadow', 'label': 'Shadow/Dark'},
                {'value': 'cosmic', 'label': 'Cosmic/Stars'},
                {'value': 'crystal', 'label': 'Crystal'},
            ],
            'required': False
        }
    ]
}

# Visual mappings for Claude avatar prompt generation
UNIVERSE_VISUALS = {
    'scifi': 'sleek spacecraft, holograms, clean futuristic tech',
    'fantasy': 'magic runes, enchanted forests, mythical creatures',
    'cyberpunk': 'neon-lit streets, augmented reality, gritty urban',
    'retro': '8-bit pixels, CRT screens, 80s synthwave colors',
    'nature': 'forests, mountains, organic growth patterns',
    'steampunk': 'brass gears, Victorian machinery, clockwork',
    'cosmic': 'galaxies, nebulas, astronaut vibes',
    'postapoc': 'rugged survival gear, wasteland, weathered tech',
    'noir': 'shadows, mystery, moody lighting, fedoras',
    'underwater': 'deep sea, bioluminescence, aquatic elements',
}

FUEL_VISUALS = {
    'gaming': 'controllers, headsets, game UI elements',
    'music': 'headphones, sound waves, instruments',
    'sports': 'athletic gear, motion lines, team energy',
    'coffee': 'steaming mug, coffee beans, cozy warmth',
    'code': 'floating syntax, terminal windows, brackets',
    'movies': 'film reels, director chair, cinematic lighting',
    'travel': 'maps, compass, passport stamps, landmarks',
    'art': 'paintbrushes, color palettes, creative splashes',
    'fitness': 'gym equipment, energy aura, strength vibes',
    'books': 'floating tomes, spectacles, library aesthetic',
}

ELEMENT_VISUALS = {
    'fire': 'flames, embers, warm orange/red glow',
    'lightning': 'electric sparks, crackling energy, blue-white',
    'ice': 'frost crystals, cold blue, frozen particles',
    'earth': 'stone, vines, grounded brown/green tones',
    'digital': 'pixel distortion, data streams, matrix code',
    'shadow': 'mysterious darkness, smoky wisps, purple-black',
    'cosmic': 'stardust, constellation patterns, galaxy swirls',
    'crystal': 'prismatic gems, light refraction, geometric',
}

FALLBACK_AVATAR_PROMPT = """Transform this selfie into a stylized digital art portrait of a Vibe Coding Network Wizard. Create an illustrated wizard character that maintains the person's likeness but in a fun, artistic style. Add magical coding elements like floating code symbols, glowing runes, and ethereal light effects. The style should be colorful and professional, suitable for a profile picture."""

VIBE_PLAN_ERROR_MESSAGE = """We couldn't generate your personalized plan at this time. The presentation will cover vibe coding techniques that you can apply to your idea!"""

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

    # Create vibe_plans table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS vibe_plans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            response_id INTEGER REFERENCES responses(id),
            email VARCHAR(255) NOT NULL,
            wishlist_input TEXT NOT NULL,
            plan_content TEXT,
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


def generate_avatar_prompt(universe: str, fuels: list, element: str) -> str:
    """
    Generate a custom Gemini image prompt based on user preferences.

    Args:
        universe: Selected aesthetic universe (e.g., 'cyberpunk')
        fuels: List of 3 interests (e.g., ['gaming', 'code', 'coffee'])
        element: Selected element (e.g., 'lightning')

    Returns:
        Custom prompt string for Gemini, or fallback prompt on failure.
    """
    client = get_claude_client()

    # Validate inputs
    if not client:
        return FALLBACK_AVATAR_PROMPT

    if universe not in UNIVERSE_VISUALS:
        print(f"Warning: Invalid universe '{universe}', using fallback")
        return FALLBACK_AVATAR_PROMPT

    if not isinstance(fuels, list) or len(fuels) != 3:
        print(f"Warning: Invalid fuels {fuels}, using fallback")
        return FALLBACK_AVATAR_PROMPT

    if element not in ELEMENT_VISUALS:
        print(f"Warning: Invalid element '{element}', using fallback")
        return FALLBACK_AVATAR_PROMPT

    # Build context for Claude
    universe_desc = UNIVERSE_VISUALS[universe]
    fuel_descs = [FUEL_VISUALS.get(f, f) for f in fuels]
    element_desc = ELEMENT_VISUALS[element]

    system_prompt = """You are a creative prompt engineer. Generate an image generation prompt for transforming a selfie into a stylized wizard avatar.

Output ONLY the image generation prompt, no explanations or preamble. Keep it under 150 words."""

    user_prompt = f"""The user selected these preferences:
- Universe: {universe} ({universe_desc})
- Interests: {fuels[0]} ({fuel_descs[0]}), {fuels[1]} ({fuel_descs[1]}), {fuels[2]} ({fuel_descs[2]})
- Element: {element} ({element_desc})

Write a detailed prompt that:
1. Keeps the person's likeness recognizable but stylized as digital art
2. Incorporates the universe aesthetic as the overall setting/style
3. Weaves in visual elements from their 3 interests as props, clothing, or background details
4. Features their element as magical effects, aura, or energy
5. Maintains a friendly, confident expression
6. Creates something fun and shareable - a profile picture they'd be proud of"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
            system=system_prompt,
        )

        prompt = response.content[0].text.strip()

        # Basic sanity check
        if len(prompt) < 50:
            print(f"Warning: Generated prompt too short ({len(prompt)} chars)")
            return FALLBACK_AVATAR_PROMPT

        return prompt

    except anthropic.APITimeoutError:
        print("Warning: Claude API timeout, using fallback prompt")
        return FALLBACK_AVATAR_PROMPT
    except anthropic.APIError as e:
        print(f"Warning: Claude API error: {e}, using fallback prompt")
        return FALLBACK_AVATAR_PROMPT
    except Exception as e:
        print(f"Warning: Unexpected error generating prompt: {e}")
        return FALLBACK_AVATAR_PROMPT


def generate_vibe_plan(wishlist_app: str) -> tuple:
    """
    Generate a vibe coding kickstart plan for the user's app idea.

    Args:
        wishlist_app: User's description of what they want to build

    Returns:
        Tuple of (plan_content, success)
        - plan_content: HTML-formatted plan or error message
        - success: True if generation succeeded
    """
    client = get_claude_client()

    # Validate input
    if not wishlist_app or not wishlist_app.strip():
        return (VIBE_PLAN_ERROR_MESSAGE, False)

    if not client:
        return (VIBE_PLAN_ERROR_MESSAGE, False)

    wishlist_app = wishlist_app.strip()

    system_prompt = """You are a helpful AI assistant explaining how to "vibe code" - building software by describing what you want to an AI coding assistant.

Create a practical kickstart guide in HTML format. Use these exact HTML tags:
- <h3> for section headers
- <p> for paragraphs
- <ul> and <li> for bullet lists
- <ol> and <li> for numbered lists
- <strong> for emphasis
- <pre> for code/prompt blocks

Keep the guide under 1500 words. Be encouraging, practical, and actionable. The audience is IT professionals who may be new to AI-assisted development."""

    user_prompt = f"""The user wants to build or automate: "{wishlist_app}"

Create a vibe coding kickstart guide with these sections:

<h3>The Vision</h3>
Brief description of what they want to build and why it's achievable with AI assistance.

<h3>Suggested Tech Stack</h3>
Recommend simple, beginner-friendly technologies. Explain why each choice.

<h3>Core Features Breakdown</h3>
List 4-6 key features, prioritized. What's MVP vs nice-to-have?

<h3>Vibe Coding Approach</h3>
Step-by-step process: how to describe this to an AI, what to build first, how to iterate.

<h3>Your First Prompt</h3>
Give them an actual prompt they can paste into Claude or ChatGPT to get started.

<h3>Tips for Success</h3>
3-4 practical tips for vibe coding this specific project."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
            system=system_prompt,
        )

        plan = response.content[0].text.strip()

        # Basic sanity check
        if len(plan) < 200 or '<h3>' not in plan:
            print(f"Warning: Generated plan seems invalid (length: {len(plan)})")
            return (VIBE_PLAN_ERROR_MESSAGE, False)

        return (plan, True)

    except anthropic.APITimeoutError:
        print("Warning: Claude API timeout generating vibe plan")
        return (VIBE_PLAN_ERROR_MESSAGE, False)
    except anthropic.APIError as e:
        print(f"Warning: Claude API error generating vibe plan: {e}")
        return (VIBE_PLAN_ERROR_MESSAGE, False)
    except Exception as e:
        print(f"Warning: Unexpected error generating vibe plan: {e}")
        return (VIBE_PLAN_ERROR_MESSAGE, False)


def generate_avatar_async(avatar_id, email, selfie_base64, response_id, preferences=None):
    """Background task to generate avatar using Gemini.

    Args:
        avatar_id: UUID of the avatar record
        email: User's email address
        selfie_base64: Base64-encoded selfie image
        response_id: ID of the response record (for coordination)
        preferences: Optional dict with avatar_universe, avatar_fuels, avatar_element
    """
    print(f"[AVATAR] Starting generation for avatar_id={avatar_id}, email={email}")

    try:
        if not GEMINI_API_KEY:
            raise Exception("Gemini API key not configured")

        print(f"[AVATAR] API key present (length: {len(GEMINI_API_KEY)})")

        # Initialize Gemini client
        print("[AVATAR] Initializing Gemini client...")
        client = genai.Client(api_key=GEMINI_API_KEY)
        print("[AVATAR] Gemini client initialized")

        # Decode the selfie image
        print(f"[AVATAR] Decoding selfie image (base64 length: {len(selfie_base64)})")
        image_data = base64.b64decode(selfie_base64.split(',')[1] if ',' in selfie_base64 else selfie_base64)
        print(f"[AVATAR] Image decoded successfully (size: {len(image_data)} bytes)")

        # Generate personalized prompt or use fallback
        if preferences and all(k in preferences for k in ['avatar_universe', 'avatar_fuels', 'avatar_element']):
            print(f"[AVATAR] Generating personalized prompt from preferences: {preferences}")
            prompt = generate_avatar_prompt(
                universe=preferences['avatar_universe'],
                fuels=preferences['avatar_fuels'],
                element=preferences['avatar_element']
            )
            is_personalized = prompt != FALLBACK_AVATAR_PROMPT
            print(f"[AVATAR] Using {'personalized' if is_personalized else 'fallback'} prompt")
        else:
            print(f"[AVATAR] No preferences or incomplete preferences, using static prompt")
            prompt = FALLBACK_AVATAR_PROMPT

        # Upload the image and generate
        model_name = "gemini-3-pro-image-preview"
        print(f"[AVATAR] Calling Gemini API with model: {model_name}")

        response = client.models.generate_content(
            model=model_name,
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

        print(f"[AVATAR] Gemini API response received")
        print(f"[AVATAR] Response candidates: {len(response.candidates) if response.candidates else 0}")

        # Extract the generated image
        generated_image = None
        if response.candidates:
            print(f"[AVATAR] Candidate 0 parts: {len(response.candidates[0].content.parts) if response.candidates[0].content.parts else 0}")
            for i, part in enumerate(response.candidates[0].content.parts):
                print(f"[AVATAR] Part {i}: has_inline_data={part.inline_data is not None}, has_text={part.text is not None if hasattr(part, 'text') else 'N/A'}")
                if part.inline_data:
                    print(f"[AVATAR] Found inline_data, mime_type={part.inline_data.mime_type}, size={len(part.inline_data.data)} bytes")
                    generated_image = base64.b64encode(part.inline_data.data).decode('utf-8')
                    break
                elif hasattr(part, 'text') and part.text:
                    print(f"[AVATAR] Text response: {part.text[:200]}...")

        if not generated_image:
            raise Exception("No image generated in response - check logs for details")

        print(f"[AVATAR] Image generated successfully (base64 length: {len(generated_image)})")

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
        print(f"[AVATAR] Database updated with completed status")

        # Check if we should send email (coordination with plan)
        print(f"[AVATAR] Checking email coordination for response_id={response_id}")
        check_and_send_email(response_id, email)
        print(f"[AVATAR] Generation complete for avatar_id={avatar_id}")

    except Exception as e:
        import traceback
        print(f"[AVATAR ERROR] Avatar generation failed: {e}")
        print(f"[AVATAR ERROR] Traceback: {traceback.format_exc()}")
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
        print(f"[AVATAR ERROR] Database updated with failed status")

        # Still check email in case plan is ready
        check_and_send_email(response_id, email)


def generate_plan_async(plan_id, email, wishlist_app, response_id):
    """Background task to generate vibe coding plan using Claude.

    Args:
        plan_id: UUID of the vibe_plan record
        email: User's email address
        wishlist_app: User's wishlist app description
        response_id: ID of the response record (for coordination)
    """
    print(f"[PLAN] Starting generation for plan_id={plan_id}, email={email}")

    try:
        plan_content, success = generate_vibe_plan(wishlist_app)

        conn = get_db()
        cur = conn.cursor()

        if success:
            cur.execute('''
                UPDATE vibe_plans
                SET plan_content = %s, status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (plan_content, plan_id))
            print(f"[PLAN] Plan generated successfully")
        else:
            cur.execute('''
                UPDATE vibe_plans
                SET status = 'failed', error_message = %s, completed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (plan_content, plan_id))  # plan_content contains error message on failure
            print(f"[PLAN] Plan generation failed: {plan_content}")

        conn.commit()
        cur.close()
        conn.close()

        # Check if we should send email
        check_and_send_email(response_id, email)

    except Exception as e:
        import traceback
        print(f"[PLAN ERROR] Plan generation failed: {e}")
        print(f"[PLAN ERROR] Traceback: {traceback.format_exc()}")

        conn = get_db()
        cur = conn.cursor()
        cur.execute('''
            UPDATE vibe_plans
            SET status = 'failed', error_message = %s, completed_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (str(e), plan_id))
        conn.commit()
        cur.close()
        conn.close()

        # Still check email
        check_and_send_email(response_id, email)


def check_and_send_email(response_id, email):
    """Check if all async tasks are complete and send combined email if ready.

    Called after each task (avatar or plan) completes. Only sends email once
    when all expected tasks are done.
    """
    print(f"[EMAIL] Checking coordination for response_id={response_id}")

    conn = get_db()
    cur = conn.cursor()

    # Check avatar status (if one exists for this response)
    cur.execute('''
        SELECT id, status, image_data FROM avatars WHERE response_id = %s
    ''', (response_id,))
    avatar = cur.fetchone()

    # Check plan status (if one exists for this response)
    cur.execute('''
        SELECT id, status, plan_content FROM vibe_plans WHERE response_id = %s
    ''', (response_id,))
    plan = cur.fetchone()

    cur.close()
    conn.close()

    # Determine what we're waiting for
    avatar_pending = avatar and avatar['status'] == 'pending'
    plan_pending = plan and plan['status'] == 'pending'

    if avatar_pending or plan_pending:
        print(f"[EMAIL] Still waiting - avatar_pending={avatar_pending}, plan_pending={plan_pending}")
        return

    # All tasks complete (or failed), send email
    avatar_data = None
    avatar_id = None
    if avatar and avatar['status'] == 'completed':
        avatar_id = avatar['id']
        avatar_data = avatar['image_data']

    plan_content = None
    if plan and plan['status'] == 'completed':
        plan_content = plan['plan_content']

    # Only send if we have something to share
    if avatar_id or plan_content:
        print(f"[EMAIL] All tasks complete, sending combined email (avatar={avatar_id is not None}, plan={plan_content is not None})")
        send_combined_email(email, avatar_id, plan_content)
    else:
        print(f"[EMAIL] No successful content to send for {email}")


def send_combined_email(email, avatar_id=None, plan_content=None):
    """Send email with avatar link and/or vibe coding plan.

    Args:
        email: Recipient email address
        avatar_id: UUID of completed avatar (optional)
        plan_content: HTML content of vibe plan (optional)
    """
    try:
        if not RESEND_API_KEY:
            print("Resend API key not configured, skipping email")
            return

        # Build email subject
        if avatar_id and plan_content:
            subject = "Your Wizard Avatar & Vibe Coding Plan are Ready!"
        elif avatar_id:
            subject = "Your Vibe Coding Wizard Avatar is Ready!"
        else:
            subject = "Your Vibe Coding Kickstart Plan is Ready!"

        # Build avatar section
        avatar_section = ""
        if avatar_id:
            avatar_url = f"{APP_URL}/avatar/{avatar_id}"
            avatar_section = f"""
                <div style="margin: 30px 0; text-align: center;">
                    <h2 style="color: #667eea;">Your Wizard Avatar</h2>
                    <p>Your personalized <strong>Vibe Coding Network Wizard</strong> avatar has been generated.</p>
                    <a href="{avatar_url}"
                       style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                              color: white;
                              padding: 15px 30px;
                              text-decoration: none;
                              border-radius: 8px;
                              font-weight: bold;
                              display: inline-block;
                              margin: 15px 0;">
                        View & Download Your Avatar
                    </a>
                </div>
            """

        # Build plan section
        plan_section = ""
        if plan_content:
            plan_section = f"""
                <div style="margin: 30px 0; padding: 20px; background: #f8f9fa; border-radius: 8px;">
                    <h2 style="color: #667eea; margin-top: 0;">Your Vibe Coding Kickstart Plan</h2>
                    <div style="line-height: 1.6;">
                        {plan_content}
                    </div>
                </div>
            """

        # Compose full email
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #667eea; text-align: center;">Thanks for completing the survey!</h1>
            <p style="font-size: 16px; color: #333; text-align: center;">
                Thank you for completing the Pre-Presentation Knowledge Assessment!
            </p>

            {avatar_section}

            {plan_section}

            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; text-align: center;">
                <p style="font-size: 14px; color: #666;">
                    See you at the presentation!
                </p>
            </div>
        </div>
        """

        resend.Emails.send({
            "from": "Vibe Coding Survey <no-reply@seanmahoney.ai>",
            "to": email,
            "subject": subject,
            "html": html_content
        })
        print(f"[EMAIL] Combined email sent to {email}")

    except Exception as e:
        print(f"[EMAIL ERROR] Email send error: {e}")


def send_avatar_email(email, avatar_id):
    """Send email notification when avatar is ready."""
    try:
        if not RESEND_API_KEY:
            print("Resend API key not configured, skipping email")
            return

        avatar_url = f"{APP_URL}/avatar/{avatar_id}"

        resend.Emails.send({
            "from": "Vibe Coding Survey <no-reply@seanmahoney.ai>",
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
        elif question['type'] == 'multi_select_exact':
            values = request.form.getlist(qid)
            # Validate exact count if provided
            if values:
                expected_count = question.get('select_count', 3)
                if len(values) != expected_count:
                    print(f"Warning: {qid} has {len(values)} items, expected {expected_count}")
                    values = []  # Clear invalid data
            responses[qid] = values
        else:
            responses[qid] = request.form.get(qid, '')

    # Get email and selfie
    email = request.form.get('email', '').lower().strip()
    selfie_data = request.form.get('selfie_data', '')

    # Extract preferences for avatar generation
    preferences = None
    if (responses.get('avatar_universe') and
        responses.get('avatar_fuels') and len(responses.get('avatar_fuels', [])) == 3 and
        responses.get('avatar_element')):
        preferences = {
            'avatar_universe': responses['avatar_universe'],
            'avatar_fuels': responses['avatar_fuels'],
            'avatar_element': responses['avatar_element']
        }
        print(f"[SUBMIT] Extracted preferences: {preferences}")

    # Save response to database
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO responses (email, data, selfie_data) VALUES (%s, %s, %s) RETURNING id',
        (email, json.dumps(responses), selfie_data if selfie_data else None)
    )
    response_id = cur.fetchone()['id']
    conn.commit()

    # Track what we're generating
    avatar_queued = False
    plan_queued = False

    # Check if we should generate an avatar
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

            # Start background generation with preferences
            thread = threading.Thread(
                target=generate_avatar_async,
                args=(avatar_id, email, selfie_data, response_id, preferences)
            )
            thread.daemon = True
            thread.start()
            print(f"[SUBMIT] Avatar generation queued for {email}")

    # Check if we should generate a vibe plan
    wishlist_app = responses.get('wishlist_app', '').strip()
    if email and wishlist_app:
        plan_id = str(uuid.uuid4())
        cur.execute(
            'INSERT INTO vibe_plans (id, email, response_id, wishlist_input, status) VALUES (%s, %s, %s, %s, %s)',
            (plan_id, email, response_id, wishlist_app, 'pending')
        )
        conn.commit()
        plan_queued = True

        # Start background plan generation
        thread = threading.Thread(
            target=generate_plan_async,
            args=(plan_id, email, wishlist_app, response_id)
        )
        thread.daemon = True
        thread.start()
        print(f"[SUBMIT] Plan generation queued for {email}")

    cur.close()
    conn.close()

    return render_template('thanks.html',
                          avatar_queued=avatar_queued,
                          plan_queued=plan_queued,
                          email=email)


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


@app.route('/admin/delete-avatar/<uuid:avatar_id>', methods=['POST'])
def delete_avatar(avatar_id):
    """Delete a failed avatar so user can retry."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM avatars WHERE id = %s', (str(avatar_id),))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin'))


@app.route('/admin/clear-failed-avatars', methods=['POST'])
def clear_failed_avatars():
    """Delete all failed avatars."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM avatars WHERE status = 'failed'")
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin'))


# Initialize database on import (for production with gunicorn)
if DATABASE_URL:
    init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
