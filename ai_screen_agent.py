"""
AI Screen Control Agent — All-in-one
--------------------------------------
Requirements:
    pip install pyautogui pillow anthropic

Usage:
    python ai_screen_agent.py
    Then type a task when prompted, e.g. "open notepad and type hello world"
"""

import os
import time
import json
import base64
import re
import pyautogui
import anthropic
from PIL import ImageGrab

# ── Safety ──────────────────────────────────────────────────────────────────
pyautogui.FAILSAFE = True       # move mouse to top-left corner to abort
pyautogui.PAUSE = 0.3           # small delay between every pyautogui call

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY    = os.getenv("ANTHROPIC_API_KEY", "sk-ant-YOUR_ACTUAL_KEY")
MODEL      = "claude-opus-4-5"
MAX_STEPS  = 15                 # max actions per task before giving up
STEP_DELAY = 1.5                # seconds to wait after each action

# ── Client ───────────────────────────────────────────────────────────────────
client = anthropic.Anthropic(api_key=API_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# 1. SCREEN CAPTURE
# ─────────────────────────────────────────────────────────────────────────────
def capture_screen() -> str:
    """Grab the full screen and return it as a base64 PNG string."""
    screenshot = ImageGrab.grab()
    # Downscale to speed up API calls (1280 wide max)
    w, h = screenshot.size
    if w > 1280:
        ratio = 1280 / w
        screenshot = screenshot.resize((1280, int(h * ratio)))

    import io
    buf = io.BytesIO()
    screenshot.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ─────────────────────────────────────────────────────────────────────────────
# 2. ASK AI
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an AI desktop agent that controls a Windows PC.
You see screenshots and decide the next single action to complete the user's task.

Respond ONLY with a valid JSON object — no explanation, no markdown, no extra text.

Available actions:
  {"action": "click",       "x": <int>, "y": <int>}
  {"action": "right_click", "x": <int>, "y": <int>}
  {"action": "double_click","x": <int>, "y": <int>}
  {"action": "type",        "text": "<string>"}
  {"action": "key",         "keys": ["ctrl", "c"]}
  {"action": "scroll",      "x": <int>, "y": <int>, "amount": <int (positive=up, negative=down)>}
  {"action": "move",        "x": <int>, "y": <int>}
  {"action": "screenshot"}   <- use this if you need to re-examine the screen
  {"action": "done",        "message": "<summary of what was accomplished>"}
  {"action": "error",       "message": "<reason you cannot continue>"}

Rules:
- Always choose the SINGLE best next action.
- Coordinates are pixels from the top-left corner of the screen.
- Use "done" when the task is fully completed.
- Use "error" only if the task is impossible or you are stuck after several attempts.
"""

def ask_ai(screenshot_b64: str, task: str, history: list) -> dict:
    """Send the current screenshot + task to Claude and get back an action dict."""
    messages = history + [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": screenshot_b64,
                    },
                },
                {
                    "type": "text",
                    "text": f"Current task: {task}\n\nWhat is the next single action?",
                },
            ],
        }
    ]

    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if the model adds them anyway
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"action": "error", "message": f"AI returned invalid JSON: {raw}"}


# ─────────────────────────────────────────────────────────────────────────────
# 3. EXECUTE ACTION
# ─────────────────────────────────────────────────────────────────────────────
def execute_action(action: dict) -> str:
    """Perform the action on the desktop. Returns a short status string."""
    a = action.get("action")

    if a == "click":
        pyautogui.click(action["x"], action["y"])
        return f"Clicked ({action['x']}, {action['y']})"

    elif a == "right_click":
        pyautogui.rightClick(action["x"], action["y"])
        return f"Right-clicked ({action['x']}, {action['y']})"

    elif a == "double_click":
        pyautogui.doubleClick(action["x"], action["y"])
        return f"Double-clicked ({action['x']}, {action['y']})"

    elif a == "type":
        pyautogui.typewrite(action["text"], interval=0.04)
        return f"Typed: {action['text']!r}"

    elif a == "key":
        pyautogui.hotkey(*action["keys"])
        return f"Key: {'+'.join(action['keys'])}"

    elif a == "scroll":
        pyautogui.scroll(action["amount"], x=action["x"], y=action["y"])
        return f"Scrolled {action['amount']} at ({action['x']}, {action['y']})"

    elif a == "move":
        pyautogui.moveTo(action["x"], action["y"], duration=0.3)
        return f"Moved to ({action['x']}, {action['y']})"

    elif a == "screenshot":
        return "Re-examining screen"

    elif a in ("done", "error"):
        return action.get("message", "")

    else:
        return f"Unknown action: {a}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. MAIN AGENT LOOP
# ─────────────────────────────────────────────────────────────────────────────
def run_agent(task: str):
    print(f"\n🤖  Starting task: {task}")
    print("    (Move mouse to TOP-LEFT corner to emergency-stop)\n")

    history = []   # keeps assistant turns for context (no images, just text)

    for step in range(1, MAX_STEPS + 1):
        print(f"── Step {step}/{MAX_STEPS} ──────────────────────────")

        # Capture
        print("  📷  Capturing screen...")
        screenshot_b64 = capture_screen()

        # Ask AI
        print("  🧠  Asking AI...")
        action = ask_ai(screenshot_b64, task, history)
        print(f"  ➡️   Action: {json.dumps(action)}")

        # Record assistant reply in history (text-only to keep context window small)
        history.append({
            "role": "assistant",
            "content": json.dumps(action),
        })

        # Terminal actions
        if action.get("action") == "done":
            print(f"\n✅  Done! {action.get('message', '')}")
            return True

        if action.get("action") == "error":
            print(f"\n❌  Agent stopped: {action.get('message', '')}")
            return False

        # Execute
        status = execute_action(action)
        print(f"  ✔️   {status}")

        # Feed execution result back so AI has full context
        history.append({
            "role": "user",
            "content": f"Action result: {status}",
        })

        time.sleep(STEP_DELAY)

    print(f"\n⚠️  Reached max steps ({MAX_STEPS}). Task may be incomplete.")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 5. ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  AI Screen Control Agent")
    print("  FAILSAFE: move mouse to TOP-LEFT to abort")
    print("=" * 55)

    if API_KEY == "YOUR_API_KEY_HERE":
        print("\n⚠️  Set your API key first:")
        print("    export ANTHROPIC_API_KEY=sk-ant-...")
        print("    or edit API_KEY in this file\n")

    while True:
        try:
            task = input("\nTask (or 'quit'): ").strip()
            if task.lower() in ("quit", "exit", "q"):
                break
            if task:
                run_agent(task)
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break