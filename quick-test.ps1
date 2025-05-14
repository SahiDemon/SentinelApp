# Quick test script to verify OpenSearch connectivity
# Run this script to ensure logs are being correctly sent and retrieved

# Set the working directory to the script location
Set-Location $PSScriptRoot

# Activate the virtual environment
Write-Host "Activating Python virtual environment..." -ForegroundColor Green
& ".\.venv\Scripts\Activate.ps1"

# Set PYTHONPATH
$env:PYTHONPATH = "$PSScriptRoot;$PSScriptRoot\src\python"
Write-Host "Set PYTHONPATH to: $env:PYTHONPATH" -ForegroundColor Green

# Disable proxy settings
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:NO_PROXY = "localhost,127.0.0.1,search-sentinelprimeregistry-re5i27ttwnf44njaayopo6vouq.aos.us-east-1.on.aws"

# Set timeout parameters
$env:OPENSEARCH_TIMEOUT = "60"
$env:OPENSEARCH_RETRY = "3"

# Create a test Python script
$testScript = @"
import os
import sys
import time
import datetime
import json
from opensearchpy import OpenSearch, RequestsHttpConnection

print("OpenSearch Connection Test Script")
print("================================")
print(f"Python version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")
print(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}")

# OpenSearch connection parameters
host = 'search-sentinelprimeregistry-re5i27ttwnf44njaayopo6vouq.aos.us-east-1.on.aws' 
port = 443
auth = ('SahiDemon', 'Sahi@448866')
index_name = 'sentinel_raw_logs'

# Connection attempt
print("\nAttempting to connect to OpenSearch...")
try:
    client = OpenSearch(
        hosts=[{'host': host, 'port': port}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=False,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
        connection_class=RequestsHttpConnection,
        timeout=60,
        max_retries=3,
        retry_on_timeout=True
    )
    
    if client.ping():
        print("Successfully connected to OpenSearch!")
    else:
        print("Failed to ping the OpenSearch server.")
        sys.exit(1)
        
    # Check if index exists
    if client.indices.exists(index=index_name):
        print(f"Index '{index_name}' exists.")
    else:
        print(f"Index '{index_name}' doesn't exist.")
        sys.exit(1)
    
    # Create test log entry
    timestamp = datetime.datetime.now(datetime.timezone.utc)
    test_id = int(timestamp.timestamp())
    
    log_entry = {
        "timestamp": timestamp.isoformat(),
        "log_timestamp_ms": int(timestamp.timestamp() * 1000),
        "hostname": "test-script",
        "user_identifier": "test-user",
        "monitor_type": "test_script",
        "event_type": "connection_test",
        "pid": os.getpid(),
        "test_id": test_id,
        "event_details": {
            "message": "This is a test log entry from quick-test.ps1",
            "time": timestamp.isoformat()
        }
    }
    
    # Send the log
    print("\nSending test log...")
    result = client.index(
        index=index_name,
        body=log_entry,
        refresh=True  # Force immediate refresh
    )
    print(f"Log sent: {result['result']}")
    
    # Wait a moment
    print("Waiting 3 seconds for log to be indexed...")
    time.sleep(3)
    
    # Refresh the index to make sure the log is searchable
    client.indices.refresh(index=index_name)
    
    # Try to find the log we just sent
    print("\nSearching for the test log...")
    search_query = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"test_id": test_id}},
                    {"range": {"timestamp": {"gte": "now-1m", "lte": "now"}}}
                ]
            }
        }
    }
    
    result = client.search(
        body=search_query,
        index=index_name
    )
    
    total_hits = result['hits']['total']['value'] if 'hits' in result else 0
    print(f"Found {total_hits} matching logs")
    
    if total_hits > 0:
        print("SUCCESS! Test log was successfully sent and retrieved.")
        print("\nQuerying the last 5 minutes of logs...")
        
        # Query logs from last 5 minutes
        recent_query = {
            "query": {
                "range": {
                    "timestamp": {
                        "gte": "now-5m",
                        "lte": "now"
                    }
                }
            },
            "sort": [{"timestamp": {"order": "desc"}}],
            "size": 10
        }
        
        recent_results = client.search(
            body=recent_query,
            index=index_name
        )
        
        recent_hits = recent_results['hits']['total']['value'] if 'hits' in recent_results else 0
        print(f"Found {recent_hits} logs from the last 5 minutes")
        
        if recent_hits > 0:
            print("\nMost recent logs:")
            for hit in recent_results['hits']['hits'][:5]:
                source = hit['_source']
                print(f"- {source.get('timestamp', 'No time')} | {source.get('monitor_type', 'Unknown')} | {source.get('event_type', 'Unknown')}")
        else:
            print("No logs found from the last 5 minutes")
    else:
        print("ERROR: Test log was not found after sending!")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
"@

# Save the test script to a temporary file
$testScriptPath = Join-Path $PSScriptRoot "opensearch_test.py"
$testScript | Out-File -FilePath $testScriptPath -Encoding utf8

try {
    # Run the test script
    Write-Host "Running OpenSearch connection test..." -ForegroundColor Cyan
    python $testScriptPath
    
    # Check if script succeeded
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nTest completed successfully!" -ForegroundColor Green
    } else {
        Write-Host "`nTest failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    }
} finally {
    # Clean up test script
    if (Test-Path $testScriptPath) {
        Remove-Item $testScriptPath -Force
    }
}

Write-Host "`nPress any key to exit..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") 