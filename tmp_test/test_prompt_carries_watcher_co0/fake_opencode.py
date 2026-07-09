import os, sys, time

args = sys.argv[1:]                      # ["run", "--model", model, (prompt)]
model = args[2] if len(args) > 2 else "?"
prompt = args[3] if len(args) > 3 else sys.stdin.read()
mode = os.environ.get("FAKE_OPENCODE_MODE", "ok")

if mode == "ok":
    sys.stdout.write(f"FAKE-REPLY model={model} prompt_chars={len(prompt)}")
elif mode == "echo":
    sys.stdout.write(prompt)
elif mode == "err":
    sys.stderr.write("AuthError: no credentials configured for this provider\n")
    sys.stderr.write("  at some/internal/frame.js:42\n")
    sys.exit(2)
elif mode == "empty":
    pass
elif mode == "sleep":
    time.sleep(8)
    sys.stdout.write("too late")
sys.exit(0)
