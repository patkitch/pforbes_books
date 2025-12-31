#!/usr/bin/env python3
"""
Setup and Environment Check Script for Forbes Lawn Accounting
Verifies that all prerequisites are met before running sync
"""

import os
import sys


def check_python_version():
    """Check Python version"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8+ required")
        print(f"   Current version: {version.major}.{version.minor}.{version.micro}")
        return False
    print(f"✓ Python version: {version.major}.{version.minor}.{version.micro}")
    return True


def check_dependencies():
    """Check if required packages are installed"""
    print("\nChecking dependencies...")
    
    try:
        import requests
        print(f"✓ requests library installed (version {requests.__version__})")
        return True
    except ImportError:
        print("❌ requests library not installed")
        print("   Install with: pip install requests --break-system-packages")
        return False


def check_environment_variables():
    """Check if API keys are set"""
    print("\nChecking environment variables...")
    
    issues = []
    
    jobber_key = os.environ.get("JOBBER_API_KEY")
    if not jobber_key:
        print("❌ JOBBER_API_KEY not set")
        issues.append("JOBBER_API_KEY")
    else:
        masked = jobber_key[:10] + "..." + jobber_key[-4:] if len(jobber_key) > 14 else "***"
        print(f"✓ JOBBER_API_KEY set: {masked}")
    
    ledgerlink_key = os.environ.get("LEDGERLINK_API_KEY")
    if not ledgerlink_key:
        print("❌ LEDGERLINK_API_KEY not set")
        issues.append("LEDGERLINK_API_KEY")
    else:
        masked = ledgerlink_key[:10] + "..." + ledgerlink_key[-4:] if len(ledgerlink_key) > 14 else "***"
        print(f"✓ LEDGERLINK_API_KEY set: {masked}")
    
    if issues:
        print("\n⚠️  Missing environment variables:")
        for var in issues:
            print(f"\n   Set {var}:")
            print(f'   export {var}="your-api-key-here"')
        return False
    
    return True


def check_api_connectivity():
    """Test API connectivity"""
    print("\nChecking API connectivity...")
    
    jobber_key = os.environ.get("JOBBER_API_KEY")
    ledgerlink_key = os.environ.get("LEDGERLINK_API_KEY")
    
    if not jobber_key or not ledgerlink_key:
        print("⊘ Skipping connectivity check (missing API keys)")
        return True  # Don't fail setup if keys aren't set yet
    
    import requests
    
    # Test Jobber API
    try:
        headers = {
            "Authorization": f"Bearer {jobber_key}",
            "Content-Type": "application/json",
            "X-JOBBER-GRAPHQL-VERSION": "2025-04-16"
        }
        query = """
        query { 
          viewer { 
            account { 
              name 
            } 
          } 
        }
        """
        response = requests.post(
            "https://api.getjobber.com/api/graphql",
            json={"query": query},
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if "data" in data and "viewer" in data["data"]:
                account_name = data["data"]["viewer"]["account"]["name"]
                print(f"✓ Jobber API connected: {account_name}")
            else:
                print("⚠️  Jobber API returned unexpected response")
                print(f"   Response: {data}")
        elif response.status_code == 401:
            print("❌ Jobber API authentication failed")
            print("   Your API token may be expired. Get a fresh token from:")
            print("   https://developer.getjobber.com/")
            return False
        else:
            print(f"⚠️  Jobber API returned status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to Jobber API: {str(e)}")
        return False
    
    # Test LedgerLink API
    try:
        headers = {
            "Authorization": f"Bearer {ledgerlink_key}",
            "Content-Type": "application/json"
        }
        query = """
        query { 
          viewer { 
            email 
          } 
        }
        """
        response = requests.post(
            "https://api.ledgerlink.io/graphql",
            json={"query": query},
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if "data" in data and "viewer" in data["data"]:
                email = data["data"]["viewer"]["email"]
                print(f"✓ LedgerLink API connected: {email}")
            else:
                print("⚠️  LedgerLink API returned unexpected response")
        elif response.status_code == 401:
            print("❌ LedgerLink API authentication failed")
            print("   Check your API token")
            return False
        else:
            print(f"⚠️  LedgerLink API returned status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to LedgerLink API: {str(e)}")
        return False
    
    return True


def check_files():
    """Check if sync service files exist"""
    print("\nChecking service files...")
    
    required_files = [
        "forbes_lawn_accounting/services/service_items_sync_service.py",
        "forbes_lawn_accounting/services/invoice_sync_service.py",
        "forbes_lawn_accounting/services/payment_sync_service.py",
        "forbes_lawn_accounting/management/commands/sync_all.py",
        "forbes_lawn_accounting/management/commands/sync_invoices.py",
        "forbes_lawn_accounting/management/commands/sync_payments.py",
        "forbes_lawn_accounting/management/commands/sync_service_items.py"
    ]
    
    missing = []
    for file in required_files:
        if os.path.exists(file):
            # Show just the filename for cleaner output
            filename = file.split('/')[-1]
            print(f"✓ {filename}")
        else:
            print(f"❌ {file} not found")
            missing.append(file)
    
    if missing:
        print("\n⚠️  Missing required files.")
        print("Make sure you've placed the service files in forbes_lawn_accounting/services/")
        print("and the command files in forbes_lawn_accounting/management/commands/")
        return False
    
    return True


def print_next_steps(all_checks_passed):
    """Print next steps based on check results"""
    print("\n" + "="*70)
    
    if all_checks_passed:
        print("✅ ALL CHECKS PASSED - Ready to sync!")
        print("="*70)
        print("\nNext steps:")
        print("  1. Set your API keys:")
        print('     $env:JOBBER_API_KEY = "your-jobber-key"')
        print('     $env:LEDGERLINK_API_KEY = "your-ledgerlink-key"')
        print("  2. Test with dry run:")
        print("     python manage.py sync_all --start-date 2024-01-01 --dry-run")
        print("  3. Run live sync:")
        print("     python manage.py sync_all --start-date 2024-01-01")
    else:
        print("❌ SOME CHECKS FAILED - Please fix issues above")
        print("="*70)
        print("\nCommon fixes:")
        print("  • Set API keys (PowerShell):")
        print('    $env:JOBBER_API_KEY = "your-key"')
        print('    $env:LEDGERLINK_API_KEY = "your-key"')
        print("  • Refresh expired Jobber token at: https://developer.getjobber.com/")
        print("  • Make sure service files are in forbes_lawn_accounting/services/")
        print("  • Make sure command files are in forbes_lawn_accounting/management/commands/")


def main():
    """Run all checks"""
    print("="*70)
    print("FORBES LAWN ACCOUNTING - Environment Check")
    print("="*70)
    
    checks = []
    
    # Run all checks
    checks.append(("Python version", check_python_version()))
    checks.append(("Dependencies", check_dependencies()))
    checks.append(("Environment variables", check_environment_variables()))
    checks.append(("Service files", check_files()))
    checks.append(("API connectivity", check_api_connectivity()))
    
    # Print results
    all_passed = all(result for _, result in checks)
    print_next_steps(all_passed)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())