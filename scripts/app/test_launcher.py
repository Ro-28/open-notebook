"""Offline launcher regression tests; never invoke the real stack."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('open-notebook.sh')


class LauncherTests(unittest.TestCase):
    def run_shell(self, body):
        # Load definitions only, isolate all runtime state before calling functions.
        source = SCRIPT.read_text().split('\ncase "${1:-}" in')[0]
        with tempfile.TemporaryDirectory() as directory:
            source = source.replace('ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"',
                                    f'ROOT="{Path(directory).resolve()}"')
            return subprocess.run(['/bin/bash', '-c', source + '\n' + body],
                                  text=True, capture_output=True, timeout=20,
                                  env={k: v for k, v in os.environ.items() if k != 'UI_PORT'})

    def test_default_ui_port(self):
        result = self.run_shell('printf "%s" "$UI_URL"')
        self.assertEqual(result.stdout, 'http://localhost:3001')

    def test_unowned_listener_rejected(self):
        result = self.run_shell('''
port_busy() { return 0; }
alive() { return 1; }
check_port frontend "$UI_PORT"
''')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('unowned', result.stdout)

    def test_stale_pid_does_not_kill_unrelated_process(self):
        result = self.run_shell('''
sleep 60 & victim=$!
trap 'kill "$victim" 2>/dev/null || true' EXIT
echo "$victim" > "$PID_DIR/frontend.pid"
stop_one frontend
kill -0 "$victim"
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legacy_pid_cannot_cross_services(self):
        result = self.run_shell('''
kill() { return 0; }
lsof() { printf 'n%s\\n' "$MAIC_DIR"; }
ps() { case "$*" in *command*) printf 'next-server (v16)';; *) printf 'started';; esac; }
! owned_pid frontend 123 || exit 2
owned_pid openmaic 123 || exit 3
lsof() { printf 'n%s\\n' "$ROOT/frontend"; }
! owned_pid openmaic 123 || exit 4
owned_pid frontend 123
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_openmaic_running_rebuild_rejected_before_writes(self):
        result = self.run_shell('''
mkdir -p "$MAIC_DIR"
touch "$MAIC_DIR/package.json"
alive() { [ "$1" = openmaic ]; }
port_busy() { return 0; }
check_port() { return 0; }
pnpm() { echo UNEXPECTED; return 1; }
start_openmaic
result=$?
[ "$result" = 1 ] && [ ! -e "$MAIC_DIR/.env" ]
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('UNEXPECTED', result.stdout)
        self.assertIn('stop', result.stdout)

    def test_frontend_port_migration_fails_before_side_effects(self):
        result = self.run_shell('''
alive() { [ "$1" = frontend ]; }
port_busy() { return 1; }
ensure_env() { echo UNEXPECTED; exit 1; }
start
''')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn('UNEXPECTED', result.stdout)
        self.assertIn('stop/restart', result.stdout)
        self.assertIn('3001', result.stdout)

    def test_started_stamp_does_not_override_service_identity(self):
        result = self.run_shell('''
kill() { return 0; }
lsof() { printf 'n%s\\n' "$MAIC_DIR"; }
ps() { case "$*" in *command*) printf 'next-server (v16)';; *) printf 'started';; esac; }
printf started > "$PID_DIR/frontend.started"
! owned_pid frontend 123
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_openmaic_unowned_listener_rejected_before_writes(self):
        result = self.run_shell('''
mkdir -p "$MAIC_DIR"
touch "$MAIC_DIR/package.json"
alive() { return 1; }
port_busy() { return 0; }
start_openmaic
result=$?
[ "$result" = 1 ] && [ ! -e "$MAIC_DIR/.env" ]
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('unowned', result.stdout)

    def test_frontend_running_rebuild_rejected(self):
        result = self.run_shell('''
mkdir -p "$ROOT/.venv" "$ROOT/frontend/node_modules"
alive() { [ "$1" = frontend ]; }
port_busy() { return 0; }
check_port() { return 0; }
ensure_env() { touch "$ROOT/.env"; }
start_bg() { return 0; }
wait_port() { return 0; }
npm() { echo UNEXPECTED > "$ROOT/build-called"; return 1; }
start
result=$?
[ "$result" = 1 ] && [ ! -f "$ROOT/build-called" ]
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('stop/restart', result.stdout)

    def test_owned_start_stop_tree(self):
        result = self.run_shell('''
start_bg worker bash -c 'bash -c "sleep 60 & wait" & wait' # fixture process tree
# Only command identity is substituted: cwd, birth time and signals remain real.
ps() { case "$*" in *command*) printf 'surreal-commands-worker --import-modules commands';; *) command ps "$@";; esac; }
p=$(pid_of worker)
trap 'pkill -KILL -P "$p" 2>/dev/null; kill "$p" 2>/dev/null || true' EXIT
sleep 0.2
child=$(pgrep -P "$p")
grandchild=$(pgrep -P "$child")
[ -n "$grandchild" ] || exit 2
trap 'kill "$grandchild" "$child" "$p" 2>/dev/null || true' EXIT
start_bg worker sleep 60
[ "$(pid_of worker)" = "$p" ] || exit 3
stop_one worker
! kill -0 "$grandchild" 2>/dev/null
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_owned_listener_allowed(self):
        result = self.run_shell('''
start_bg api python3 "''' + str(SCRIPT.with_name('socket_fixture.py')) + '''" "$ROOT/port"
# Only the service command is substituted, not socket or ownership checks.
ps() { case "$*" in *command*) printf 'uvicorn api.main:app';; *) command ps "$@";; esac; }
p=$(pid_of api)
trap 'stop_one api' EXIT
port=''
for _ in {1..50}; do
    [ -f "$ROOT/port" ] && port=$(cat "$ROOT/port")
    [ -n "$port" ] && port_busy "$port" && break
    sleep 0.1
done
[ -n "$port" ] || { ps -p "$p" -o pid,ppid,command; lsof -a -p "$p" -i; cat "$LOG_DIR/api.log"; exit 2; }
[ "$(nc -w 2 127.0.0.1 "$port")" = ready ] || exit 4
check_port api "$port" || exit 3
# A valid owner PID must not confer ownership of a different listener.
lsof() { if [ "$1" = '-t' ]; then printf '%s\\n' "$$"; else command lsof "$@"; fi; }
! check_port api "$port"
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_start_fails_before_side_effects_on_collision(self):
        result = self.run_shell('''
port_busy() { return 0; }
ensure_env() { echo UNEXPECTED; }
start
''')
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('UNEXPECTED', result.stdout)


if __name__ == '__main__':
    unittest.main()
