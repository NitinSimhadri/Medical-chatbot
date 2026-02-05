"""
Pytest Configuration and Fixtures for Medical Chatbot Tests
"""

import pytest
import os
import sys
import json
from io import BytesIO
from PIL import Image

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, get_user_id


@pytest.fixture(scope="session")
def test_app():
    """Create test app instance"""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    return app


@pytest.fixture
def client(test_app):
    """Create test client"""
    return test_app.test_client()


@pytest.fixture
def authenticated_client(client):
    """Create authenticated test client"""
    with client:
        response = client.post('/authenticate',
            data=json.dumps({
                'email': 'demo@medicare.com',
                'password': 'demo123'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        assert json.loads(response.data).get('success')
    return client


@pytest.fixture
def test_image():
    """Create a test image in memory"""
    img = Image.new('RGB', (100, 100), color='red')
    img_io = BytesIO()
    img.save(img_io, format='PNG')
    img_io.seek(0)
    return img_io


@pytest.fixture
def test_image_jpg():
    """Create a test JPEG image in memory"""
    img = Image.new('RGB', (100, 100), color='blue')
    img_io = BytesIO()
    img.save(img_io, format='JPEG')
    img_io.seek(0)
    return img_io


@pytest.fixture
def test_image_large():
    """Create a large test image (>5MB would exceed limit)"""
    img = Image.new('RGB', (5000, 5000), color='green')
    img_io = BytesIO()
    img.save(img_io, format='PNG')
    img_io.seek(0)
    return img_io


@pytest.fixture
def invalid_image_data():
    """Create invalid image data"""
    return BytesIO(b'not an image file')


@pytest.fixture
def temp_dir():
    """Create and cleanup temp directory"""
    temp_path = 'temp'
    if not os.path.exists(temp_path):
        os.makedirs(temp_path)
    yield temp_path
    # Cleanup is handled by app, but ensure directory exists
    if not os.path.exists(temp_path):
        os.makedirs(temp_path)


@pytest.fixture
def sample_messages():
    """Sample messages for testing"""
    return {
        'greeting': 'hello',
        'medical': 'I have a headache and fever',
        'appointment': 'I want to book an appointment',
        'hospital': 'find hospitals near me',
        'bmi': 'calculate my bmi',
        'empty': '   ',
        'long': 'A' * 1000,
    }


@pytest.fixture
def sample_locations():
    """Sample locations for hospital search"""
    return {
        'delhi': {
            'pincode': '110001',
            'name': 'Delhi',
            'keyword': 'delhi'
        },
        'mumbai': {
            'pincode': '400001',
            'name': 'Mumbai',
            'keyword': 'mumbai'
        },
        'bangalore': {
            'pincode': '560001',
            'name': 'Bangalore',
            'keyword': 'bangalore'
        },
        'noida': {
            'pincode': '201301',
            'name': 'Noida',
            'keyword': 'noida'
        },
        'pune': {
            'pincode': '411001',
            'name': 'Pune',
            'keyword': 'pune'
        },
        'bhubaneswar': {
            'pincode': '765022',
            'name': 'Bhubaneswar',
            'keyword': 'bhubaneswar'
        }
    }


@pytest.fixture
def user_id():
    """Get test user ID"""
    return get_user_id()


# Markers for categorizing tests
def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers", "unit: unit tests"
    )
    config.addinivalue_line(
        "markers", "integration: integration tests"
    )
    config.addinivalue_line(
        "markers", "smoke: smoke tests (quick sanity checks)"
    )
    config.addinivalue_line(
        "markers", "slow: slow running tests"
    )
    config.addinivalue_line(
        "markers", "auth: authentication tests"
    )
    config.addinivalue_line(
        "markers", "chat: chat functionality tests"
    )
    config.addinivalue_line(
        "markers", "image: image analysis tests"
    )
    config.addinivalue_line(
        "markers", "hospital: hospital search tests"
    )


# Hook for test reporting
def pytest_collection_modifyitems(config, items):
    """Modify test items after collection"""
    for item in items:
        # Auto-mark tests based on class name
        if "Auth" in item.nodeid:
            item.add_marker(pytest.mark.auth)
        if "Chat" in item.nodeid:
            item.add_marker(pytest.mark.chat)
        if "Image" in item.nodeid:
            item.add_marker(pytest.mark.image)
        if "Hospital" in item.nodeid:
            item.add_marker(pytest.mark.hospital)
        
        # Mark all as unit tests by default
        item.add_marker(pytest.mark.unit)


# Pytest hooks for better error reporting
def pytest_runtest_logreport(report):
    """Hook for test result reporting"""
    if report.when == "call":
        if report.outcome == "passed":
            print(f"\n✅ {report.nodeid.split('::')[-1]} PASSED")
        elif report.outcome == "failed":
            print(f"\n❌ {report.nodeid.split('::')[-1]} FAILED")
        elif report.outcome == "skipped":
            print(f"\n⏭️ {report.nodeid.split('::')[-1]} SKIPPED")


# Session-scoped setup and teardown
@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment before all tests"""
    print("\n" + "="*70)
    print("🧪 MEDICAL CHATBOT TEST SUITE - STARTING")
    print("="*70)
    
    # Ensure temp directory exists
    if not os.path.exists('temp'):
        os.makedirs('temp')
    
    yield
    
    print("\n" + "="*70)
    print("✅ TEST SUITE COMPLETED")
    print("="*70)


# Utility assertion helpers
class Assertions:
    """Custom assertions for tests"""
    
    @staticmethod
    def assert_json_response(response, has_keys=None):
        """Assert response is valid JSON with required keys"""
        try:
            data = json.loads(response.data)
        except json.JSONDecodeError:
            raise AssertionError(f"Response is not valid JSON: {response.data}")
        
        if has_keys:
            for key in has_keys:
                if key not in data:
                    raise AssertionError(f"Missing key '{key}' in response: {data}")
        
        return data
    
    @staticmethod
    def assert_file_exists(filepath):
        """Assert file exists"""
        if not os.path.exists(filepath):
            raise AssertionError(f"File does not exist: {filepath}")
    
    @staticmethod
    def assert_temp_files_cleaned(before_count, after_count):
        """Assert temp files were cleaned up"""
        if after_count > before_count:
            raise AssertionError(
                f"Temp files not cleaned up. Before: {before_count}, After: {after_count}"
            )


@pytest.fixture
def assertions():
    """Provide custom assertions"""
    return Assertions


# Helper for creating test data
class TestDataFactory:
    """Factory for creating test data"""
    
    @staticmethod
    def create_image(size=(100, 100), color='red', format='PNG'):
        """Create test image"""
        img = Image.new('RGB', size, color=color)
        img_io = BytesIO()
        img.save(img_io, format=format)
        img_io.seek(0)
        return img_io
    
    @staticmethod
    def create_hospital(name="Test Hospital", address="Test Address"):
        """Create test hospital data"""
        return {
            'name': name,
            'address': address,
            'phone': '1234567890',
            'rating': 4.5,
            'distance': '5 km away',
            'specialties': ['General', 'Cardiology']
        }
    
    @staticmethod
    def create_user_data(email="test@test.com", password="password123"):
        """Create test user data"""
        return {
            'email': email,
            'password': password
        }


@pytest.fixture
def factory():
    """Provide test data factory"""
    return TestDataFactory
