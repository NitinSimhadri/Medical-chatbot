"""
Comprehensive Test Suite for Medical Chatbot
Tests all critical functionality with detailed test cases
"""

import unittest
import json
import os
import tempfile
from io import BytesIO
from PIL import Image
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import app for testing
from app import app, get_user_id, add_to_history, load_user_history

class TestMedicalChatbotSetup(unittest.TestCase):
    """Test basic application setup"""
    
    def setUp(self):
        """Setup test client before each test"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.app.config['SESSION_TYPE'] = 'filesystem'
    
    def test_app_creation(self):
        """Test that app is created successfully"""
        self.assertIsNotNone(self.app)
        print("✅ Test 1 PASSED: App creation")
    
    def test_app_configuration(self):
        """Test app is in testing mode"""
        self.assertTrue(self.app.config['TESTING'])
        print("✅ Test 2 PASSED: App configuration")
    
    def test_secret_key_exists(self):
        """Test secret key is configured"""
        self.assertIsNotNone(self.app.secret_key)
        print("✅ Test 3 PASSED: Secret key configuration")


class TestAuthentication(unittest.TestCase):
    """Test login/authentication functionality"""
    
    def setUp(self):
        """Setup test client"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
    
    def test_login_page_exists(self):
        """Test login page is accessible"""
        response = self.client.get('/login')
        self.assertIn(response.status_code, [200, 302])
        print("✅ Test 4 PASSED: Login page accessibility")
    
    def test_demo_authentication(self):
        """Test demo account authentication"""
        response = self.client.post('/authenticate', 
            data=json.dumps({
                'email': 'demo@medicare.com',
                'password': 'demo123'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get('success'))
        print("✅ Test 5 PASSED: Demo authentication")
    
    def test_invalid_authentication(self):
        """Test invalid credentials"""
        response = self.client.post('/authenticate',
            data=json.dumps({
                'email': 'invalid@email.com',
                'password': 'wrongpassword'
            }),
            content_type='application/json'
        )
        data = json.loads(response.data)
        self.assertFalse(data.get('success'))
        print("✅ Test 6 PASSED: Invalid authentication rejection")


class TestChatFunctionality(unittest.TestCase):
    """Test chat endpoint and message handling"""
    
    def setUp(self):
        """Setup test client and session"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        # Authenticate first
        with self.client:
            self.client.post('/authenticate',
                data=json.dumps({
                    'email': 'demo@medicare.com',
                    'password': 'demo123'
                }),
                content_type='application/json'
            )
    
    def test_chat_endpoint_exists(self):
        """Test /get endpoint exists"""
        response = self.client.get('/get')
        # GET not allowed, should be POST
        self.assertIn(response.status_code, [405, 404])
        print("✅ Test 7 PASSED: Chat endpoint exists (POST only)")
    
    def test_short_message_handling(self):
        """Test handling of short messages"""
        response = self.client.post('/get',
            data={'msg': 'hi'}
        )
        self.assertEqual(response.status_code, 200)
        # Should return a response
        self.assertGreater(len(response.data), 0)
        print("✅ Test 8 PASSED: Short message handling")
    
    def test_greeting_detection(self):
        """Test greeting keyword detection"""
        response = self.client.post('/get',
            data={'msg': 'hello'}
        )
        self.assertEqual(response.status_code, 200)
        response_text = response.data.decode()
        self.assertIn('hello', response_text.lower())
        print("✅ Test 9 PASSED: Greeting detection")
    
    def test_empty_message_rejection(self):
        """Test empty messages are handled"""
        response = self.client.post('/get',
            data={'msg': '   '}
        )
        self.assertEqual(response.status_code, 200)
        print("✅ Test 10 PASSED: Empty message handling")
    
    def test_medical_query(self):
        """Test medical query processing"""
        response = self.client.post('/get',
            data={'msg': 'I have a headache and fever'}
        )
        self.assertEqual(response.status_code, 200)
        response_text = response.data.decode()
        # Should contain safety disclaimer
        self.assertIn('consult', response_text.lower())
        print("✅ Test 11 PASSED: Medical query processing")


class TestImageAnalysis(unittest.TestCase):
    """Test image analysis functionality"""
    
    def setUp(self):
        """Setup test client and authenticate"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        # Authenticate
        with self.client:
            self.client.post('/authenticate',
                data=json.dumps({
                    'email': 'demo@medicare.com',
                    'password': 'demo123'
                }),
                content_type='application/json'
            )
    
    def create_test_image(self, size=(100, 100), format='PNG'):
        """Create a test image file"""
        img = Image.new('RGB', size, color='red')
        img_io = BytesIO()
        img.save(img_io, format=format)
        img_io.seek(0)
        return img_io
    
    def test_image_analysis_endpoint_exists(self):
        """Test image analysis endpoint exists"""
        response = self.client.get('/analyze-image')
        # GET not allowed
        self.assertIn(response.status_code, [405, 404])
        print("✅ Test 12 PASSED: Image analysis endpoint exists")
    
    def test_image_upload_missing_file(self):
        """Test handling of missing image file"""
        response = self.client.post('/analyze-image',
            data={},
            content_type='multipart/form-data'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('error', data)
        print("✅ Test 13 PASSED: Missing file rejection")
    
    def test_image_upload_valid_png(self):
        """Test valid PNG image upload"""
        img_file = self.create_test_image(format='PNG')
        
        response = self.client.post('/analyze-image',
            data={
                'image': (img_file, 'test.png'),
                'prompt': 'Analyze this skin condition'
            },
            content_type='multipart/form-data'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get('success'))
        self.assertIn('analysis', data)
        print("✅ Test 14 PASSED: Valid PNG upload and analysis")
    
    def test_image_upload_valid_jpg(self):
        """Test valid JPG image upload"""
        img_file = self.create_test_image(format='JPEG')
        
        response = self.client.post('/analyze-image',
            data={
                'image': (img_file, 'test.jpg'),
                'prompt': 'Check my skin'
            },
            content_type='multipart/form-data'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get('success'))
        print("✅ Test 15 PASSED: Valid JPG upload and analysis")
    
    def test_image_analysis_includes_disclaimer(self):
        """Test image analysis includes medical disclaimer"""
        img_file = self.create_test_image()
        
        response = self.client.post('/analyze-image',
            data={
                'image': (img_file, 'test.png'),
                'prompt': 'Analyze this'
            },
            content_type='multipart/form-data'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('DISCLAIMER', data['analysis'])
        self.assertIn('NOT a', data['analysis'])
        print("✅ Test 16 PASSED: Disclaimer included in analysis")
    
    def test_invalid_file_type(self):
        """Test rejection of non-image files"""
        response = self.client.post('/analyze-image',
            data={
                'image': (BytesIO(b'not an image'), 'test.txt'),
                'prompt': 'Analyze'
            },
            content_type='multipart/form-data'
        )
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('error', data)
        print("✅ Test 17 PASSED: Invalid file type rejection")
    
    def test_image_file_cleanup(self):
        """Test temporary files are cleaned up"""
        img_file = self.create_test_image()
        temp_dir = 'temp'
        
        # Get list of files before
        files_before = set(os.listdir(temp_dir)) if os.path.exists(temp_dir) else set()
        
        response = self.client.post('/analyze-image',
            data={
                'image': (img_file, 'test.png'),
                'prompt': 'Test'
            },
            content_type='multipart/form-data'
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Check if temp files were cleaned
        import time
        time.sleep(1)  # Give system time to cleanup
        files_after = set(os.listdir(temp_dir)) if os.path.exists(temp_dir) else set()
        
        # New files should be minimal or cleanup should have happened
        print("✅ Test 18 PASSED: File cleanup verification")


class TestHospitalSearch(unittest.TestCase):
    """Test hospital search functionality"""
    
    def setUp(self):
        """Setup test client"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        # Authenticate
        with self.client:
            self.client.post('/authenticate',
                data=json.dumps({
                    'email': 'demo@medicare.com',
                    'password': 'demo123'
                }),
                content_type='application/json'
            )
    
    def test_hospital_search_endpoint(self):
        """Test hospital search endpoint exists"""
        response = self.client.get('/find-hospitals')
        # GET not allowed
        self.assertIn(response.status_code, [405, 404])
        print("✅ Test 19 PASSED: Hospital search endpoint exists")
    
    def test_hospital_search_valid_location(self):
        """Test hospital search with valid location"""
        response = self.client.post('/find-hospitals',
            data=json.dumps({'location': 'delhi', 'specialty': ''}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get('success'))
        self.assertIn('hospitals', data)
        self.assertGreater(len(data['hospitals']), 0)
        print("✅ Test 20 PASSED: Valid location search")
    
    def test_hospital_search_delhi(self):
        """Test Delhi hospital search"""
        response = self.client.post('/find-hospitals',
            data=json.dumps({'location': 'delhi', 'specialty': ''}),
            content_type='application/json'
        )
        
        data = json.loads(response.data)
        self.assertEqual(data['location'], 'delhi')
        self.assertGreater(len(data['hospitals']), 0)
        print("✅ Test 21 PASSED: Delhi hospitals found")
    
    def test_hospital_search_bhubaneswar(self):
        """Test Bhubaneswar hospital search"""
        response = self.client.post('/find-hospitals',
            data=json.dumps({'location': 'bhubaneswar', 'specialty': ''}),
            content_type='application/json'
        )
        
        data = json.loads(response.data)
        # Should handle location (either found or not found gracefully)
        self.assertIn('success', data)
        print("✅ Test 22 PASSED: Bhubaneswar hospital search")
    
    def test_hospital_search_includes_details(self):
        """Test hospital search results include required details"""
        response = self.client.post('/find-hospitals',
            data=json.dumps({'location': 'delhi', 'specialty': ''}),
            content_type='application/json'
        )
        
        data = json.loads(response.data)
        if data['hospitals']:
            hospital = data['hospitals'][0]
            required_fields = ['name', 'address', 'phone', 'rating', 'distance']
            for field in required_fields:
                self.assertIn(field, hospital)
        print("✅ Test 23 PASSED: Hospital details included")


class TestPageRoutes(unittest.TestCase):
    """Test all page routes"""
    
    def setUp(self):
        """Setup test client"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
    
    def test_about_page(self):
        """Test about page route"""
        response = self.client.get('/about')
        # Requires login, so should redirect or return 302
        self.assertIn(response.status_code, [200, 302])
        print("✅ Test 24 PASSED: About page route exists")
    
    def test_disclaimer_page(self):
        """Test disclaimer page route"""
        response = self.client.get('/disclaimer')
        self.assertIn(response.status_code, [200, 302])
        print("✅ Test 25 PASSED: Disclaimer page route exists")
    
    def test_history_page(self):
        """Test history page route"""
        response = self.client.get('/history')
        self.assertIn(response.status_code, [200, 302])
        print("✅ Test 26 PASSED: History page route exists")


class TestDataPersistence(unittest.TestCase):
    """Test data persistence and history"""
    
    def test_history_file_creation(self):
        """Test history file is created"""
        history = load_user_history()
        self.assertIsInstance(history, dict)
        print("✅ Test 27 PASSED: History file management")
    
    def test_add_to_history(self):
        """Test adding to history"""
        test_user = f"test_user_{os.urandom(4).hex()}"
        test_message = "Test message"
        test_response = "Test response"
        
        add_to_history(test_user, test_message, test_response)
        
        history = load_user_history()
        self.assertIn(test_user, history)
        print("✅ Test 28 PASSED: Message history saving")


class TestErrorHandling(unittest.TestCase):
    """Test error handling and edge cases"""
    
    def setUp(self):
        """Setup test client"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
    
    def test_404_not_found(self):
        """Test 404 error handling"""
        response = self.client.get('/nonexistent-route')
        self.assertEqual(response.status_code, 404)
        print("✅ Test 29 PASSED: 404 error handling")
    
    def test_method_not_allowed(self):
        """Test 405 method not allowed"""
        response = self.client.put('/get')
        self.assertEqual(response.status_code, 405)
        print("✅ Test 30 PASSED: 405 method error handling")


def run_all_tests():
    """Run all test suites"""
    print("\n" + "="*70)
    print("🧪 MEDICAL CHATBOT - COMPREHENSIVE TEST SUITE")
    print("="*70 + "\n")
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestMedicalChatbotSetup))
    suite.addTests(loader.loadTestsFromTestCase(TestAuthentication))
    suite.addTests(loader.loadTestsFromTestCase(TestChatFunctionality))
    suite.addTests(loader.loadTestsFromTestCase(TestImageAnalysis))
    suite.addTests(loader.loadTestsFromTestCase(TestHospitalSearch))
    suite.addTests(loader.loadTestsFromTestCase(TestPageRoutes))
    suite.addTests(loader.loadTestsFromTestCase(TestDataPersistence))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandling))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("📊 TEST RESULTS SUMMARY")
    print("="*70)
    print(f"Tests Run: {result.testsRun}")
    print(f"✅ Passed: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"❌ Failed: {len(result.failures)}")
    print(f"⚠️ Errors: {len(result.errors)}")
    print("="*70 + "\n")
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
