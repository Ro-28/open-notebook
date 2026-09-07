"""Apply the Soft Fern theme (DESIGN.md) to frontend/src/app/globals.css. Idempotent."""
import re
from pathlib import Path

p = Path(__file__).resolve().parents[2] / "frontend" / "src" / "app" / "globals.css"
s = p.read_text()
if "Soft Fern" in s:
    print("already applied")
    raise SystemExit(0)


def rep(old, new):
    global s
    assert old in s, old[:60]
    s = s.replace(old, new, 1)


def rep_re(pat, new):
    global s
    m = re.search(pat, s, re.S)
    assert m, pat[:50]
    s = s[: m.start()] + new + s[m.end():]


rep('   OPEN NOTEBOOK — DESIGN FOUNDATION ("Quiet Green")',
    '   OPEN NOTEBOOK — DESIGN FOUNDATION ("Soft Fern" — tokens in /DESIGN.md)')
rep('''     hairline borders, near-zero shadows — popovers own the one real shadow
     geometry is squared, 4–6px, floor is 4 · mono is for data, not prose''',
    '''     depth from soft elevation; borders are optional hairlines
     geometry is rounded, 6–18px, floor is 6 · mono is for data, not prose''')
rep('''  /* shape — squared: instrument, not toy; floor is 4px */
  --radius-sm: 4px;
  --radius-md: 5px;
  --radius-lg: 5px;
  --radius-xl: 6px;''', '''  /* shape — rounded, not pill; floor is 6px */
  --radius-xs: 6px;
  --radius-sm: 8px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --radius-xl: 18px;
  --radius-2xl: 22px;''')
rep('''  --primary: #2e6b4f;
  --primary-hover: #245740;
  --on-primary: #f1f8f3;

  --danger: #b0432d;
  --danger-deep: #93341f;
  --danger-tint: #f5e4df;''', '''  --primary: #2f7a57;
  --primary-hover: #276849;
  --on-primary: #f2faf5;

  --danger: #c24a34;
  --danger-deep: #a13b27;
  --danger-tint: #fbeae5;''')
rep_re(r'  --bg: #f5f5f2;.*?--line-strong: #23252a;', '''  --bg: #f7f6f2;
  --bg-deep: #f1f0eb;

  --surface: #ffffff;
  --surface-raised: #ffffff;
  --surface-recessed: #f1f0eb;
  --surface-sunken: #e9e8e2;

  --ink: #1f2125;
  --ink-soft: #5a5e66;
  --ink-faint: #8b8f97;
  --ink-faintest: #aaadb4;

  --line: #e6e5df;
  --line-soft: #eeede7;
  --line-strong: #1f2125;''')
rep_re(r'  --shadow-soft: 0 1px 2px rgba\(35, 37, 42, 0\.06\);.*?--shadow-overlay: [^\n]*\n',
       '''  --shadow-soft: 0 1px 2px rgba(31, 33, 37, 0.05), 0 1px 1px rgba(31, 33, 37, 0.03);
  --shadow-lift: 0 2px 6px rgba(31, 33, 37, 0.07), 0 12px 28px rgba(31, 33, 37, 0.08);
  --shadow-pop: 0 4px 12px rgba(31, 33, 37, 0.1), 0 24px 48px rgba(31, 33, 37, 0.14);
  --shadow-overlay: 0 6px 16px rgba(31, 33, 37, 0.12), 0 32px 64px rgba(31, 33, 37, 0.2);
''')
rep('  --radius: 5px;\n', '  --radius: 10px;\n')
rep_re(r'  --bg: #17181b;.*?--line-strong: #ecedea;', '''  --bg: #141619;
  --bg-deep: #0f1113;

  --surface: #1c1f24;
  --surface-raised: #23272d;
  --surface-recessed: #23272d;
  --surface-sunken: #2b3037;

  --ink: #eeefea;
  --ink-soft: #adb1b8;
  --ink-faint: #7a7e86;
  --ink-faintest: #666a71;

  --line: #2f333a;
  --line-soft: #272b31;
  --line-strong: #eeefea;''')
rep_re(r'  --primary: #3d8e67;\n  --primary-hover: #479e74;', '''  --primary: #4ca47a;
  --primary-hover: #5ab489;''')
rep_re(r'  --shadow-soft: 0 1px 2px rgba\(0, 0, 0, 0\.35\);.*?--shadow-overlay: [^\n]*\n',
       '''  --shadow-soft: 0 1px 2px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(255, 255, 255, 0.03);
  --shadow-lift: 0 2px 6px rgba(0, 0, 0, 0.4), 0 12px 28px rgba(0, 0, 0, 0.45);
  --shadow-pop: 0 4px 12px rgba(0, 0, 0, 0.45), 0 24px 48px rgba(0, 0, 0, 0.55);
  --shadow-overlay: 0 6px 16px rgba(0, 0, 0, 0.5), 0 32px 64px rgba(0, 0, 0, 0.6);
''')

addition = '''
/* ============================================================================
   SOFT FERN — modern surface polish (elevation, motion, rounded geometry)
   ========================================================================== */
@layer components {
  /* cards: soft shadow at rest, lift on hover — depth carries hierarchy */
  [data-slot="card"] {
    box-shadow: var(--shadow-soft);
    border-color: var(--line-soft);
    transition: box-shadow var(--motion-base) ease, transform var(--motion-base) ease, border-color var(--motion-base) ease;
  }
  [data-slot="card"].cursor-pointer:hover,
  [data-slot="card"][role="button"]:hover,
  a > [data-slot="card"]:hover {
    box-shadow: var(--shadow-lift);
    transform: translateY(-1px);
    border-color: var(--line);
  }

  /* dialogs & command palette own the real shadows */
  [data-slot="dialog-content"],
  [data-slot="alert-dialog-content"] {
    box-shadow: var(--shadow-pop);
    border-radius: var(--radius-xl);
  }
  [data-slot="dialog-overlay"],
  [data-slot="alert-dialog-overlay"] {
    background-color: color-mix(in oklab, var(--ink) 40%, transparent) !important;
    backdrop-filter: blur(6px);
  }
  [data-slot="popover-content"],
  [data-slot="dropdown-menu-content"],
  [data-slot="select-content"] {
    box-shadow: var(--shadow-lift);
    border-radius: var(--radius-md);
  }

  /* inputs: quiet at rest, teal ring on focus */
  [data-slot="input"],
  [data-slot="textarea"],
  [data-slot="select-trigger"] {
    background-color: var(--surface);
    border-radius: var(--radius-sm);
  }

  /* buttons: rounded; outline sits on surface; primary gets a subtle inner highlight */
  [data-slot="button"] {
    border-radius: var(--radius-md);
  }
  [data-slot="button"].border:not(.bg-primary):not(.bg-destructive):not(.bg-secondary) {
    background-color: var(--surface);
  }
  [data-slot="button"].border:not(.bg-primary):not(.bg-destructive):hover {
    box-shadow: var(--shadow-soft);
  }
  [data-slot="button"].bg-primary {
    box-shadow: 0 1px 2px rgba(31, 33, 37, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.12);
  }

  .app-sidebar .sidebar-menu-item {
    border-radius: var(--radius-sm);
  }

  /* badges & chips are pills */
  [data-slot="badge"] {
    border-radius: 999px;
  }

  /* headings get the display face */
  h1, h2, h3 {
    font-family: var(--font-display);
    letter-spacing: -0.015em;
  }
}
'''
s = s.rstrip("\n") + "\n" + addition
p.write_text(s)
print("applied", p)
