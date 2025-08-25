import requests
import base64
from datetime import datetime, timedelta

# ---- Config ----
ADO_ORG = "<YOUR_AZURE_DEVOPS_ORGANIZATION>"  # e.g., "contoso"
ADO_PAT = "<YOUR_AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN>"

PORT_BASE_URL = "https://api.getport.io/v1"
PORT_CLIENT_ID = "<YOUR_PORT_CLIENT_ID>"
PORT_CLIENT_SECRET = "<YOUR_PORT_CLIENT_SECRET>"

# Blueprint IDs in Port
BP_BUILD = "azure_dev_ops_build"
BP_TEST_RUN = "azureTestRun"
BP_TEST_RESULT = "azureTestResult"
BP_COVERAGE = "azureCodeCoverage"
BP_REPOSITORY = "azureDevopsRepository"

# Port authentication - will be set dynamically
PORT_ACCESS_TOKEN = None

def ado_headers():
    token = f":{ADO_PAT}".encode("utf-8")
    b64 = base64.b64encode(token).decode("utf-8")
    return {"Authorization": f"Basic {b64}"}

def get_port_access_token():
    """Get a fresh access token from Port using client credentials"""
    global PORT_ACCESS_TOKEN
    
    print("🔐 Authenticating with Port...")
    auth_url = "https://api.getport.io/v1/auth/access_token"
    
    auth_data = {
        "clientId": PORT_CLIENT_ID,
        "clientSecret": PORT_CLIENT_SECRET
    }
    
    try:
        response = requests.post(auth_url, json=auth_data, timeout=30)
        response.raise_for_status()
        
        token_data = response.json()
        PORT_ACCESS_TOKEN = token_data.get("accessToken")
        
        if PORT_ACCESS_TOKEN:
            print("✅ Successfully authenticated with Port")
        else:
            print("❌ Failed to get access token from Port")
            return False
            
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error authenticating with Port: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected authentication error: {e}")
        return False

def port_headers():
    """Get headers for Port API requests"""
    if not PORT_ACCESS_TOKEN:
        return None
    return {
        "Authorization": f"Bearer {PORT_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

# ---- Port Helpers ----
def upsert_entity(blueprint: str, identifier: str, properties: dict, relations: dict = None):
    body = {
        "identifier": identifier,
        "properties": properties,
    }
    if relations:
        body["relations"] = relations

    headers = port_headers()
    if not headers:
        print(f"❌ Cannot upsert {blueprint}:{identifier} - no valid Port token")
        return None

    url = f"{PORT_BASE_URL}/blueprints/{blueprint}/entities?upsert=true"
    try:
        r = requests.post(url, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        print(f"✅ Upserted {blueprint}:{identifier}")
        return r.json()
    except Exception as e:
        print(f"❌ Failed to upsert {blueprint}:{identifier}: {e}")
        return None

# ---- Azure DevOps Fetchers ----
def get_all_projects():
    """Get all projects from the Azure DevOps organization"""
    url = f"https://dev.azure.com/{ADO_ORG}/_apis/projects?api-version=7.1-preview.4"
    try:
        r = requests.get(url, headers=ado_headers(), timeout=30)
        r.raise_for_status()
        data = r.json()
        projects = data.get("value", [])
        print(f"📁 Found {len(projects)} projects in organization '{ADO_ORG}'")
        return projects
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching projects: {e}")
        return []
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return []

def get_recent_builds(project_name, days=10):
    since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
    url = f"https://dev.azure.com/{ADO_ORG}/{project_name}/_apis/build/builds?api-version=7.1-preview.7&minTime={since}"
    try:
        r = requests.get(url, headers=ado_headers(), timeout=30)
        r.raise_for_status()
        data = r.json()
        builds = data.get("value", [])
        return builds
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching builds: {e}")
        return []
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return []

def get_test_runs(project_name, build_id):
    build_uri = f"vstfs:///Build/Build/{build_id}"
    url = f"https://dev.azure.com/{ADO_ORG}/{project_name}/_apis/test/runs?buildUri={build_uri}&api-version=7.0"
    try:
        r = requests.get(url, headers=ado_headers(), timeout=30)
        r.raise_for_status()
        data = r.json().get("value", [])
        if data:
            print(f"  ✅ Found {len(data)} test runs for build {build_id}")
        return data
    except requests.exceptions.HTTPError as e:
        if r.status_code == 404:
            print(f"  ⚠️  No test runs found for build {build_id}")
            return []
        else:
            print(f"  ❌ Error fetching test runs for build {build_id}: {e}")
            return []
    except Exception as e:
        print(f"  ❌ Unexpected error fetching test runs for build {build_id}: {e}")
        return []

def get_test_results(project_name, run_id):
    url = f"https://dev.azure.com/{ADO_ORG}/{project_name}/_apis/test/Runs/{run_id}/results?api-version=7.0"
    try:
        r = requests.get(url, headers=ado_headers(), timeout=30)
        r.raise_for_status()
        return r.json().get("value", [])
    except Exception as e:
        print(f"    ❌ Error fetching test results for run {run_id}: {e}")
        return []

def get_code_coverage(project_name, build_id):
    url = f"https://dev.azure.com/{ADO_ORG}/{project_name}/_apis/test/codecoverage?buildId={build_id}&api-version=7.0"
    try:
        r = requests.get(url, headers=ado_headers(), timeout=30)
        r.raise_for_status()
        
        response_data = r.json()
        
        # Azure DevOps uses "coverageData" key for the response
        coverage_data = response_data.get("coverageData", [])
        if not coverage_data:
            coverage_data = response_data.get("value", [])
            
        return coverage_data
    except Exception as e:
        print(f"  ❌ Error fetching code coverage for build {build_id}: {e}")
        return []

# ---- Main Sync ----
def list_port_blueprints():
    """List all blueprints in Port to find correct identifiers"""
    headers = port_headers()
    if not headers:
        print("❌ Cannot list blueprints - no valid Port token")
        return None

    url = f"{PORT_BASE_URL}/blueprints"
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        blueprints = r.json().get("blueprints", [])
        
        print(f"📋 Found {len(blueprints)} blueprints in Port:")
        for bp in blueprints:
            print(f"  - {bp.get('identifier')} ({bp.get('title')})")
        
        return blueprints
    except Exception as e:
        print(f"❌ Failed to list blueprints: {e}")
        return None

def main():
    print("🚀 Starting Azure DevOps sync...")
    
    # Authenticate with Port first
    if not get_port_access_token():
        print("❌ Failed to authenticate with Port. Exiting.")
        return
    
    # Get all projects from the organization
    projects = get_all_projects()
    if not projects:
        print("❌ No projects found - check your Azure DevOps organization configuration")
        return
    
    total_builds_processed = 0
    
    for project in projects:
        project_name = project.get("name")
        project_id = project.get("id")
        print(f"\n🏗️ Processing Project: {project_name} ({project_id})")
        
        builds = get_recent_builds(project_name, days=30)
        print(f"📊 Found {len(builds)} builds in project '{project_name}' (last 30 days)")
        
        if not builds:
            print(f"  ℹ️ No builds found in project '{project_name}'")
            continue
        
        total_builds_processed += len(builds)
        
        for b in builds:
            build_id = str(b["id"])
            print(f"\n🔹 Processing Build {build_id} (Project: {project_name})")

            # --- Create Build Entity First ---
            build_properties = {
                "message": b.get("definition", {}).get("name", ""),
                "build_id": int(build_id),
                "build_number": b.get("buildNumber", ""),
                "status": b.get("status", ""),
                "owning_repository": b.get("repository", {}).get("name", "") if b.get("repository") else ""
            }
            
            build_relations = {}
            # Add repository relation using Port repository identifiers (format: project/repo-name)
            if b.get("repository", {}).get("name"):
                repo_name = b["repository"]["name"]
                # Use the actual project name from Azure DevOps (lowercased to match Port format)
                project_name_lower = project_name.lower()
                # Construct Port repository identifier dynamically: {project}/{repo-name}
                port_repo_id = f"{project_name_lower}/{repo_name}"
                build_relations["repository"] = port_repo_id
                print(f"  🔗 Linking build to repository: {port_repo_id}")
            
            upsert_entity(BP_BUILD, build_id, build_properties, build_relations if build_relations else None)

            # --- Test Runs ---
            runs = get_test_runs(project_name, build_id)
            for run in runs:
                run_id = str(run["id"])
                run_entity_id = f"testrun-{run_id}"

                properties = {
                    "state": run.get("state"),
                    "totalTests": run.get("totalTests"),
                    "passedTests": run.get("passedTests"),
                    "failedTests": run.get("unanalyzedTests"),  # Azure API may use different keys
                    "startTime": run.get("startedDate"),
                    "completeTime": run.get("completedDate"),
                    "durationSec": run.get("runStatistics", [{}])[0].get("duration", 0)
                }
                relations = {"build": build_id}
                upsert_entity(BP_TEST_RUN, run_entity_id, properties, relations)

                # --- Test Results per Run ---
                results = get_test_results(project_name, run_id)
                for res in results:
                    res_id = str(res["id"])
                    result_entity_id = f"testresult-{run_id}-{res_id}"
                    properties = {
                        "testCaseTitle": res.get("testCaseTitle"),
                        "outcome": res.get("outcome"),
                        "durationMs": res.get("durationInMs"),
                        "owner": res.get("owner", {}).get("displayName"),
                        "automatedTestName": res.get("automatedTestName"),
                        "automatedTestType": res.get("automatedTestType"),
                        "errorMessage": res.get("errorMessage"),
                        "stackTrace": res.get("stackTrace")
                    }
                    relations = {"run": run_entity_id}
                    upsert_entity(BP_TEST_RESULT, result_entity_id, properties, relations)

            # --- Code Coverage ---
            coverages = get_code_coverage(project_name, build_id)
            if coverages:
                print(f"  ✅ Found {len(coverages)} code coverage report(s)")
                
            for cov in coverages:
                # Handle Azure DevOps coverage structure
                modules = cov.get("modules", [])
                if not modules and "coverageStats" in cov:
                    # Alternative structure for some coverage reports
                    modules = [{"name": "summary", "coverageData": cov.get("coverageStats", [])}]
                
                for module in modules:
                    coverage_data_list = module.get("coverageData", [])
                    
                    for cov_data in coverage_data_list:
                        # Use label instead of coverageType if available
                        coverage_type = cov_data.get("coverageType") or cov_data.get("label", "unknown")
                        module_name = module.get("name", "unknown")
                        
                        cov_entity_id = f"coverage-{build_id}-{coverage_type}-{module_name}".replace("/", "-").replace(" ", "-")
                        covered = cov_data.get("covered", 0)
                        total = cov_data.get("total", 0)
                        pct = (covered / total * 100) if total else 0

                        properties = {
                            "coverage_type": coverage_type,
                            "moduleName": module_name,
                            "covered": covered,
                            "total": total,
                            "percentage": pct,
                            "reportUrl": cov.get("url", "")
                        }
                        relations = {"build": build_id}
                        upsert_entity(BP_COVERAGE, cov_entity_id, properties, relations)
    
    print(f"\n🎉 Sync completed! Processed {total_builds_processed} builds across {len(projects)} projects.")

if __name__ == "__main__":
    main()
