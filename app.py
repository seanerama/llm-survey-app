from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import json
from datetime import datetime

app = Flask(__name__)
DATABASE = 'survey.db'

# Survey configuration - customize your questions here
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


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


@app.route('/')
def survey():
    return render_template('survey.html', config=SURVEY_CONFIG)


@app.route('/submit', methods=['POST'])
def submit():
    responses = {}
    for question in SURVEY_CONFIG['questions']:
        qid = question['id']
        if question['type'] == 'checkbox':
            responses[qid] = request.form.getlist(qid)
        else:
            responses[qid] = request.form.get(qid, '')

    conn = get_db()
    conn.execute('INSERT INTO responses (data) VALUES (?)', (json.dumps(responses),))
    conn.commit()
    conn.close()

    return render_template('thanks.html')


@app.route('/admin')
def admin():
    conn = get_db()
    rows = conn.execute('SELECT * FROM responses ORDER BY submitted_at DESC').fetchall()
    conn.close()

    responses = []
    for row in rows:
        responses.append({
            'id': row['id'],
            'data': json.loads(row['data']),
            'submitted_at': row['submitted_at']
        })

    # Calculate statistics for charts
    stats = {}
    mc_stats = {}  # Multiple choice stats
    text_responses = []  # For word cloud

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
                          stats=stats, mc_stats=mc_stats, text_responses=text_responses)


@app.route('/admin/delete/<int:response_id>', methods=['POST'])
def delete_response(response_id):
    conn = get_db()
    conn.execute('DELETE FROM responses WHERE id = ?', (response_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))


# Initialize database on import (for production with gunicorn)
init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
