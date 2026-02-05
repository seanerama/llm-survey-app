from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from functools import wraps
import json
import os
import uuid
import base64
import threading
import time
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
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'changeme')  # Set this in production!


def check_admin_auth(username, password):
    """Check if username/password is valid for admin access."""
    return username == 'admin' and password == ADMIN_PASSWORD


def require_admin(f):
    """Decorator to require admin authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_admin_auth(auth.username, auth.password):
            return Response(
                'Admin access required. Please log in.',
                401,
                {'WWW-Authenticate': 'Basic realm="Admin Area"'}
            )
        return f(*args, **kwargs)
    return decorated


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
            'type': 'radio_with_other',
            'label': 'What\'s one platform/app you use daily that you wish you could just chat with or automate?',
            'options': [
                'Email & Calendar (Outlook, Gmail)',
                'Spreadsheets & Reports (Excel, Google Sheets)',
                'Project Management (Jira, Trello, Asana)',
                'Document Creation (Word, Google Docs)',
                'CRM & Sales Tools (Salesforce, HubSpot)',
                'File Organization & Storage (SharePoint, Drive)',
                'Network Source of Truth (Netbox, Nautobot, Infrahub, IP Fabric, NetBrain, etc.)',
                'Network Security (CVE reporting & mitigation, FW rule checks, etc.)'
            ],
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
            'description': 'Select exactly 2 interests',
            'select_count': 2,
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

FALLBACK_AVATAR_PROMPT = """Transform this selfie into a stylized digital art portrait of a mythical hero. Create an illustrated character that maintains the person's likeness but in a fun, artistic style. They should look like a confident champion ready to build the future. Add glowing energy effects and a dynamic background. The style should be colorful and professional, suitable for a profile picture."""

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

    if not isinstance(fuels, list) or len(fuels) != 2:
        print(f"Warning: Invalid fuels {fuels}, using fallback")
        return FALLBACK_AVATAR_PROMPT

    if element not in ELEMENT_VISUALS:
        print(f"Warning: Invalid element '{element}', using fallback")
        return FALLBACK_AVATAR_PROMPT

    # Build context for Claude
    universe_desc = UNIVERSE_VISUALS[universe]
    fuel_descs = [FUEL_VISUALS.get(f, f) for f in fuels]
    element_desc = ELEMENT_VISUALS[element]

    # Map universes to fitting character archetypes
    universe_archetypes = {
        'scifi': 'space captain, starship pilot, or galactic explorer',
        'fantasy': 'legendary hero, mystical ranger, or arcane mage',
        'cyberpunk': 'netrunner, street samurai, or rogue hacker',
        'retro': 'arcade champion, pixel warrior, or retro game hero',
        'nature': 'forest guardian, elemental druid, or nature spirit',
        'steampunk': 'airship captain, clockwork inventor, or brass-clad adventurer',
        'cosmic': 'cosmic voyager, astral being, or starborn guardian',
        'postapoc': 'wasteland survivor, road warrior, or resistance fighter',
        'noir': 'hardboiled detective, shadow operative, or mystery solver',
        'underwater': 'deep sea explorer, ocean guardian, or aquatic adventurer',
    }
    archetype = universe_archetypes.get(universe, 'mythical hero')

    system_prompt = """You are a creative prompt engineer. Generate an image generation prompt for transforming a selfie into a stylized character avatar.

Output ONLY the image generation prompt, no explanations or preamble. Keep it under 150 words. Make the character feel powerful and heroic - like the protagonist of their own story."""

    user_prompt = f"""The user selected these preferences:
- Universe: {universe} ({universe_desc})
- Character type: {archetype}
- Interests: {fuels[0]} ({fuel_descs[0]}), {fuels[1]} ({fuel_descs[1]})
- Element: {element} ({element_desc})

Write a detailed prompt that:
1. Keeps the person's likeness recognizable but stylized as digital art
2. Makes them look like a {archetype} in a {universe} setting
3. Incorporates the universe aesthetic as the overall setting/style
4. Weaves in visual elements from their 2 interests as props, clothing, or background details
5. Features their element as powers, aura, or energy effects
6. Maintains a confident, heroic expression
7. Creates something fun and shareable - a profile picture they'd be proud of"""

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


PREGENERATED_PLANS = {
    'Email & Calendar (Outlook, Gmail)': """
<h3>The Vision</h3>
<p>Imagine being able to type <strong>"Schedule a meeting with the dev team next Tuesday at 2pm"</strong> or <strong>"Show me all emails from Sarah about the budget"</strong> into a simple chat interface — and have it just happen. That's what you're building: an AI-powered assistant that talks to your email and calendar so you don't have to click through menus.</p>
<p>The best part? You don't need to write a single line of code yourself. You'll describe what you want to an AI like Claude or ChatGPT, and it writes all the code for you.</p>

<h3>Suggested Tech Stack</h3>
<ul>
<li><strong>Python</strong> — The AI will write it all for you. You just copy, paste, and run.</li>
<li><strong>Streamlit</strong> — Creates a simple chat-style web interface with almost no setup.</li>
<li><strong>Microsoft Graph API</strong> (for Outlook/Microsoft 365) or <strong>Gmail API</strong> — These are the official ways to read emails and manage calendars programmatically.</li>
<li><strong>Claude or OpenAI API</strong> — Powers the natural language understanding so you can talk in plain English.</li>
</ul>

<h3>Core Features Breakdown</h3>
<ol>
<li><strong>Natural language email search</strong> — Ask "What did John send me last week?" and get results.</li>
<li><strong>Calendar event creation</strong> — Say "Block off Friday afternoon" and it creates the event.</li>
<li><strong>Email summarization</strong> — "Summarize my unread emails" gives you a quick digest.</li>
<li><strong>Meeting scheduling</strong> — "Find a free slot with Sarah this week" checks both calendars.</li>
</ol>

<h3>Vibe Coding Approach</h3>
<ol>
<li><strong>Start here:</strong> Ask Claude to build a basic Streamlit chat app that connects to the Gmail or Outlook API.</li>
<li><strong>Run it:</strong> Open your terminal (the black window where you type commands), paste <code>streamlit run app.py</code>, and see it in your browser.</li>
<li><strong>Iterate:</strong> If something doesn't work, copy the error message and paste it back to Claude. Say "I got this error, can you fix it?"</li>
<li><strong>Add features one at a time:</strong> Get email reading working first, then add calendar, then add natural language commands.</li>
</ol>

<h3>Your First Prompt</h3>
<pre>Build me a Python Streamlit app that connects to the Gmail API. It should have a chat interface where I can type "show my unread emails" and it displays them. Start with just reading emails - I'll add more features later. Include setup instructions for someone who has never used Python before.</pre>

<h3>Tips for Success</h3>
<ul>
<li>Start with <strong>read-only</strong> features (searching/reading emails) before moving to actions (sending, scheduling).</li>
<li>Don't be afraid to say <strong>"That didn't work, here's the error message"</strong> — the AI is great at debugging.</li>
<li>Google/Microsoft will ask you to set up API credentials. Ask Claude to walk you through it step by step.</li>
<li>Test with your own email first before sharing with anyone else.</li>
</ul>""",

    'Spreadsheets & Reports (Excel, Google Sheets)': """
<h3>The Vision</h3>
<p>What if you could just say <strong>"Create a summary report of Q4 sales by region"</strong> or <strong>"Highlight all rows where spending is over budget"</strong> instead of writing complex formulas? You're going to build a chat assistant that reads, analyzes, and updates your spreadsheets using plain English.</p>
<p>No coding experience needed — you'll describe what you want and let AI write every line of code.</p>

<h3>Suggested Tech Stack</h3>
<ul>
<li><strong>Python</strong> — Claude will write it all. You just run it.</li>
<li><strong>Streamlit</strong> — Gives you a drag-and-drop file upload and chat interface instantly.</li>
<li><strong>Pandas</strong> — A Python library that makes working with spreadsheet data incredibly easy (the AI handles this part).</li>
<li><strong>OpenPyXL</strong> — Reads and writes Excel files directly.</li>
</ul>

<h3>Core Features Breakdown</h3>
<ol>
<li><strong>Upload and chat</strong> — Drag in an Excel/CSV file and ask questions about the data.</li>
<li><strong>Natural language analysis</strong> — "What's the average sales per region?" returns an instant answer.</li>
<li><strong>Auto-generate reports</strong> — "Create a pivot table of expenses by department" builds it for you.</li>
<li><strong>Data cleanup</strong> — "Remove duplicate rows" or "Fix the date format in column C."</li>
</ol>

<h3>Vibe Coding Approach</h3>
<ol>
<li><strong>Start here:</strong> Ask Claude to build a Streamlit app where you upload a CSV file and ask questions about it.</li>
<li><strong>Run it:</strong> Open your terminal, type <code>streamlit run app.py</code>, and open the link in your browser.</li>
<li><strong>Iterate:</strong> Upload one of your real spreadsheets and try asking questions. If something's wrong, tell Claude.</li>
<li><strong>Expand:</strong> Add Excel support, chart generation, and the ability to download modified files.</li>
</ol>

<h3>Your First Prompt</h3>
<pre>Build me a Python Streamlit app where I can upload a CSV or Excel file and then ask questions about the data in a chat interface. For example, I should be able to ask "What's the total for column B?" or "Show me rows where status is Pending." Use pandas for data handling. Include setup instructions for a beginner.</pre>

<h3>Tips for Success</h3>
<ul>
<li>Start with <strong>CSV files</strong> first (they're simpler), then add Excel support.</li>
<li>Use a <strong>small sample spreadsheet</strong> for testing — don't start with a 100,000-row file.</li>
<li>If the AI gives wrong answers about your data, try saying <strong>"Here are the column names: [list them]"</strong> for better results.</li>
<li>Ask Claude to add a <strong>"Download results"</strong> button so you can save any analysis back to a file.</li>
</ul>""",

    'Project Management (Jira, Trello, Asana)': """
<h3>The Vision</h3>
<p>Instead of clicking through boards and forms, imagine saying <strong>"Create a bug ticket for the login page crash, high priority, assign to DevOps"</strong> or <strong>"What tickets are blocking the release?"</strong> in a simple chat. You're building an AI assistant that talks to your project management tool.</p>
<p>You won't write any code — just describe what you want and let AI build it.</p>

<h3>Suggested Tech Stack</h3>
<ul>
<li><strong>Python</strong> — The AI writes everything. You just run it.</li>
<li><strong>Streamlit</strong> — Simple chat interface, no web development needed.</li>
<li><strong>Jira REST API / Trello API / Asana API</strong> — The official way to interact with these tools programmatically.</li>
<li><strong>Claude or OpenAI API</strong> — Understands your plain English requests and translates them to API calls.</li>
</ul>

<h3>Core Features Breakdown</h3>
<ol>
<li><strong>Quick ticket creation</strong> — "Create a task: Update firewall rules, assign to network team, due Friday."</li>
<li><strong>Status queries</strong> — "What's open in the current sprint?" or "Show me all my tickets."</li>
<li><strong>Bulk updates</strong> — "Move all QA-approved tickets to Done."</li>
<li><strong>Sprint summaries</strong> — "Give me a summary of what shipped this sprint."</li>
</ol>

<h3>Vibe Coding Approach</h3>
<ol>
<li><strong>Start here:</strong> Ask Claude to build a Streamlit app that connects to Jira's REST API and lists your current tickets.</li>
<li><strong>Run it:</strong> Open your terminal, type <code>streamlit run app.py</code>, and test it.</li>
<li><strong>Iterate:</strong> Once reading works, ask Claude to add ticket creation through the chat interface.</li>
<li><strong>Expand:</strong> Add natural language queries like "Show all critical bugs assigned to me."</li>
</ol>

<h3>Your First Prompt</h3>
<pre>Build me a Python Streamlit app that connects to Jira using its REST API. Start with a simple chat interface where I can type "show my tickets" and it lists my assigned issues. I'll need instructions on how to get a Jira API token. Make it beginner-friendly — I've never used Python before.</pre>

<h3>Tips for Success</h3>
<ul>
<li>Start with <strong>read-only</strong> actions (listing tickets) before adding create/update capabilities.</li>
<li>You'll need an <strong>API token</strong> from your project tool — ask Claude to walk you through getting one.</li>
<li>Test with a <strong>sandbox project</strong> first so you don't accidentally modify real work items.</li>
<li>If your company restricts API access, check with your admin — you may need permission first.</li>
</ul>""",

    'Document Creation (Word, Google Docs)': """
<h3>The Vision</h3>
<p>What if you could say <strong>"Draft a change management document for the network upgrade"</strong> or <strong>"Create a weekly status report from these bullet points"</strong> and get a polished document instantly? You're building an AI assistant that creates and manages documents for you.</p>
<p>No coding required — you describe what you want and AI builds the whole thing.</p>

<h3>Suggested Tech Stack</h3>
<ul>
<li><strong>Python</strong> — Claude writes all the code. You just run it.</li>
<li><strong>Streamlit</strong> — Simple interface for chatting and downloading documents.</li>
<li><strong>python-docx</strong> — Creates Word documents programmatically.</li>
<li><strong>Google Docs API</strong> — If you prefer Google Docs over Word files.</li>
</ul>

<h3>Core Features Breakdown</h3>
<ol>
<li><strong>Document generation</strong> — Describe what you need, get a formatted Word doc or Google Doc.</li>
<li><strong>Template filling</strong> — "Fill in the change request template for server migration on March 15th."</li>
<li><strong>Report compilation</strong> — "Combine these notes into a weekly status report."</li>
<li><strong>Format conversion</strong> — Upload rough notes, get back a polished document.</li>
</ol>

<h3>Vibe Coding Approach</h3>
<ol>
<li><strong>Start here:</strong> Ask Claude to build a Streamlit app where you type a document description and it generates a downloadable Word file.</li>
<li><strong>Run it:</strong> Open your terminal, type <code>streamlit run app.py</code>, and try it out.</li>
<li><strong>Iterate:</strong> If the formatting isn't right, tell Claude what you want changed.</li>
<li><strong>Expand:</strong> Add templates, upload existing docs for editing, or connect to Google Docs.</li>
</ol>

<h3>Your First Prompt</h3>
<pre>Build me a Python Streamlit app where I can describe a document I need in a text box, and it generates a formatted Word document (.docx) that I can download. For example, if I type "weekly status report for the infrastructure team," it should create a professional document with appropriate sections. Include setup instructions for a complete beginner.</pre>

<h3>Tips for Success</h3>
<ul>
<li>Start with <strong>Word file generation</strong> — it's simpler than the Google Docs API.</li>
<li>Create a few <strong>document templates</strong> that match what you actually write at work.</li>
<li>Ask Claude to add a <strong>"refine" feature</strong> where you can say "make the executive summary shorter."</li>
<li>You can always copy-paste the AI output into your existing templates if you prefer.</li>
</ul>""",

    'CRM & Sales Tools (Salesforce, HubSpot)': """
<h3>The Vision</h3>
<p>Instead of navigating through endless CRM screens, imagine typing <strong>"Show me all deals closing this month over $50k"</strong> or <strong>"Log a call with Acme Corp — discussed renewal, they want a demo next week."</strong> You're building a chat interface to your CRM that saves time on every interaction.</p>
<p>You don't need to code — just describe what you want and AI builds it for you.</p>

<h3>Suggested Tech Stack</h3>
<ul>
<li><strong>Python</strong> — Claude writes it all. You copy, paste, and run.</li>
<li><strong>Streamlit</strong> — Instant chat interface, no web development skills needed.</li>
<li><strong>Salesforce REST API / HubSpot API</strong> — Official APIs to read and write CRM data.</li>
<li><strong>Claude or OpenAI API</strong> — Translates your plain English into CRM queries and updates.</li>
</ul>

<h3>Core Features Breakdown</h3>
<ol>
<li><strong>Natural language queries</strong> — "Show all open opportunities for Q1" returns results instantly.</li>
<li><strong>Quick data entry</strong> — "Add a note to the Acme Corp account: discussed pricing on Feb 5th."</li>
<li><strong>Pipeline summaries</strong> — "Give me a forecast summary for this quarter."</li>
<li><strong>Contact lookup</strong> — "Who's our contact at Globex? When did we last talk to them?"</li>
</ol>

<h3>Vibe Coding Approach</h3>
<ol>
<li><strong>Start here:</strong> Ask Claude to build a Streamlit app that connects to the Salesforce or HubSpot API and lists recent deals.</li>
<li><strong>Run it:</strong> Open your terminal, type <code>streamlit run app.py</code>, and check the results.</li>
<li><strong>Iterate:</strong> Once reading works, add the ability to search and filter with natural language.</li>
<li><strong>Expand:</strong> Add note logging, contact management, and pipeline reporting.</li>
</ol>

<h3>Your First Prompt</h3>
<pre>Build me a Python Streamlit app that connects to the Salesforce REST API (or HubSpot API). It should have a chat interface where I can type "show my open deals" and see a list of my current opportunities. Include step-by-step instructions for getting API credentials and setting up Python for the first time.</pre>

<h3>Tips for Success</h3>
<ul>
<li>Start with <strong>read-only access</strong> to your CRM before adding write operations.</li>
<li>Use a <strong>sandbox or developer account</strong> for testing — don't experiment with production data.</li>
<li>Salesforce and HubSpot both have <strong>free developer accounts</strong> — ask Claude how to set one up.</li>
<li>If you get authentication errors, paste the full error into Claude and ask it to help troubleshoot.</li>
</ul>""",

    'File Organization & Storage (SharePoint, Drive)': """
<h3>The Vision</h3>
<p>Tired of digging through nested folders to find that one document? Imagine saying <strong>"Find the network diagram we updated last month"</strong> or <strong>"Move all the Q4 reports into the archive folder."</strong> You're building a chat assistant that manages your files using plain English.</p>
<p>No coding experience needed — AI writes everything for you.</p>

<h3>Suggested Tech Stack</h3>
<ul>
<li><strong>Python</strong> — Claude handles all the code. You just run it.</li>
<li><strong>Streamlit</strong> — Simple chat interface for file operations.</li>
<li><strong>Microsoft Graph API</strong> (for SharePoint/OneDrive) or <strong>Google Drive API</strong> — Official file management APIs.</li>
<li><strong>Claude or OpenAI API</strong> — Understands what you're asking for and translates it to file operations.</li>
</ul>

<h3>Core Features Breakdown</h3>
<ol>
<li><strong>Natural language search</strong> — "Find all PowerPoints about the budget from last quarter."</li>
<li><strong>File organization</strong> — "Move everything in Downloads older than 30 days to Archive."</li>
<li><strong>Content search</strong> — "Which documents mention the VPN migration?"</li>
<li><strong>Quick sharing</strong> — "Share the project plan with the infrastructure team."</li>
</ol>

<h3>Vibe Coding Approach</h3>
<ol>
<li><strong>Start here:</strong> Ask Claude to build a Streamlit app that connects to Google Drive or SharePoint and lists files in a folder.</li>
<li><strong>Run it:</strong> Open your terminal, type <code>streamlit run app.py</code>, and verify it shows your files.</li>
<li><strong>Iterate:</strong> Add search capabilities next — "find files matching X."</li>
<li><strong>Expand:</strong> Add move/copy operations, bulk organization, and content search.</li>
</ol>

<h3>Your First Prompt</h3>
<pre>Build me a Python Streamlit app that connects to Google Drive (or SharePoint via Microsoft Graph API). It should have a chat interface where I can type "show files in my Documents folder" or "find files named budget." Start simple with listing and searching. Include setup instructions for someone who has never coded before.</pre>

<h3>Tips for Success</h3>
<ul>
<li>Start with <strong>listing and searching</strong> before adding move/delete operations.</li>
<li>Always add a <strong>confirmation step</strong> before deleting or moving files — mistakes are hard to undo.</li>
<li>Test with a <strong>non-critical folder</strong> first — don't point it at your most important files right away.</li>
<li>The API credentials setup can be tricky — ask Claude to guide you through it step by step.</li>
</ul>""",

    'Network Source of Truth (Netbox, Nautobot, Infrahub, IP Fabric, NetBrain, etc.)': """
<h3>The Vision</h3>
<p>What if you could just ask <strong>"What IP addresses are assigned in the 10.50.0.0/24 subnet?"</strong> or <strong>"Show me all switches in the NYC data center that are end-of-life"</strong> instead of clicking through your source of truth UI? You're building a natural language chat interface to your network source of truth.</p>
<p>No coding required — you describe what you want and AI builds everything.</p>

<h3>Suggested Tech Stack</h3>
<ul>
<li><strong>Python</strong> — Claude writes all the code. You just run it.</li>
<li><strong>Streamlit</strong> — Gives you an instant chat interface with no web development.</li>
<li><strong>NetBox/Nautobot REST API</strong> — These tools have excellent APIs for querying and updating network data.</li>
<li><strong>Claude or OpenAI API</strong> — Translates your plain English into the right API calls.</li>
</ul>

<h3>Core Features Breakdown</h3>
<ol>
<li><strong>Device lookups</strong> — "Show me all Cisco 9300s in the Dallas site" returns a clean table.</li>
<li><strong>IP address management</strong> — "What's the next available IP in the server VLAN?" gives you an answer instantly.</li>
<li><strong>Circuit and connection queries</strong> — "What's connected to port Gi1/0/24 on switch NYC-ACC-01?"</li>
<li><strong>Inventory reports</strong> — "How many devices are running IOS-XE 17.3 or older?"</li>
<li><strong>Change planning</strong> — "List all interfaces in VLAN 100 across all sites."</li>
</ol>

<h3>Vibe Coding Approach</h3>
<ol>
<li><strong>Start here:</strong> Ask Claude to build a Streamlit app that connects to your NetBox/Nautobot API and lists devices.</li>
<li><strong>Run it:</strong> Open your terminal, type <code>streamlit run app.py</code>, and verify it pulls your devices.</li>
<li><strong>Iterate:</strong> Add natural language search — "show me all firewalls" should filter devices by role.</li>
<li><strong>Expand:</strong> Add IP address lookups, interface queries, and the ability to create reservations.</li>
</ol>

<h3>Your First Prompt</h3>
<pre>Build me a Python Streamlit app that connects to a NetBox instance via its REST API. It should have a chat interface where I can ask things like "show all devices in site NYC" or "what IPs are in the 10.0.1.0/24 prefix?" I'll provide the NetBox URL and API token. Include instructions for setting up Python and getting a NetBox API token.</pre>

<h3>Tips for Success</h3>
<ul>
<li>Start with <strong>read-only queries</strong> (device lookups, IP searches) before adding create/update operations.</li>
<li>NetBox and Nautobot both have <strong>excellent API documentation</strong> — tell Claude which platform you use and it will know the API endpoints.</li>
<li>Use your <strong>staging/lab instance</strong> for testing, not production, especially when adding write operations.</li>
<li>If you use IP Fabric or NetBrain, the APIs are different — just tell Claude which tool you have and it will adapt.</li>
</ul>""",

    'Network Security (CVE reporting & mitigation, FW rule checks, etc.)': """
<h3>The Vision</h3>
<p>Imagine asking <strong>"Are any of our Cisco devices affected by CVE-2024-20356?"</strong> or <strong>"Show me all firewall rules that allow any-to-any"</strong> and getting an instant answer. You're building an AI-powered network security assistant that checks vulnerabilities, audits firewall rules, and helps you stay on top of your security posture.</p>
<p>You don't need to write code — you'll describe what you want and let AI build it all.</p>

<h3>Suggested Tech Stack</h3>
<ul>
<li><strong>Python</strong> — Claude writes everything. You copy, paste, and run.</li>
<li><strong>Streamlit</strong> — Simple chat interface, no web development needed.</li>
<li><strong>NVD/NIST API</strong> — Free access to the National Vulnerability Database for CVE lookups.</li>
<li><strong>Your firewall's API</strong> (Palo Alto Panorama, Fortinet FortiManager, Cisco FMC, etc.) — For pulling and auditing rules.</li>
<li><strong>Claude or OpenAI API</strong> — Understands your security questions and generates actionable reports.</li>
</ul>

<h3>Core Features Breakdown</h3>
<ol>
<li><strong>CVE impact checks</strong> — "Which of our devices are affected by this CVE?" cross-references your inventory with vulnerability data.</li>
<li><strong>Firewall rule audits</strong> — "Show me all rules with 'any' in the source or destination" flags overly permissive rules.</li>
<li><strong>Mitigation guidance</strong> — "What's the recommended fix for CVE-2024-12345?" pulls remediation steps.</li>
<li><strong>Compliance checks</strong> — "Do any rules violate our policy of no direct internet access from the server VLAN?"</li>
<li><strong>Security summaries</strong> — "Give me a weekly vulnerability report for all critical-severity CVEs affecting our platform."</li>
</ol>

<h3>Vibe Coding Approach</h3>
<ol>
<li><strong>Start here:</strong> Ask Claude to build a Streamlit app that queries the NVD API for CVE details when you type a CVE ID.</li>
<li><strong>Run it:</strong> Open your terminal, type <code>streamlit run app.py</code>, and test with a known CVE.</li>
<li><strong>Iterate:</strong> Add the ability to cross-reference CVEs against a list of your devices and software versions.</li>
<li><strong>Expand:</strong> Connect to your firewall's API to pull rules and run audit checks via chat.</li>
</ol>

<h3>Your First Prompt</h3>
<pre>Build me a Python Streamlit app for network security. It should have a chat interface where I can type a CVE ID (like CVE-2024-20356) and it pulls the details from the NIST NVD API — severity, affected products, and remediation info. Also let me upload a CSV of my network devices (hostname, vendor, OS version) and ask "which of my devices are affected by this CVE?" Include beginner-friendly setup instructions.</pre>

<h3>Tips for Success</h3>
<ul>
<li>Start with <strong>CVE lookups against the free NVD API</strong> before trying to connect to firewalls — it's the easiest win.</li>
<li>Keep a <strong>CSV inventory of your devices</strong> (hostname, vendor, OS, version) — this is the simplest way to cross-reference vulnerabilities.</li>
<li>When connecting to firewall APIs, always use <strong>read-only credentials</strong> — you never want an AI assistant accidentally modifying security rules.</li>
<li>Ask Claude to add <strong>severity filtering</strong> — most teams only need to act on Critical and High CVEs immediately.</li>
</ul>""",
}


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

    system_prompt = """You are a helpful AI assistant explaining how to "vibe code" - building software by describing what you want to an AI coding assistant like Claude or ChatGPT. The user does NOT need to know how to code. They just describe what they want in plain English and the AI writes the code for them.

IMPORTANT CONTEXT:
- If the user mentions an existing product/platform (like ServiceNow, Salesforce, Jira, SAP, etc.), they want to build an AI-powered natural language interface TO that product - a way to chat with it, automate it, or query it using plain English. They are NOT trying to rebuild the product itself.
- The audience is IT professionals who may have ZERO coding or DevOps experience. Assume they've never used a terminal, never deployed anything, and don't know what an API is. Explain everything simply.
- Vibe coding means: you describe what you want, the AI writes the code, you test it, you describe fixes, repeat. No manual coding required.

Create a practical kickstart guide in HTML format. Use these exact HTML tags:
- <h3> for section headers
- <p> for paragraphs
- <ul> and <li> for bullet lists
- <ol> and <li> for numbered lists
- <strong> for emphasis
- <pre> for code/prompt blocks

Keep the guide under 1500 words. Be encouraging and emphasize that they don't need to know how to code."""

    user_prompt = f"""The user wants to interact with, automate, or build something related to: "{wishlist_app}"

If this is an existing product/platform, assume they want to build an AI-powered chatbot or natural language interface that connects to it - so they can ask questions or give commands in plain English instead of clicking through menus.

Create a vibe coding kickstart guide with these sections:

<h3>The Vision</h3>
Describe what they're building (likely an AI chat interface to {wishlist_app}). Emphasize this is totally achievable without coding experience - they'll describe what they want and let Claude/ChatGPT write all the code.

<h3>Suggested Tech Stack</h3>
Recommend the SIMPLEST possible approach. Consider:
- Python (Claude can write it all for you)
- Streamlit or Gradio for a simple chat UI (no web development needed)
- If {wishlist_app} has an API, mention it. If not, suggest alternatives.
Explain each choice in plain English - no jargon.

<h3>Core Features Breakdown</h3>
List 3-5 key features for an MVP. Keep it simple. What's the minimum they need to have a working demo?

<h3>Vibe Coding Approach</h3>
Step-by-step process assuming ZERO coding experience:
1. What to ask Claude/ChatGPT first
2. How to run the code it gives you (explain what a terminal is if needed)
3. How to describe problems when something doesn't work
4. How to iterate until it works

<h3>Your First Prompt</h3>
Give them an ACTUAL prompt they can copy-paste into Claude or ChatGPT right now to get started. Make it specific to their use case.

<h3>Tips for Success</h3>
3-4 practical tips for someone who has never coded before. Include things like:
- Don't be afraid to say "that didn't work, here's the error message"
- Start small and add features one at a time
- It's okay to ask the AI to explain what the code does"""

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

    # Retry configuration
    MAX_RETRIES = 3
    BASE_DELAY = 2  # seconds
    RETRYABLE_ERRORS = ['503', 'UNAVAILABLE', 'overloaded', '429', 'RESOURCE_EXHAUSTED']

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

        # Upload the image and generate with retry logic
        model_name = "gemini-3-pro-image-preview"
        response = None
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                print(f"[AVATAR] Calling Gemini API with model: {model_name} (attempt {attempt + 1}/{MAX_RETRIES})")

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
                # Success - break out of retry loop
                print(f"[AVATAR] Gemini API response received on attempt {attempt + 1}")
                break

            except Exception as api_error:
                last_error = api_error
                error_str = str(api_error)

                # Check if this is a retryable error
                is_retryable = any(err in error_str for err in RETRYABLE_ERRORS)

                if is_retryable and attempt < MAX_RETRIES - 1:
                    delay = BASE_DELAY * (2 ** attempt)  # Exponential backoff: 2s, 4s, 8s
                    print(f"[AVATAR] Retryable error on attempt {attempt + 1}: {error_str}")
                    print(f"[AVATAR] Waiting {delay}s before retry...")
                    time.sleep(delay)
                else:
                    # Not retryable or last attempt - re-raise
                    print(f"[AVATAR] Non-retryable error or max retries reached: {error_str}")
                    raise api_error

        if response is None:
            raise last_error or Exception("No response from Gemini API after retries")

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
        # Check for pre-generated plan first (for predefined radio options)
        if wishlist_app in PREGENERATED_PLANS:
            print(f"[PLAN] Using pre-generated plan for: {wishlist_app}")
            plan_content = PREGENERATED_PLANS[wishlist_app]
            success = True
        else:
            print(f"[PLAN] Custom 'Other' input, calling Claude API: {wishlist_app}")
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
        send_combined_email(email, avatar_id, avatar_data, plan_content)
    else:
        print(f"[EMAIL] No successful content to send for {email}")


def send_combined_email(email, avatar_id=None, avatar_data=None, plan_content=None):
    """Send email with embedded avatar image and/or vibe coding plan.

    Args:
        email: Recipient email address
        avatar_id: UUID of completed avatar (optional)
        avatar_data: Base64-encoded avatar image data (optional)
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

        # Build avatar section with embedded image
        avatar_section = ""
        attachments = []
        if avatar_id and avatar_data:
            # Embed image directly in email using CID
            avatar_section = f"""
                <div style="margin: 30px 0; text-align: center;">
                    <h2 style="color: #667eea;">Your Wizard Avatar</h2>
                    <p>Your personalized <strong>Vibe Coding Network Wizard</strong> avatar has been generated!</p>
                    <img src="cid:avatar_image" alt="Your Wizard Avatar"
                         style="max-width: 400px; width: 100%; border-radius: 12px; margin: 15px 0; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
                    <p style="font-size: 14px; color: #666; margin-top: 10px;">
                        Right-click on the image to save it, or view full-size at:<br>
                        <a href="{APP_URL}/avatar/{avatar_id}" style="color: #667eea;">{APP_URL}/avatar/{avatar_id}</a>
                    </p>
                </div>
            """
            # Add image as CID attachment
            attachments.append({
                "content": avatar_data,
                "filename": "wizard-avatar.png",
                "content_id": "avatar_image"
            })

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

        email_params = {
            "from": "Vibe Coding Survey <survey@seanmahoney.ai>",
            "to": email,
            "subject": subject,
            "html": html_content
        }

        # Add attachments if we have an embedded avatar
        if attachments:
            email_params["attachments"] = attachments

        resend.Emails.send(email_params)
        print(f"[EMAIL] Combined email sent to {email} (embedded_avatar={len(attachments) > 0})")

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
            "from": "Vibe Coding Survey <survey@seanmahoney.ai>",
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
        elif question['type'] == 'radio_with_other':
            value = request.form.get(qid, '')
            if value == '__other__':
                # Use the custom text from the "Other" field
                value = request.form.get(f'{qid}_other_text', '').strip()
            responses[qid] = value
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
        responses.get('avatar_fuels') and len(responses.get('avatar_fuels', [])) == 2 and
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
@require_admin
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
            max_rating = question.get('max_rating', 10)
            # Initialize distribution with all possible values
            distribution = {i: 0 for i in range(1, max_rating + 1)}
            for resp in responses:
                val = resp['data'].get(qid)
                if val:
                    try:
                        int_val = int(val)
                        values.append(int_val)
                        if 1 <= int_val <= max_rating:
                            distribution[int_val] += 1
                    except (ValueError, TypeError):
                        pass
            if values:
                stats[qid] = {
                    'average': round(sum(values) / len(values), 1),
                    'count': len(values),
                    'min': min(values),
                    'max': max(values),
                    'distribution': distribution
                }
            else:
                stats[qid] = {'average': 0, 'count': 0, 'min': 0, 'max': 0, 'distribution': distribution}

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
@require_admin
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
@require_admin
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
@require_admin
def clear_failed_avatars():
    """Delete all failed avatars."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM avatars WHERE status = 'failed'")
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin'))


@app.route('/admin/clear-all', methods=['POST'])
@require_admin
def clear_all_data():
    """Delete all responses, avatars, and vibe plans. Use for testing cleanup."""
    conn = get_db()
    cur = conn.cursor()
    # Delete in order to respect foreign keys
    cur.execute('DELETE FROM vibe_plans')
    cur.execute('DELETE FROM avatars')
    cur.execute('DELETE FROM responses')
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin'))


# Initialize database on import (for production with gunicorn)
if DATABASE_URL:
    init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
