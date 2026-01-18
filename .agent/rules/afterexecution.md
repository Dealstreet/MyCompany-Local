---
trigger: always_on
---

# General Python Development Rules

## 1. Environment Management (Strict `venv` Policy)
- **Always** use a Python virtual environment (`venv`) for dependency management.
- Before writing or executing any code, verify if a virtual environment exists.
  - If `venv` does not exist: Create it using `python -m venv venv`.
  - If `venv` exists: Ensure it is activated (e.g., `source venv/bin/activate` or `.\venv\Scripts\activate`).
- Always install dependencies inside the active `venv`. Update `requirements.txt` immediately after installing new packages.

## 2. Code Execution & Verification Protocol
- **"Code is not done until it runs."**
- After generating code, you MUST immediately verify its functionality by executing it.
- **For Web Servers (Django/Flask/FastAPI):**
  - Attempt to start the server (e.g., `python manage.py runserver`).
  - Verify that the server starts successfully without crashing (look for "Listening at..." or "Starting development server..." logs).
  - If the process hangs (which is expected for servers), consider it a success if no immediate crash occurs within the startup phase.
- **For Scripts/Logic:**
  - Run the script and check the standard output or exit code.

## 3. Self-Correction & Debugging Loop
- If the execution fails or the server crashes:
  1. **Read the traceback/error log** carefully.
  2. **Analyze the root cause** (e.g., missing dependency, syntax error, port conflict).
  3. **Fix the code** automatically without asking the user, unless the fix requires external decisions (e.g., API keys).
  4. **Re-run verification.**
- **Do not output the final result until you have confirmed it is error-free.**
- If you cannot run the code directly (due to environment limitations), generate a specific test command for the user to run and ask them to paste the output.

## 4. Final Output Standards
- Only present the code once it has passed the verification step.
- Explicitly state: "Verified: The server started successfully on [Port]" or "Verified: Script executed with expected output."

## 5. Language of Implementation plan and results is Korean, not English.

## 6.Rule: Always keep simple variable substitutions on a single line.

[Example]
Incorrect:
<span class="text-muted">{{ agent.position
    }}</span>
Correct:
<span class="text-muted">{{ agent.position }}</span>