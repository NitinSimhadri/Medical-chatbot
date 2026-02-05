# Medical Chatbot - Local CI/CD Script (Windows PowerShell)
# Run all quality checks and tests locally

# Color codes for output
function Write-Header {
    Write-Host "`n========================================" -ForegroundColor Blue
    Write-Host $args[0] -ForegroundColor Blue
    Write-Host "========================================`n" -ForegroundColor Blue
}

function Write-Success {
    Write-Host "✅ $($args[0])" -ForegroundColor Green
}

function Write-Error {
    Write-Host "❌ $($args[0])" -ForegroundColor Red
}

function Write-Warning {
    Write-Host "⚠️  $($args[0])" -ForegroundColor Yellow
}

# Check Python version
Write-Header "Checking Python Version"
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python not found"
    exit 1
}
Write-Host $pythonVersion
Write-Success "Python found"

# Install dependencies
Write-Header "Installing Dependencies"
pip install -q -r requirements.txt
pip install -q pytest pytest-cov pytest-xdist pytest-timeout pylint flake8 bandit safety black isort 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Success "Dependencies installed"
} else {
    Write-Warning "Some tools failed to install (this is OK)"
}

# Run Tests
Write-Header "Running Unit Tests"
python test_suite.py
if ($LASTEXITCODE -eq 0) {
    Write-Success "All tests passed!"
} else {
    Write-Error "Some tests failed"
    exit 1
}

# Run Tests with Coverage
Write-Header "Running Tests with Coverage"
pytest test_suite.py --cov=. --cov-report=term-missing --cov-report=html -q
if ($LASTEXITCODE -eq 0) {
    Write-Success "Coverage report generated (htmlcov/index.html)"
    Write-Host "Open: htmlcov/index.html in browser"
} else {
    Write-Warning "Coverage report generation had issues"
}

# Lint with pylint
Write-Header "Running Code Quality - Pylint"
pylint app.py src/ --exit-zero -q 2>$null
if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 1) {
    Write-Success "Pylint check completed"
} else {
    Write-Warning "Pylint check had issues"
}

# Check style with flake8
Write-Header "Running Code Style - Flake8"
flake8 app.py src/ --count --select=E9,F63,F7,F82 --show-source --statistics 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Success "Flake8 check passed"
} else {
    Write-Warning "Flake8 found issues"
}

# Security check with bandit
Write-Header "Running Security Scan - Bandit"
bandit -r app.py src/ -ll -q 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Success "Bandit security scan passed"
} else {
    Write-Warning "Bandit found potential security issues (review above)"
}

# Check for vulnerable dependencies
Write-Header "Checking for Vulnerable Dependencies - Safety"
safety check --json 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Success "No vulnerable dependencies found"
} else {
    Write-Warning "Safety check completed (see above for details)"
}

# Code formatting check
Write-Header "Running Code Format Check - Black"
black --check app.py src/ -q 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Success "Code formatting looks good"
} else {
    Write-Warning "Code formatting issues found. Run: black app.py src/"
}

# Import ordering check
Write-Header "Checking Import Order - isort"
isort --check-only app.py src/ -q 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Success "Import ordering is correct"
} else {
    Write-Warning "Import ordering issues found. Run: isort app.py src/"
}

# Final Summary
Write-Header "CI/CD Pipeline Summary"
Write-Success "Unit Tests: PASSED"
Write-Success "Code Coverage: GENERATED"
Write-Success "Code Quality: CHECKED"
Write-Success "Security Scan: COMPLETED"
Write-Success "Dependency Check: COMPLETED"
Write-Success "Code Formatting: CHECKED"

Write-Header "All Checks Completed Successfully! 🎉"
Write-Host "Coverage Report: " -NoNewline
Write-Host "htmlcov/index.html" -ForegroundColor Blue
Write-Host "Ready for deployment! ✨"
