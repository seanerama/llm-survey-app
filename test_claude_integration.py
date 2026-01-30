"""Stage 3 Claude Integration Tests"""
import unittest
from unittest.mock import Mock, patch


class TestGenerateAvatarPrompt(unittest.TestCase):

    def test_valid_inputs_returns_prompt(self):
        """Valid inputs should return a non-empty prompt string."""
        from app import generate_avatar_prompt, FALLBACK_AVATAR_PROMPT

        # Mock the Claude client
        with patch('app.get_claude_client') as mock_get_client:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.content = [Mock(text="A detailed prompt for a cyberpunk wizard with neon lighting and electric effects...")]
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = generate_avatar_prompt(
                universe='cyberpunk',
                fuels=['gaming', 'code', 'coffee'],
                element='lightning'
            )

            assert isinstance(result, str)
            assert len(result) > 50
            assert result != FALLBACK_AVATAR_PROMPT

    def test_invalid_universe_returns_fallback(self):
        """Invalid universe should return fallback prompt."""
        from app import generate_avatar_prompt, FALLBACK_AVATAR_PROMPT

        with patch('app.get_claude_client') as mock_get_client:
            mock_get_client.return_value = Mock()

            result = generate_avatar_prompt(
                universe='invalid_universe',
                fuels=['gaming', 'code', 'coffee'],
                element='lightning'
            )

            assert result == FALLBACK_AVATAR_PROMPT

    def test_invalid_fuels_count_returns_fallback(self):
        """Wrong number of fuels should return fallback prompt."""
        from app import generate_avatar_prompt, FALLBACK_AVATAR_PROMPT

        with patch('app.get_claude_client') as mock_get_client:
            mock_get_client.return_value = Mock()

            result = generate_avatar_prompt(
                universe='cyberpunk',
                fuels=['gaming', 'code'],  # Only 2, need 3
                element='lightning'
            )

            assert result == FALLBACK_AVATAR_PROMPT

    def test_invalid_element_returns_fallback(self):
        """Invalid element should return fallback prompt."""
        from app import generate_avatar_prompt, FALLBACK_AVATAR_PROMPT

        with patch('app.get_claude_client') as mock_get_client:
            mock_get_client.return_value = Mock()

            result = generate_avatar_prompt(
                universe='cyberpunk',
                fuels=['gaming', 'code', 'coffee'],
                element='invalid_element'
            )

            assert result == FALLBACK_AVATAR_PROMPT

    def test_no_client_returns_fallback(self):
        """No Claude client should return fallback prompt."""
        from app import generate_avatar_prompt, FALLBACK_AVATAR_PROMPT

        with patch('app.get_claude_client') as mock_get_client:
            mock_get_client.return_value = None

            result = generate_avatar_prompt(
                universe='cyberpunk',
                fuels=['gaming', 'code', 'coffee'],
                element='lightning'
            )

            assert result == FALLBACK_AVATAR_PROMPT

    def test_api_error_returns_fallback(self):
        """API error should return fallback prompt."""
        import anthropic
        from app import generate_avatar_prompt, FALLBACK_AVATAR_PROMPT

        with patch('app.get_claude_client') as mock_get_client:
            mock_client = Mock()
            mock_client.messages.create.side_effect = anthropic.APIError(
                message="Test error",
                request=Mock(),
                body=None
            )
            mock_get_client.return_value = mock_client

            result = generate_avatar_prompt(
                universe='cyberpunk',
                fuels=['gaming', 'code', 'coffee'],
                element='lightning'
            )

            assert result == FALLBACK_AVATAR_PROMPT

    def test_api_timeout_returns_fallback(self):
        """API timeout should return fallback prompt."""
        import anthropic
        from app import generate_avatar_prompt, FALLBACK_AVATAR_PROMPT

        with patch('app.get_claude_client') as mock_get_client:
            mock_client = Mock()
            mock_client.messages.create.side_effect = anthropic.APITimeoutError(
                request=Mock()
            )
            mock_get_client.return_value = mock_client

            result = generate_avatar_prompt(
                universe='cyberpunk',
                fuels=['gaming', 'code', 'coffee'],
                element='lightning'
            )

            assert result == FALLBACK_AVATAR_PROMPT

    def test_short_response_returns_fallback(self):
        """Too short response should return fallback prompt."""
        from app import generate_avatar_prompt, FALLBACK_AVATAR_PROMPT

        with patch('app.get_claude_client') as mock_get_client:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.content = [Mock(text="Too short")]  # Less than 50 chars
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = generate_avatar_prompt(
                universe='cyberpunk',
                fuels=['gaming', 'code', 'coffee'],
                element='lightning'
            )

            assert result == FALLBACK_AVATAR_PROMPT


class TestGenerateVibePlan(unittest.TestCase):

    def test_valid_input_returns_plan(self):
        """Valid input should return (plan, True)."""
        from app import generate_vibe_plan

        with patch('app.get_claude_client') as mock_get_client:
            mock_client = Mock()
            mock_response = Mock()
            # Response must be > 200 chars and contain <h3> tags
            mock_response.content = [Mock(text="""<h3>The Vision</h3>
<p>Your expense automation project is totally achievable with modern AI tools. You want to eliminate the tedious manual process of creating expense reports.</p>
<h3>Suggested Tech Stack</h3>
<ul>
<li><strong>Python:</strong> Great for automation scripts</li>
<li><strong>Flask:</strong> Simple web framework</li>
</ul>
<h3>Core Features</h3>
<ol>
<li>Receipt scanning</li>
<li>Automatic categorization</li>
</ol>""")]
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            content, success = generate_vibe_plan("automate my expense reports")

            assert success is True
            assert '<h3>' in content
            assert len(content) > 100

    def test_empty_input_returns_error(self):
        """Empty input should return (error, False)."""
        from app import generate_vibe_plan, VIBE_PLAN_ERROR_MESSAGE

        content, success = generate_vibe_plan("")

        assert success is False
        assert content == VIBE_PLAN_ERROR_MESSAGE

    def test_whitespace_input_returns_error(self):
        """Whitespace-only input should return (error, False)."""
        from app import generate_vibe_plan, VIBE_PLAN_ERROR_MESSAGE

        content, success = generate_vibe_plan("   ")

        assert success is False
        assert content == VIBE_PLAN_ERROR_MESSAGE

    def test_none_input_returns_error(self):
        """None input should return (error, False)."""
        from app import generate_vibe_plan, VIBE_PLAN_ERROR_MESSAGE

        content, success = generate_vibe_plan(None)

        assert success is False
        assert content == VIBE_PLAN_ERROR_MESSAGE

    def test_no_client_returns_error(self):
        """No Claude client should return (error, False)."""
        from app import generate_vibe_plan, VIBE_PLAN_ERROR_MESSAGE

        with patch('app.get_claude_client') as mock_get_client:
            mock_get_client.return_value = None

            content, success = generate_vibe_plan("build an app")

            assert success is False
            assert content == VIBE_PLAN_ERROR_MESSAGE

    def test_api_error_returns_error(self):
        """API error should return (error, False)."""
        import anthropic
        from app import generate_vibe_plan, VIBE_PLAN_ERROR_MESSAGE

        with patch('app.get_claude_client') as mock_get_client:
            mock_client = Mock()
            mock_client.messages.create.side_effect = anthropic.APIError(
                message="Test error",
                request=Mock(),
                body=None
            )
            mock_get_client.return_value = mock_client

            content, success = generate_vibe_plan("build an app")

            assert success is False
            assert content == VIBE_PLAN_ERROR_MESSAGE

    def test_api_timeout_returns_error(self):
        """API timeout should return (error, False)."""
        import anthropic
        from app import generate_vibe_plan, VIBE_PLAN_ERROR_MESSAGE

        with patch('app.get_claude_client') as mock_get_client:
            mock_client = Mock()
            mock_client.messages.create.side_effect = anthropic.APITimeoutError(
                request=Mock()
            )
            mock_get_client.return_value = mock_client

            content, success = generate_vibe_plan("build an app")

            assert success is False
            assert content == VIBE_PLAN_ERROR_MESSAGE

    def test_invalid_response_returns_error(self):
        """Response without proper HTML should return (error, False)."""
        from app import generate_vibe_plan, VIBE_PLAN_ERROR_MESSAGE

        with patch('app.get_claude_client') as mock_get_client:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.content = [Mock(text="Just a plain text response without h3 tags")]
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            content, success = generate_vibe_plan("build an app")

            assert success is False
            assert content == VIBE_PLAN_ERROR_MESSAGE


class TestClaudeClientInitialization(unittest.TestCase):

    def test_client_created_with_api_key(self):
        """Client should be created when API key exists."""
        import app

        # Reset the global client
        app._claude_client = None

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('app.anthropic.Anthropic') as mock_anthropic:
                mock_anthropic.return_value = Mock()
                client = app.get_claude_client()

                mock_anthropic.assert_called_once_with(api_key='test-key')
                assert client is not None

        # Reset again for other tests
        app._claude_client = None

    def test_client_none_without_api_key(self):
        """Client should be None when no API key."""
        import app

        # Reset the global client
        app._claude_client = None

        with patch.dict('os.environ', {}, clear=True):
            # Remove ANTHROPIC_API_KEY if it exists
            import os
            os.environ.pop('ANTHROPIC_API_KEY', None)

            client = app.get_claude_client()
            assert client is None

        # Reset for other tests
        app._claude_client = None


if __name__ == '__main__':
    unittest.main()
