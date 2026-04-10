import subprocess
import tempfile
import os
import sys

BANNED = ['import os', 'import sys', 'import subprocess',
          'import shutil', '__import__', 'open(',
          'exec(', 'eval(', 'compile(']

def run_code(language, source_code, stdin=""):
    for banned in BANNED:
        if banned in source_code:
            return {"error": f"Security Error: '{banned}' is not allowed."}

    if language != "python":
        return {"error": "Only Python supported"}

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as f:
            f.write(source_code.encode())
            file_name = f.name

        print("RUNNING FILE:", file_name)
        print("INPUT:", stdin)

        result = subprocess.run(
            [sys.executable, file_name],
            input=stdin,
            text=True,
            capture_output=True,
            timeout=5
        )

        print("DEBUG STDOUT:", result.stdout)
        print("DEBUG STDERR:", result.stderr)

        os.remove(file_name)

        if result.stdout.strip():
            return {"stdout": result.stdout.strip()}

        if result.stderr.strip():
            return {"stderr": result.stderr.strip()}

        return {"stdout": "No Output"}

    except subprocess.TimeoutExpired:
        return {"error": "Time Limit Exceeded (5s)"}
    except Exception as e:
        return {"error": str(e)}
