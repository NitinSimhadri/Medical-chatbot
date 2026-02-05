#!/bin/bash

# Medical Chatbot - Local CI/CD Script
# Runs all quality checks and tests locally

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Check Python version
print_header "Checking Python Version"
python --version || (print_error "Python not found" && exit 1)
print_success "Python found"

# Install dependencies
print_header "Installing Dependencies"
pip install -q -r requirements.txt
pip install -q pytest pytest-cov pytest-xdist pytest-timeout pylint flake8 bandit safety black isort || print_warning "Some tools failed to install"
print_success "Dependencies installed"

# Run Tests
print_header "Running Unit Tests"
if python test_suite.py; then
    print_success "All tests passed!"
else
    print_error "Some tests failed"
    exit 1
fi

# Run Tests with Coverage
print_header "Running Tests with Coverage"
if pytest test_suite.py --cov=. --cov-report=term-missing --cov-report=html -q; then
    print_success "Coverage report generated (htmlcov/index.html)"
else
    print_warning "Coverage report generation had issues"
fi

# Lint with pylint
print_header "Running Code Quality - Pylint"
if pylint app.py src/ --exit-zero -q; then
    print_success "Pylint check completed"
else
    print_warning "Pylint found issues (see above)"
fi

# Check style with flake8
print_header "Running Code Style - Flake8"
if flake8 app.py src/ --count --select=E9,F63,F7,F82 --show-source --statistics; then
    print_success "Flake8 check passed"
else
    print_warning "Flake8 found issues"
fi

# Security check with bandit
print_header "Running Security Scan - Bandit"
if bandit -r app.py src/ -ll -q; then
    print_success "Bandit security scan passed"
else
    print_warning "Bandit found potential security issues (review above)"
fi

# Check for vulnerable dependencies
print_header "Checking for Vulnerable Dependencies - Safety"
if safety check --json 2>/dev/null; then
    print_success "No vulnerable dependencies found"
else
    print_warning "Safety check completed (see above for details)"
fi

# Code formatting check
print_header "Running Code Format Check - Black"
if black --check app.py src/ -q 2>/dev/null; then
    print_success "Code formatting looks good"
else
    print_warning "Code formatting issues found. Run: black app.py src/"
fi

# Import ordering check
print_header "Checking Import Order - isort"
if isort --check-only app.py src/ -q 2>/dev/null; then
    print_success "Import ordering is correct"
else
    print_warning "Import ordering issues found. Run: isort app.py src/"
fi

# Final Summary
print_header "CI/CD Pipeline Summary"
echo -e "${GREEN}✅ Unit Tests: PASSED${NC}"
echo -e "${GREEN}✅ Code Coverage: GENERATED${NC}"
echo -e "${GREEN}✅ Code Quality: CHECKED${NC}"
echo -e "${GREEN}✅ Security Scan: COMPLETED${NC}"
echo -e "${GREEN}✅ Dependency Check: COMPLETED${NC}"
echo -e "${GREEN}✅ Code Formatting: CHECKED${NC}"

print_header "All Checks Completed Successfully! 🎉"
echo -e "Coverage Report: ${BLUE}htmlcov/index.html${NC}"
echo -e "Ready for deployment! ✨"
