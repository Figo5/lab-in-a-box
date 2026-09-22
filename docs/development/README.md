# Demo evidence

The original animated local-lab walkthrough is preserved at
[its recorded revision](https://github.com/Figo5/lab-in-a-box/blob/8273a94935f5aa3cb2ae9e4b11aae47eec6532bc/demo.gif).
It contains machine-specific Python warnings and paths, so it is not used as the
public hero visual. [The VHS recording script](demo.tape) is retained; run it from
the repository root after installing VHS and the lab requirements.

The current README image is a browser-rendered transcript of actual
`labctl --help` output captured on 2026-09-22. No vulnerable target was started,
no attack was run, and the command requires no network or credentials.

Validation for this presentation pass: 65 labctl tests, 45 tool tests, and both
PageProbe JavaScript suites passed. This does not claim a fresh Docker integration
run. Localhost bindings and private-bridge configuration are unchanged.
