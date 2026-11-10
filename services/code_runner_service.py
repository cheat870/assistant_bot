import sys
import time
import subprocess
import tempfile
import logging
import asyncio
from typing import Dict, Any, Optional
from services.ai_service import _call_gemini_api, format_gemini_error
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# Dangerous system commands to block in sandbox
BLOCKED_PATTERNS = [
    "shutil.rmtree",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.system",
    "format c:",
    "rm -rf",
    "del /f",
    "subprocess.popen",
    "os.kill",
    "ctypes",
    "winreg",
]

def execute_python_code_sandboxed(code: str, timeout_seconds: float = 5.0) -> Dict[str, Any]:
    """
    Safely executes Python code in an isolated subprocess with timeout and output limits.
    Returns stdout, stderr, execution time, and exit code.
    """
    code_clean = code.strip()
    if not code_clean:
        return {
            "success": False,
            "stdout": "",
            "stderr": "❌ មិនមានកូដសម្រាប់ដំណើរការឡើយ!",
            "elapsed": 0.0,
            "exit_code": 1
        }

    # Security check against destructive system calls
    code_lower = code_clean.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern in code_lower:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"🛡️ សុវត្ថិភាពខ្ពស់៖ កូដនេះត្រូវបានទប់ស្កាត់ដោយសារមានពាក្យគន្លឹះប្រព័ន្ធគ្រោះថ្នាក់ ('{pattern}')!",
                "elapsed": 0.0,
                "exit_code": 403
            }

    start_time = time.perf_counter()
    temp_dir = tempfile.gettempdir()

    try:
        proc = subprocess.run(
            [sys.executable, "-c", code_clean],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=temp_dir
        )
        elapsed = round(time.perf_counter() - start_time, 3)

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        # Limit output length to prevent Telegram message overflows (3,000 chars max)
        if len(stdout) > 2800:
            stdout = stdout[:2800] + "\n... [⚠️ ទិន្នន័យ Output វែងពេក ត្រូវបានកាត់ត្រឹមនេះ]"
        if len(stderr) > 2800:
            stderr = stderr[:2800] + "\n... [⚠️ ព័ត៌មាន Error វែងពេក]"

        return {
            "success": proc.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "elapsed": elapsed,
            "exit_code": proc.returncode
        }
    except subprocess.TimeoutExpired:
        elapsed = round(time.perf_counter() - start_time, 2)
        return {
            "success": False,
            "stdout": "",
            "stderr": f"⏱️ កូដដំណើរការលើសកំណត់ (Timeout > {timeout_seconds}s)!\n💡 សូមប្រយ័ត្នកុំបង្កើត infinite loop (while True) ណា៎!",
            "elapsed": elapsed,
            "exit_code": 124
        }
    except Exception as e:
        elapsed = round(time.perf_counter() - start_time, 3)
        return {
            "success": False,
            "stdout": "",
            "stderr": f"❌ កំហុសដំណើរការប្រព័ន្ធ Sandbox៖ {str(e)[:200]}",
            "elapsed": elapsed,
            "exit_code": 1
        }

def format_execution_result(result: Dict[str, Any], code: str) -> str:
    """Format clean, informative Telegram markdown message for code execution output."""
    code_preview = code.strip()
    if len(code_preview) > 300:
        code_preview = code_preview[:300] + "\n# ... [កូដនៅសល់]"

    py_ver = f"Python {sys.version_info.major}.{sys.version_info.minor}"
    status_emoji = "✅ ជោគជ័យ (Success)" if result["success"] else "❌ មានបញ្ហា (Failed)"

    msg = (
        f"💻 *លទ្ធផលដំណើរការកូដ ({py_ver} Sandbox)* ⚡\n\n"
        f"📝 *កូដដែលបានដំណើរការ៖*\n"
        f"```python\n{code_preview}\n```\n\n"
    )

    if result["stdout"]:
        msg += f"📤 *លទ្ធផលចេញ (Output)៖*\n```text\n{result['stdout']}\n```\n\n"
    elif result["success"] and not result["stderr"]:
        msg += "📤 *លទ្ធផលចេញ (Output)៖*\n`[ដំណើរការជោគជ័យ ដោយគ្មាន output print អ្វីចេញមក]`\n\n"

    if result["stderr"]:
        msg += f"⚠️ *ព័ត៌មានកំហុស (Error / Traceback)៖*\n```text\n{result['stderr']}\n```\n\n"

    msg += (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ *រយៈពេលដំណើរការ:* `{result['elapsed']}s` | ស្ថានភាព៖ *{status_emoji}*\n"
    )

    if not result["success"]:
        msg += "💡 _លោកអ្នកអាចចុចប៊ូតុង **'🐞 Debug ជាមួយ AI'** ខាងក្រោម ដើម្បីឱ្យ AI កែកូដឱ្យត្រឹមត្រូវភ្លាមៗ!_"

    return msg

CODE_DEBUGGER_PROMPT = (
    "You are a World-Class Principal Software Engineer, Senior Code Reviewer, and Programming Mentor. "
    "A developer sent you code that has a bug, threw an error, or needs optimization. "
    "\n\nProvide an authoritative, polite, and practical debugging response in Khmer:\n"
    "💻 **របាយការណ៍ជួសជុលកូដ (AI Code Debugger)**\n"
    "• ភាសា & ប្រភេទកំហុស៖ (Language detected, e.g. Python, JS, PHP, SQL and Error type)\n"
    "• មូលហេតុនៃ Error៖ (Clear explanation in Khmer of why the error happened)\n"
    "• កូដដែលបានកែសម្រួលរួចរាល់៖ (Provide the complete, corrected, drop-in replacement code in proper markdown ```language code block)\n"
    "• គន្លឹះបង្កើនល្បឿន & សុវត្ថិភាព (Best Practice Tip)៖ (One concise, high-value engineering recommendation)\n"
)

async def debug_and_explain_code(code: str, language: str = "auto", error_msg: str = "") -> str:
    """Debug and optimize programming code across Python, JS, PHP, SQL, HTML, etc."""
    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return (
            "💻 *AI Code Debugger:*\n\n"
            "⚠️ មុខងារ AI Code Debugger ត្រូវការកំណត់ GEMINI_API_KEY ជាមុនសិន។"
        )

    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = (
        f"{CODE_DEBUGGER_PROMPT}\n\n"
        f"Language hint: {language}\n"
        f"Runtime error message if any: '{error_msg}'\n\n"
        f"CODE TO DEBUG:\n"
        f"```\n{code}\n```"
    )

    try:
        resp = await asyncio.to_thread(_call_gemini_api, client, prompt)
        return resp.text
    except Exception as e:
        logger.error(f"Code debugging failed: {e}")
        return format_gemini_error(e)
