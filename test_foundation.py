"""Stage 1 Foundation Tests"""
import importlib


def test_anthropic_import():
    """Verify anthropic package is installed and importable."""
    anthropic = importlib.import_module('anthropic')
    assert anthropic is not None


def test_vibe_plans_table_schema():
    """Verify vibe_plans table is created by init_db."""
    # This test requires DATABASE_URL to be set
    import os
    if not os.environ.get('DATABASE_URL'):
        print("Skipping: DATABASE_URL not set")
        return

    from app import init_db, get_db

    init_db()
    conn = get_db()
    cur = conn.cursor()

    # Check table exists
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'vibe_plans'
        ORDER BY ordinal_position;
    """)
    columns = cur.fetchall()
    conn.close()

    column_names = [c[0] for c in columns]
    assert 'id' in column_names
    assert 'response_id' in column_names
    assert 'email' in column_names
    assert 'wishlist_input' in column_names
    assert 'plan_content' in column_names
    assert 'status' in column_names
    assert 'error_message' in column_names
    assert 'created_at' in column_names
    assert 'completed_at' in column_names
