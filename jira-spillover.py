import os
import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

# === CONFIG ===
BOARD_ID = 1  # Change to your JIRA board ID
PROJECT_KEY = "YOUR_PROJECT_KEY"  # e.g., "FINTECH"
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Accept": "application/json"}

# === Fetch all closed sprints ===
def get_sprints(board_id):
    url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{board_id}/sprint?state=closed"
    sprints = []
    start_at = 0
    while True:
        response = requests.get(f"{url}&startAt={start_at}", headers=HEADERS, auth=AUTH)
        data = response.json()
        sprints.extend(data.get("values", []))
        if data.get("isLast", True):
            break
        start_at += len(data.get("values", []))
    return sprints

# === Fetch issues for a sprint ===
def get_issues_for_sprint(sprint_id):
    url = f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{sprint_id}/issue"
    issues = []
    start_at = 0
    while True:
        response = requests.get(f"{url}?startAt={start_at}&maxResults=100", headers=HEADERS, auth=AUTH)
        data = response.json()
        issues.extend(data.get("issues", []))
        if data.get("isLast", True) or len(data.get("issues", [])) == 0:
            break
        start_at += len(data.get("issues", []))
    return issues

# === Determine spillover reason ===
def get_spillover_reason(issue, sprint_start, sprint_end):
    fields = issue["fields"]
    status = fields.get("status", {}).get("statusCategory", {}).get("name", "")
    created = pd.to_datetime(fields.get("created"), errors="coerce")
    updated = pd.to_datetime(fields.get("updated"), errors="coerce")
    story_points = fields.get("customfield_10016", 0)  # common SP field ID
    assignee = fields.get("assignee", {}).get("displayName", "Unassigned")

    if status.lower() == "done":
        return None

    # Heuristics for reason
    if created > pd.to_datetime(sprint_start):
        return "Scope added mid-sprint"
    elif story_points and story_points >= 8:
        return "Underestimated effort"
    elif updated > pd.to_datetime(sprint_end):
        return "Carried over work post-sprint"
    elif assignee == "Unassigned":
        return "No assignee during sprint"
    else:
        return "General delay / blocked"

# === MAIN LOGIC ===
def analyze_spillovers():
    sprints = get_sprints(BOARD_ID)
    records = []

    print(f"🔍 Found {len(sprints)} closed sprints")

    for sprint in sprints:
        sprint_id = sprint["id"]
        sprint_name = sprint["name"]
        sprint_start = sprint.get("startDate")
        sprint_end = sprint.get("endDate")

        if not sprint_start or not sprint_end:
            continue

        issues = get_issues_for_sprint(sprint_id)
        print(f"📅 Sprint: {sprint_name} — Issues: {len(issues)}")

        for issue in issues:
            fields = issue["fields"]
            assignee = fields.get("assignee", {}).get("displayName", "Unassigned")
            status = fields.get("status", {}).get("statusCategory", {}).get("name", "")
            story_points = fields.get("customfield_10016", 0)
            reason = get_spillover_reason(issue, sprint_start, sprint_end)

            records.append({
                "Sprint": sprint_name,
                "Assignee": assignee,
                "Issue Key": issue["key"],
                "Summary": fields.get("summary", ""),
                "Status": status,
                "Story Points": story_points,
                "Spillover Reason": reason
            })

    df = pd.DataFrame(records)
    df_spilled = df[df["Spillover Reason"].notna()]

    # === Summaries ===
    summary = (
        df_spilled.groupby(["Assignee", "Spillover Reason"])
        .agg({"Issue Key": "count", "Story Points": "sum"})
        .reset_index()
        .rename(columns={"Issue Key": "Spilled Issues"})
    )

    print("\n=== Spillover Summary ===")
    print(summary)

    # === Visualization ===
    pivot = summary.pivot(index="Assignee", columns="Spillover Reason", values="Spilled Issues").fillna(0)
    pivot.plot(kind="bar", stacked=True, figsize=(12, 6))
    plt.title("Spillover Reasons by Assignee")
    plt.xlabel("Assignee")
    plt.ylabel("Number of Spilled Issues")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.show()

    df_spilled.to_csv("jira_spillover_detailed.csv", index=False)
    summary.to_csv("jira_spillover_summary.csv", index=False)
    print("\n✅ Saved: jira_spillover_detailed.csv & jira_spillover_summary.csv")

# === RUN ===
if __name__ == "__main__":
    analyze_spillovers()