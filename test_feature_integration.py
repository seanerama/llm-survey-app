"""Stage 4 Feature Integration Tests

Tests for email coordination, combined email sending, and task coordination.
"""
import unittest
from unittest.mock import Mock, patch, MagicMock


class TestCheckAndSendEmail(unittest.TestCase):
    """Tests for check_and_send_email coordination logic."""

    def test_waits_when_avatar_pending(self):
        """Should not send email when avatar is still pending."""
        from app import check_and_send_email

        with patch('app.get_db') as mock_db:
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            # Avatar pending, no plan
            mock_cursor.fetchone.side_effect = [
                {'id': '123', 'status': 'pending', 'image_data': None},
                None
            ]

            with patch('app.send_combined_email') as mock_send:
                check_and_send_email(1, 'test@example.com')
                mock_send.assert_not_called()

    def test_waits_when_plan_pending(self):
        """Should not send email when plan is still pending."""
        from app import check_and_send_email

        with patch('app.get_db') as mock_db:
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            # No avatar, plan pending
            mock_cursor.fetchone.side_effect = [
                None,
                {'id': '456', 'status': 'pending', 'plan_content': None}
            ]

            with patch('app.send_combined_email') as mock_send:
                check_and_send_email(1, 'test@example.com')
                mock_send.assert_not_called()

    def test_waits_when_both_pending(self):
        """Should not send email when both avatar and plan are pending."""
        from app import check_and_send_email

        with patch('app.get_db') as mock_db:
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            # Both pending
            mock_cursor.fetchone.side_effect = [
                {'id': '123', 'status': 'pending', 'image_data': None},
                {'id': '456', 'status': 'pending', 'plan_content': None}
            ]

            with patch('app.send_combined_email') as mock_send:
                check_and_send_email(1, 'test@example.com')
                mock_send.assert_not_called()

    def test_sends_when_avatar_completed_no_plan(self):
        """Should send email when avatar completes and no plan exists."""
        from app import check_and_send_email

        with patch('app.get_db') as mock_db:
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            # Avatar completed, no plan
            mock_cursor.fetchone.side_effect = [
                {'id': '123', 'status': 'completed', 'image_data': 'base64...'},
                None
            ]

            with patch('app.send_combined_email') as mock_send:
                check_and_send_email(1, 'test@example.com')
                mock_send.assert_called_once_with('test@example.com', '123', None)

    def test_sends_when_plan_completed_no_avatar(self):
        """Should send email when plan completes and no avatar exists."""
        from app import check_and_send_email

        with patch('app.get_db') as mock_db:
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            # No avatar, plan completed
            mock_cursor.fetchone.side_effect = [
                None,
                {'id': '456', 'status': 'completed', 'plan_content': '<h3>Plan</h3>'}
            ]

            with patch('app.send_combined_email') as mock_send:
                check_and_send_email(1, 'test@example.com')
                mock_send.assert_called_once_with('test@example.com', None, '<h3>Plan</h3>')

    def test_sends_when_both_completed(self):
        """Should send combined email when both avatar and plan complete."""
        from app import check_and_send_email

        with patch('app.get_db') as mock_db:
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            # Both completed
            mock_cursor.fetchone.side_effect = [
                {'id': '123', 'status': 'completed', 'image_data': 'base64...'},
                {'id': '456', 'status': 'completed', 'plan_content': '<h3>Plan</h3>'}
            ]

            with patch('app.send_combined_email') as mock_send:
                check_and_send_email(1, 'test@example.com')
                mock_send.assert_called_once_with('test@example.com', '123', '<h3>Plan</h3>')

    def test_sends_when_avatar_failed_plan_completed(self):
        """Should send plan-only email when avatar fails but plan succeeds."""
        from app import check_and_send_email

        with patch('app.get_db') as mock_db:
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            # Avatar failed, plan completed
            mock_cursor.fetchone.side_effect = [
                {'id': '123', 'status': 'failed', 'image_data': None},
                {'id': '456', 'status': 'completed', 'plan_content': '<h3>Plan</h3>'}
            ]

            with patch('app.send_combined_email') as mock_send:
                check_and_send_email(1, 'test@example.com')
                mock_send.assert_called_once_with('test@example.com', None, '<h3>Plan</h3>')

    def test_no_email_when_both_failed(self):
        """Should not send email when both avatar and plan fail."""
        from app import check_and_send_email

        with patch('app.get_db') as mock_db:
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            # Both failed
            mock_cursor.fetchone.side_effect = [
                {'id': '123', 'status': 'failed', 'image_data': None},
                {'id': '456', 'status': 'failed', 'plan_content': None}
            ]

            with patch('app.send_combined_email') as mock_send:
                check_and_send_email(1, 'test@example.com')
                mock_send.assert_not_called()


class TestSendCombinedEmail(unittest.TestCase):
    """Tests for send_combined_email function."""

    def test_skips_when_no_resend_key(self):
        """Should skip email when RESEND_API_KEY not set."""
        from app import send_combined_email

        with patch('app.RESEND_API_KEY', None):
            with patch('app.resend') as mock_resend:
                send_combined_email('test@example.com', '123', '<h3>Plan</h3>')
                mock_resend.Emails.send.assert_not_called()

    def test_avatar_only_subject(self):
        """Should use avatar-only subject when no plan content."""
        from app import send_combined_email

        with patch('app.RESEND_API_KEY', 'test-key'):
            with patch('app.resend') as mock_resend:
                send_combined_email('test@example.com', '123', None)
                call_args = mock_resend.Emails.send.call_args[0][0]
                self.assertEqual(call_args['subject'], 'Your Vibe Coding Wizard Avatar is Ready!')

    def test_plan_only_subject(self):
        """Should use plan-only subject when no avatar."""
        from app import send_combined_email

        with patch('app.RESEND_API_KEY', 'test-key'):
            with patch('app.resend') as mock_resend:
                send_combined_email('test@example.com', None, '<h3>Plan</h3>')
                call_args = mock_resend.Emails.send.call_args[0][0]
                self.assertEqual(call_args['subject'], 'Your Vibe Coding Kickstart Plan is Ready!')

    def test_combined_subject(self):
        """Should use combined subject when both avatar and plan."""
        from app import send_combined_email

        with patch('app.RESEND_API_KEY', 'test-key'):
            with patch('app.resend') as mock_resend:
                send_combined_email('test@example.com', '123', '<h3>Plan</h3>')
                call_args = mock_resend.Emails.send.call_args[0][0]
                self.assertEqual(call_args['subject'], 'Your Wizard Avatar & Vibe Coding Plan are Ready!')

    def test_includes_avatar_link(self):
        """Should include avatar link in email when avatar_id provided."""
        from app import send_combined_email

        with patch('app.RESEND_API_KEY', 'test-key'):
            with patch('app.APP_URL', 'https://test.example.com'):
                with patch('app.resend') as mock_resend:
                    send_combined_email('test@example.com', 'abc-123', None)
                    call_args = mock_resend.Emails.send.call_args[0][0]
                    self.assertIn('https://test.example.com/avatar/abc-123', call_args['html'])

    def test_includes_plan_content(self):
        """Should include plan content in email when provided."""
        from app import send_combined_email

        with patch('app.RESEND_API_KEY', 'test-key'):
            with patch('app.resend') as mock_resend:
                send_combined_email('test@example.com', None, '<h3>My Custom Plan</h3>')
                call_args = mock_resend.Emails.send.call_args[0][0]
                self.assertIn('<h3>My Custom Plan</h3>', call_args['html'])


class TestPreferenceExtraction(unittest.TestCase):
    """Tests for preference extraction in submit route."""

    def test_extracts_valid_preferences(self):
        """Should extract preferences when all fields present."""
        # This tests the logic that would be in submit()
        responses = {
            'avatar_universe': 'cyberpunk',
            'avatar_fuels': ['gaming', 'code', 'coffee'],
            'avatar_element': 'lightning'
        }

        preferences = None
        if (responses.get('avatar_universe') and
            responses.get('avatar_fuels') and len(responses.get('avatar_fuels', [])) == 3 and
            responses.get('avatar_element')):
            preferences = {
                'avatar_universe': responses['avatar_universe'],
                'avatar_fuels': responses['avatar_fuels'],
                'avatar_element': responses['avatar_element']
            }

        self.assertIsNotNone(preferences)
        self.assertEqual(preferences['avatar_universe'], 'cyberpunk')
        self.assertEqual(preferences['avatar_fuels'], ['gaming', 'code', 'coffee'])
        self.assertEqual(preferences['avatar_element'], 'lightning')

    def test_no_preferences_when_missing_universe(self):
        """Should not extract preferences when universe missing."""
        responses = {
            'avatar_fuels': ['gaming', 'code', 'coffee'],
            'avatar_element': 'lightning'
        }

        preferences = None
        if (responses.get('avatar_universe') and
            responses.get('avatar_fuels') and len(responses.get('avatar_fuels', [])) == 3 and
            responses.get('avatar_element')):
            preferences = {
                'avatar_universe': responses['avatar_universe'],
                'avatar_fuels': responses['avatar_fuels'],
                'avatar_element': responses['avatar_element']
            }

        self.assertIsNone(preferences)

    def test_no_preferences_when_wrong_fuels_count(self):
        """Should not extract preferences when fuels count is wrong."""
        responses = {
            'avatar_universe': 'cyberpunk',
            'avatar_fuels': ['gaming', 'code'],  # Only 2, need 3
            'avatar_element': 'lightning'
        }

        preferences = None
        if (responses.get('avatar_universe') and
            responses.get('avatar_fuels') and len(responses.get('avatar_fuels', [])) == 3 and
            responses.get('avatar_element')):
            preferences = {
                'avatar_universe': responses['avatar_universe'],
                'avatar_fuels': responses['avatar_fuels'],
                'avatar_element': responses['avatar_element']
            }

        self.assertIsNone(preferences)


class TestGeneratePlanAsync(unittest.TestCase):
    """Tests for generate_plan_async function."""

    def test_updates_db_on_success(self):
        """Should update database with completed status on success."""
        from app import generate_plan_async

        with patch('app.generate_vibe_plan') as mock_gen:
            mock_gen.return_value = ('<h3>Plan</h3>', True)

            with patch('app.get_db') as mock_db:
                mock_cursor = MagicMock()
                mock_conn = MagicMock()
                mock_conn.cursor.return_value = mock_cursor
                mock_db.return_value = mock_conn

                with patch('app.check_and_send_email'):
                    generate_plan_async('plan-123', 'test@example.com', 'My app idea', 1)

                # Verify the UPDATE was called with completed status
                update_call = mock_cursor.execute.call_args_list[0]
                self.assertIn('completed', update_call[0][0])

    def test_updates_db_on_failure(self):
        """Should update database with failed status on failure."""
        from app import generate_plan_async

        with patch('app.generate_vibe_plan') as mock_gen:
            mock_gen.return_value = ('Error message', False)

            with patch('app.get_db') as mock_db:
                mock_cursor = MagicMock()
                mock_conn = MagicMock()
                mock_conn.cursor.return_value = mock_cursor
                mock_db.return_value = mock_conn

                with patch('app.check_and_send_email'):
                    generate_plan_async('plan-123', 'test@example.com', 'My app idea', 1)

                # Verify the UPDATE was called with failed status
                update_call = mock_cursor.execute.call_args_list[0]
                self.assertIn('failed', update_call[0][0])

    def test_calls_check_and_send_email(self):
        """Should call check_and_send_email after completion."""
        from app import generate_plan_async

        with patch('app.generate_vibe_plan') as mock_gen:
            mock_gen.return_value = ('<h3>Plan</h3>', True)

            with patch('app.get_db') as mock_db:
                mock_cursor = MagicMock()
                mock_conn = MagicMock()
                mock_conn.cursor.return_value = mock_cursor
                mock_db.return_value = mock_conn

                with patch('app.check_and_send_email') as mock_check:
                    generate_plan_async('plan-123', 'test@example.com', 'My app idea', 1)
                    mock_check.assert_called_once_with(1, 'test@example.com')


if __name__ == '__main__':
    unittest.main()
