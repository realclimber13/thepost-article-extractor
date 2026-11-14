import unittest
from unittest.mock import patch
import extract

class ExtractorTests(unittest.TestCase):
    def test_private_destinations_rejected(self):
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaises(ValueError):
                extract.public_url('https://example.com/story')
        for url in ('file:///etc/passwd', 'https://user:pass@example.com', 'http://example.com:8080'):
            with self.assertRaises(ValueError):
                extract.public_url(url)

    def test_article_text_extracted(self):
        paragraphs = ''.join('<p>' + ('A reporter verified the facts with public records and interviewed officials about the local project. ' * 8) + '</p>' for _ in range(5))
        with patch.object(extract, 'download', return_value=('<html><body><article><h1>Local project report</h1>' + paragraphs + '</article></body></html>', 'https://example.com/story')):
            result = extract.extract({'id': 'a', 'url': 'https://example.com/story'})
        self.assertGreater(len(result['content']), 600)

    def test_denied_page_keeps_fallback(self):
        with patch.object(extract, 'download', side_effect=ValueError('Denied')):
            result = extract.extract({'id': 'a', 'url': 'https://example.com/story'})
        self.assertNotIn('content', result)
        self.assertEqual(result['error'], 'ValueError')

if __name__ == '__main__':
    unittest.main()
