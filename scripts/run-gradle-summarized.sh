#!/bin/zsh

set -euo pipefail

if [[ $# -lt 1 ]]; then
  printf 'USAGE: %s <repo-path> [gradle args ...]\n' "$0" >&2
  exit 64
fi

requested_repo_path="$1"
shift

repo_path="$requested_repo_path"
if [[ ! -x "$repo_path/gradlew" && -x "$PWD/gradlew" ]]; then
  repo_path="$PWD"
fi

if [[ ! -d "$repo_path" ]]; then
  printf 'RESULT=ERROR\n'
  printf 'REASON=repo path does not exist: %s\n' "$repo_path"
  exit 1
fi

gradlew="$repo_path/gradlew"
if [[ ! -x "$gradlew" ]]; then
  printf 'RESULT=ERROR\n'
  printf 'REASON=missing executable gradlew at %s\n' "$gradlew"
  exit 1
fi

if [[ $# -eq 0 ]]; then
  printf 'RESULT=ERROR\n'
  printf 'REASON=no Gradle tasks or arguments provided\n'
  exit 1
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
log_dir="${TMPDIR:-/tmp}/coding-colony-gradle"
mkdir -p "$log_dir"
log_file="$log_dir/gradle-${timestamp}-$$.log"

cmd=("$gradlew" "--console=plain" "--no-daemon" "--quiet" "$@")

printf 'COMMAND=%s\n' "${cmd[*]}"
printf 'LOG_FILE=%s\n' "$log_file"

set +e
(cd "$repo_path" && "${cmd[@]}") >"$log_file" 2>&1
exit_code=$?
set -e

summary="$(
python3 - "$log_file" "$exit_code" <<'PY'
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
exit_code = int(sys.argv[2])
text = log_path.read_text(encoding="utf-8", errors="ignore")
lines = text.splitlines()

def emit(label: str, value: str) -> None:
    print(f"{label}={value}")

def clean(line: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line).strip()

result = "SUCCESS" if exit_code == 0 else "ERROR"
if re.search(r"\bNO-SOURCE\b", text) and exit_code == 0:
    result = "SUCCESS_NO_SOURCE"

emit("RESULT", result)
emit("EXIT_CODE", str(exit_code))

build_lines = [clean(line) for line in lines if "BUILD " in line or "FAILURE: Build failed" in line]
if build_lines:
    emit("BUILD_STATUS", " | ".join(build_lines[-3:]))

failed_tasks = []
for line in lines:
    m = re.search(r"> Task (.+?) FAILED", clean(line))
    if m:
        failed_tasks.append(m.group(1))
if failed_tasks:
    emit("FAILED_TASKS", " | ".join(dict.fromkeys(failed_tasks)))

interesting_tests = []
for line in lines:
    cleaned = clean(line)
    if re.search(r"\b(Test|Tests?)\b.*\bFAILED\b", cleaned):
        interesting_tests.append(cleaned)
if interesting_tests:
    emit("FAILED_TESTS", " | ".join(interesting_tests[:10]))

root_cause = []
capture = False
for line in lines:
    cleaned = clean(line)
    if cleaned.startswith("* What went wrong:"):
        capture = True
        continue
    if capture:
        if cleaned.startswith("* Try:") or cleaned.startswith("Exception is:"):
            break
        if cleaned:
            root_cause.append(cleaned)
if root_cause:
    emit("ROOT_CAUSE", " | ".join(root_cause[:8]))

high_signal = []
for line in lines:
    cleaned = clean(line)
    if not cleaned:
        continue
    if any(token in cleaned for token in ["FAILED", "BUILD SUCCESSFUL", "BUILD FAILED", "NO-SOURCE", "FAILURE: Build failed"]):
        high_signal.append(cleaned)

if high_signal:
    print("HIGHLIGHTS_BEGIN")
    for line in high_signal[:40]:
      print(line)
    print("HIGHLIGHTS_END")
PY
)"

printf '%s\n' "$summary"

exit "$exit_code"
