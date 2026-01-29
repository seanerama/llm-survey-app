"""Stage 2 Survey Preferences Tests"""


def test_survey_config_has_preference_questions():
    """Verify SURVEY_CONFIG contains the 3 preference questions."""
    from app import SURVEY_CONFIG

    question_ids = [q['id'] for q in SURVEY_CONFIG['questions']]

    assert 'avatar_universe' in question_ids
    assert 'avatar_fuels' in question_ids
    assert 'avatar_element' in question_ids


def test_avatar_universe_options():
    """Verify avatar_universe has 10 options."""
    from app import SURVEY_CONFIG

    q = next(q for q in SURVEY_CONFIG['questions'] if q['id'] == 'avatar_universe')
    assert len(q['options']) == 10
    assert q['type'] == 'single_select'


def test_avatar_fuels_options():
    """Verify avatar_fuels has 10 options and select_count of 3."""
    from app import SURVEY_CONFIG

    q = next(q for q in SURVEY_CONFIG['questions'] if q['id'] == 'avatar_fuels')
    assert len(q['options']) == 10
    assert q['type'] == 'multi_select_exact'
    assert q['select_count'] == 3


def test_avatar_element_options():
    """Verify avatar_element has 8 options."""
    from app import SURVEY_CONFIG

    q = next(q for q in SURVEY_CONFIG['questions'] if q['id'] == 'avatar_element')
    assert len(q['options']) == 8
    assert q['type'] == 'single_select'


def test_preference_questions_are_optional():
    """Verify all preference questions are not required."""
    from app import SURVEY_CONFIG

    preference_ids = ['avatar_universe', 'avatar_fuels', 'avatar_element']
    for qid in preference_ids:
        q = next(q for q in SURVEY_CONFIG['questions'] if q['id'] == qid)
        assert q.get('required', False) is False, f"{qid} should not be required"


def test_preference_questions_have_descriptions():
    """Verify preference questions have descriptions."""
    from app import SURVEY_CONFIG

    preference_ids = ['avatar_universe', 'avatar_fuels', 'avatar_element']
    for qid in preference_ids:
        q = next(q for q in SURVEY_CONFIG['questions'] if q['id'] == qid)
        assert 'description' in q, f"{qid} should have a description"
        assert len(q['description']) > 0, f"{qid} description should not be empty"


def test_avatar_universe_valid_values():
    """Verify avatar_universe has the correct option values."""
    from app import SURVEY_CONFIG

    q = next(q for q in SURVEY_CONFIG['questions'] if q['id'] == 'avatar_universe')
    values = [opt['value'] for opt in q['options']]

    expected = ['scifi', 'fantasy', 'cyberpunk', 'retro', 'nature',
                'steampunk', 'cosmic', 'postapoc', 'noir', 'underwater']
    assert values == expected


def test_avatar_fuels_valid_values():
    """Verify avatar_fuels has the correct option values."""
    from app import SURVEY_CONFIG

    q = next(q for q in SURVEY_CONFIG['questions'] if q['id'] == 'avatar_fuels')
    values = [opt['value'] for opt in q['options']]

    expected = ['gaming', 'music', 'sports', 'coffee', 'code',
                'movies', 'travel', 'art', 'fitness', 'books']
    assert values == expected


def test_avatar_element_valid_values():
    """Verify avatar_element has the correct option values."""
    from app import SURVEY_CONFIG

    q = next(q for q in SURVEY_CONFIG['questions'] if q['id'] == 'avatar_element')
    values = [opt['value'] for opt in q['options']]

    expected = ['fire', 'lightning', 'ice', 'earth', 'digital', 'shadow', 'cosmic', 'crystal']
    assert values == expected
