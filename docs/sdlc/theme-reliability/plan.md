# Theme reliability plan

1. Reproduce original tests and isolate runtime cause (done: 3 failed / 10 passed; webstorage-disabled probe 13 passed).
2. Add focused real browser-storage environment regression; run RED before setup change.
3. Make minimal setup-only binding to Vitest jsdom storage; verify GREEN plus unchanged theme tests.
4. Run complete tests, lint, and production build in isolated temporary copy to protect live port 3000.
5. Review diff and write data/app/theme-reliability-report.md with commands, counts, warnings and scope. No commits or pushes.
