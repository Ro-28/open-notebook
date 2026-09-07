# Theme reliability specification

Node 26.3.0 exposes a global localStorage getter returning undefined without --localstorage-file. Vitest jsdom leaves that existing global in place; Zustand createJSONStorage captures undefined and later setItem throws. The original 3 failures disappear with NODE_OPTIONS=--no-experimental-webstorage (13/13), isolating the environment rather than theme rendering.

Ranked hypotheses: (1) native Node storage shadows jsdom (confirmed by flag probe); (2) Zustand hydration regression (disconfirmed by unchanged store passing probe); (3) React subscription/remount failure (disconfirmed by original assertions passing probe).

Bind test globals explicitly to the current Vitest jsdom storage before store imports. Use actual Storage rather than a no-op persistence mock; keep production component/store unchanged. Add storage regression assertions and preserve all original theme assertions. Build in a temporary frontend copy excluding environment files and live .next output.
