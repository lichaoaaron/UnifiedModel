---
name: osd-query-workbench
description: >-
  Execute PPL queries on OpenSearch Dashboards Query Workbench.
  Use this skill when the user wants to query OpenSearch data using PPL (Piped Processing Language),
  analyze log data, explore indices, or perform ad-hoc analysis.
  The user already has the Query Workbench page open in their browser at localhost:13124.
  This skill switches to PPL mode if needed, writes the PPL query, executes it,
  and reads the results — without closing the user's tab.
---

# OSD Query Workbench Skill

This skill executes PPL queries on the user's already-open OpenSearch Dashboards Query Workbench page.

## Prerequisites

- User has OpenSearch Dashboards Query Workbench open at `http://localhost:13124/app/opensearch-query-workbench`
- User is already logged in and on the Query Workbench page
- The CDP proxy from web-access skill must be available

## Workflow

Always load the web-access skill first for browser automation. Follow these steps:

### 1. Find the Target Tab

DO NOT create a new tab or navigate. The user already has the Query Workbench page open.
Find it by listing targets and matching the URL:

```bash
curl -s http://localhost:3456/targets
```

Identify the target whose URL contains `opensearch-query-workbench`. Use that `targetId` for all subsequent operations.

### 2. Switch to PPL Mode (if needed)

Check whether PPL mode is active. The page has a button group with `data-test-subj="switch-button"` containing two radio buttons: SQL and PPL.

If the element with `data-test-subj="switch-button-ppl"` is not already selected (check for `euiButtonGroupButton-isSelected` or `euiButtonGroupButton--fill` class), click it:

```bash
curl -s -X POST http://localhost:3456/click?target=TARGET_ID \
  -d '[data-test-subj="switch-button-ppl"]'
```

### 3. Write the PPL Query

The Query Workbench uses Ace Editor. Set the editor content via its API:

```js
var editor = document.querySelector(".ace_editor").env.editor;
editor.session.setValue("YOUR_PPL_QUERY_HERE");
```

Common PPL patterns:
- `source = <index-pattern> | stats count()` — total document count
- `source = <index-pattern> | stats count() by <field>` — grouped count
- `describe <index-name>` — show index schema
- `source = <index-pattern> | where <condition> | stats count()` — filtered count

### 4. Execute the Query

In PPL mode, the Run button has `data-test-subj="pplRunButton"`:

```bash
curl -s -X POST http://localhost:3456/click?target=TARGET_ID \
  -d '[data-test-subj="pplRunButton"]'
```

### 5. Read Results

Wait 5-8 seconds for query execution. Read results from the page:

```js
var t = document.querySelector(".application").innerText;
var idx = t.indexOf("Full screen view");
t.substring(idx, idx + 2000);
```

The results table appears under "Full screen view" / "Output" section.

For paginated results, click page buttons to navigate:

```js
var btn = Array.from(document.querySelectorAll("button"))
  .find(b => b.innerText.trim() === "{PAGE_NUMBER}");
btn.click();
```

### 6. DO NOT Close the Tab

Leave the user's tab open after completing the task.

## Important Notes

- **DO NOT** create new tabs or close the user's tab
- The target ID changes when a tab is navigated/reloaded — list targets at the start of each session
- In PPL mode, the Run button's `data-test-subj` is `pplRunButton` (NOT `sqlRunButton`)
- Use the Ace Editor API (`editor.session.setValue()`) to set query text
- PPL supports `*` wildcard in the `source` clause for index patterns
- `DESCRIBE` results are often paginated — navigate through all pages for the full schema
