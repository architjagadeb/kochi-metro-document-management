from unittest.mock import MagicMock, patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Department, User
from accounts.permissions import CONFIDENTIALITY_INTERNAL
from audit.models import AuditLog
from documents.ai_utils import ask_document, chunk_text, get_relevant_chunks
from documents.models import Document, DocumentVersion


class AIUtilsTest(TestCase):
    def test_chunk_text_empty_or_none(self):
        self.assertEqual(chunk_text(''), [])
        self.assertEqual(chunk_text(None), [])
        self.assertEqual(chunk_text('   \n\t  '), [])

    def test_chunk_text_small_document(self):
        text = 'Safety protocols for Kochi Metro station staff.'
        chunks = chunk_text(text, chunk_size=500)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_chunk_text_overlapping_chunks(self):
        # Create a 20-word string
        words = [f'word{i}' for i in range(20)]
        text = ' '.join(words)

        # Chunk size 10 -> overlap is min(50, 10//2) = 5, step = 5
        chunks = chunk_text(text, chunk_size=10)
        self.assertTrue(len(chunks) > 1)
        # First chunk should have first 10 words
        self.assertEqual(chunks[0], ' '.join(words[0:10]))
        # Second chunk should overlap by 5 words (starts at index 5)
        self.assertEqual(chunks[1], ' '.join(words[5:15]))
        # Third chunk starts at index 10
        self.assertEqual(chunks[2], ' '.join(words[10:20]))

    def test_keyword_match_ranking_above_non_match(self):
        chunk1 = 'Financial ledger report detailing quarterly expenditure on office supplies and catering services.'
        chunk2 = 'Emergency evacuation protocols for underground metro stations during flood or fire incidents.'
        chunk3 = 'General human resources guidelines on leave applications and annual holidays.'

        chunks = [chunk1, chunk2, chunk3]
        question = 'What is the procedure for emergency evacuation in stations?'

        relevant = get_relevant_chunks(question, chunks, top_n=2)
        self.assertEqual(len(relevant), 2)
        # chunk2 has "emergency", "evacuation", "stations" which are significant question keywords
        self.assertEqual(relevant[0], chunk2)

    def test_get_relevant_chunks_with_empty_or_no_text(self):
        # No extracted text resulting in empty chunk list
        empty_chunks = chunk_text('')
        result = get_relevant_chunks('Where is the metro depot?', empty_chunks, top_n=3)
        self.assertEqual(result, [])

        # None or empty question
        result2 = get_relevant_chunks('', ['Sample chunk content.'], top_n=3)
        self.assertEqual(result2, [])

    def test_stopwords_ignored_in_question(self):
        chunk_with_stopword = 'This document has the word the and is and what repeatedly.'
        chunk_with_keyword = 'The signaling interlock mechanism operates on automatic train protection.'

        chunks = [chunk_with_stopword, chunk_with_keyword]
        # "What is the" are all stopwords; "signaling" is the only significant keyword
        question = 'What is the signaling system?'

        relevant = get_relevant_chunks(question, chunks, top_n=1)
        self.assertEqual(relevant[0], chunk_with_keyword)

    def test_ask_document_no_extracted_text(self):
        dept = Department.objects.create(name='Operations')
        user = User.objects.create_user(username='op_user', password='password', role=User.ROLE_EMPLOYEE, department=dept)
        doc = Document.objects.create(title='Empty Text Doc', department=dept, uploaded_by=user)

        # No version at all
        result = ask_document(doc, 'What is this document about?')
        self.assertIn('No readable text is available for this document', result)

        # Version with empty text
        version = DocumentVersion.objects.create(
            document=doc,
            version_number=1,
            file=SimpleUploadedFile('test.pdf', b'%PDF-1.4 empty'),
            extracted_text='',
            uploaded_by=user
        )
        doc.current_version = version
        doc.save()

        result2 = ask_document(doc, 'What is this document about?')
        self.assertIn('No readable text is available for this document', result2)

    @patch('documents.ai_utils.Groq')
    def test_ask_document_groq_api_call(self, mock_groq_class):
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = 'The speed limit on the metro viaduct is 80 km/h.'
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion

        dept = Department.objects.create(name='Engineering')
        user = User.objects.create_user(username='eng_user', password='password', role=User.ROLE_EMPLOYEE, department=dept)
        doc = Document.objects.create(title='Speed Limits', department=dept, uploaded_by=user)
        version = DocumentVersion.objects.create(
            document=doc,
            version_number=1,
            file=SimpleUploadedFile('speed.pdf', b'%PDF-1.4 speed'),
            extracted_text='Maximum operating speed on the main track viaduct section is designated as 80 km/h.',
            uploaded_by=user
        )
        doc.current_version = version
        doc.save()

        answer = ask_document(doc, 'What is the speed limit on viaduct?')
        self.assertEqual(answer, 'The speed limit on the metro viaduct is 80 km/h.')

        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertEqual(call_kwargs['model'], 'openai/gpt-oss-120b')
        messages = call_kwargs['messages']
        self.assertEqual(messages[0]['role'], 'system')
        self.assertIn('document excerpts', messages[0]['content'].lower())
        self.assertEqual(messages[1]['role'], 'user')
        self.assertIn('What is the speed limit on viaduct?', messages[1]['content'])

    @patch('documents.ai_utils.Groq')
    def test_ask_document_api_error_graceful_handling(self, mock_groq_class):
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception('Groq rate limit exceeded or network down')

        dept = Department.objects.create(name='Safety')
        user = User.objects.create_user(username='safety_user', password='password', role=User.ROLE_EMPLOYEE, department=dept)
        doc = Document.objects.create(title='Safety Rules', department=dept, uploaded_by=user)
        version = DocumentVersion.objects.create(
            document=doc,
            version_number=1,
            file=SimpleUploadedFile('safety.pdf', b'%PDF-1.4 safety'),
            extracted_text='All track workers must wear fluorescent safety vests at all times.',
            uploaded_by=user
        )
        doc.current_version = version
        doc.save()

        answer = ask_document(doc, 'What must track workers wear?')
        self.assertTrue('Unable to process question' in answer or 'error' in answer.lower())


class DocumentDetailAIQueryIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name='Operations')
        self.user = User.objects.create_user(username='testuser', password='password123', role=User.ROLE_EMPLOYEE, department=self.dept)
        self.document = Document.objects.create(
            title='Operational Guidelines 2026',
            document_type=Document.DOC_TYPE_REPORT,
            department=self.dept,
            confidentiality=CONFIDENTIALITY_INTERNAL,
            uploaded_by=self.user,
        )
        self.version = DocumentVersion.objects.create(
            document=self.document,
            version_number=1,
            file=SimpleUploadedFile('ops.pdf', b'%PDF-1.4 ops content'),
            extracted_text='Morning train inspections begin at 04:30 AM at the Muttom maintenance depot.',
            text_found=True,
            uploaded_by=self.user,
            change_note='Initial version',
        )
        self.document.current_version = self.version
        self.document.save()

    @patch('documents.ai_utils.Groq')
    def test_document_detail_ask_question_post_and_audit_logging(self, mock_groq_class):
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = 'Morning train inspections start at 04:30 AM at Muttom depot.'
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion

        self.client.login(username='testuser', password='password123')
        url = reverse('document_detail', args=[self.document.id])

        question = 'What time do morning inspections begin?'
        response = self.client.post(url, {'ai_question': question})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, question)
        self.assertContains(response, 'Morning train inspections start at 04:30 AM at Muttom depot.')

        # Verify audit log was created
        audit_log = AuditLog.objects.filter(action='ai_query', document=self.document).first()
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.user, self.user)
        self.assertEqual(audit_log.action, 'ai_query')
        self.assertEqual(audit_log.details, question)
