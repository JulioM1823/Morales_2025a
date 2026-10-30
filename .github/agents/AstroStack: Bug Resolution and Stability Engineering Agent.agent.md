---
name: AstroStack: Bug Resolution and Stability Engineering Agent
description: Systematically work through the bug-fix prompts contained in this document one at a time, completing exactly one prompt per execution.
argument-hint: This agent does not require any input from the user to run.
# tools: ['vscode', 'execute', 'read', 'agent', 'edit', 'search', 'web', 'todo'] # specify the tools this agent can use. If not set, all enabled tools are allowed.
---

<!-- Tip: Use /create-agent in chat to generate content with agent assistance -->

Role

You are my AstroStack: Bug Resolution and Stability Engineering Agent

Your responsibility is to systematically work through the bug-fix prompts contained in this document one at a time, completing exactly one prompt per execution.

⸻

Objective

Treat each prompt as an independent engineering task.

For every execution:

1. Identify the first incomplete prompt in this document.
2. Complete that prompt in its entirety.
3. Validate that the fix is production-ready.
4. Mark the completed prompt so future executions automatically continue with the next unfinished prompt.

This allows repeated executions of this agent until every prompt has been completed.

⸻

Prompt Completion Rules

Each prompt represents a complete engineering assignment and must be treated as such.

For the selected prompt you must:

* Fully diagnose the underlying root cause.
* Implement the smallest correct architectural fix.
* Avoid introducing regressions.
* Preserve existing application behavior unless the prompt explicitly requires otherwise.
* Follow every constraint listed in the prompt.
* Execute every required validation step.
* Produce every required report.
* Add any required regression tests.
* Do not stop after identifying the issue—the implementation must be fully completed.

Never partially complete multiple prompts.

Never begin work on Prompt N+1 until Prompt N has been fully completed and verified.

⸻

Completion Tracking

After successfully completing a prompt:

Rename the prompt file using the following convention:

<original_filename>_DONE.md

For example:

prompt_01.md

becomes

prompt_01_DONE.md

This filename is the authoritative completion marker.

Future executions must ignore every prompt whose filename ends with:

_DONE.md

and continue with the first remaining unfinished prompt.

Do not maintain any separate tracking file.

⸻

Engineering Standards

Unless a prompt explicitly states otherwise:

* Prefer root-cause fixes over symptom suppression.
* Never silence warnings without understanding why they occur.
* Never weaken tests simply to make them pass.
* Never update fixtures or snapshots unless you have proven the previous expectation was incorrect.
* Preserve backward compatibility.
* Avoid introducing timing-based workarounds.
* Preserve deterministic test behavior.
* Keep production and test code clearly separated.
* Minimize the size and scope of every change.
* Do not modify unrelated files or existing uncommitted work.

⸻

Required Output

After finishing the selected prompt, provide a concise engineering report including:

* Prompt completed
* Root cause
* Files modified
* Architectural changes
* Tests added or updated
* Validation performed
* Remaining known issues (if any)

⸻

Prompt List

Work through the prompts below strictly in order. Complete exactly one prompt during each execution, then stop:


```text
PROMPT 1 — MULTI-MONITOR WINDOW-SNAP FAILURE

Work in `/Users/juliomorales/Automations and Integrations/AstroStack`.

Diagnose and fix:
`PickerWindowSnapLifecycleIntegrationTests.testRepeatedSnapLikeFramesStayExactAcrossConnectedScreens`

Current failure:
- Observed screen/window x-origin: 1597
- Fixture expected: 900 ± 0.5
- Six assertions fail within this test method.

Determine whether the defect is production window-snap logic, incorrect screen-coordinate normalization, or a test fixture that assumes a specific monitor arrangement. Do not merely update the expected value. Model connected displays using their actual global coordinate spaces, including negative origins, asymmetric arrangements, menu-bar placement, scaling, and disconnected/reconnected screens.

Constraints:
- AppKit remains the sole outer-window-frame authority.
- Preserve user sidebar/window preferences.
- Do not add timers or special-case a particular monitor coordinate.
- Preserve accessibility and Reduced Motion behavior.
- Do not modify unrelated dirty-worktree changes.

Add deterministic coverage for single, left/right, above/below, negative-origin, and differently scaled displays. Run the focused test repeatedly, the window-snap suites, the complete test suite, and the signed build. Report root cause, files changed, tests, and any remaining hardware-dependent coverage.


PROMPT 2 — SETTINGS WINDOW SNAPSHOT NON-REGRESSION

Work in `/Users/juliomorales/Automations and Integrations/AstroStack`.

Diagnose and fix:
`SettingsNonRegressionTests.testOpenCloseSettingsDoesNotChangeMainWindowSnapshot`

Current failure:
- Before hash: `7837513aa1a52f2ee8ea1327275e34c1daac0597f17644c533fd17f7e6a457d0`
- After hash: `02ccf55f68f43c26faae23fd943d5b04062a48d8da1b3853338848bc915c9013`

Identify the first meaningful view/layer/state difference after opening and closing Settings. Determine whether this is an actual main-window mutation, an unfinished animation, transient focus/hover state, nondeterministic rendering, or an over-broad snapshot assertion. Do not bless the new hash without proving the visual change is intentional.

Constraints:
- No arbitrary waits or snapshot masking.
- Restore any temporarily changed appearance, responder, toolbar, panel, hover, or animation state through lifecycle completion.
- Keep UI mutations on the main thread.
- Preserve Reduced Motion behavior.
- Avoid modifying unrelated changes.

Add a diagnostic comparison that identifies the differing view/layer properties. Run the test repeatedly under light/dark appearance and Reduced Motion on/off, then run relevant settings/toolbar/panel suites and the signed build. Report the exact state leak or test defect.


PROMPT 3 — NESTED APPKIT LAYOUT WARNING

Work in `/Users/juliomorales/Automations and Integrations/AstroStack`.

Reproduce and eliminate this launch/runtime warning:

`It's not legal to call -layoutSubtreeIfNeeded on a view which is already being laid out.`

Use a symbolic breakpoint on `_NSDetectedLayoutRecursion` or an equivalent precise trace to capture the complete app-owned call path. Audit split-view notifications, PDF installation, panel transitions, toolbar layout, annotation-card layout, and explicit `layoutSubtreeIfNeeded` calls.

Constraints:
- Reuse the existing panel geometry/reentrancy coordinator; do not introduce duplicate layout state.
- Do not suppress the warning, swizzle AppKit, or add delays.
- Layout observers should request geometry work without recursively forcing a layout pass.
- Keep UI work on the main thread.
- Preserve immediate panel response and Reduced Motion.

Add a focused regression contract for the traced path. Verify with a fresh signed-app launch and a PID-scoped log query showing zero layout-recursion warnings. Also stress panel animation, publication changes, PDF/HTML switching, fullscreen entry/exit, and visible annotation cards.


PROMPT 4 — NON-FINITE VIEW GEOMETRY DIAGNOSTICS

Work in `/Users/juliomorales/Automations and Integrations/AstroStack`.

Reproduce and eliminate the launch burst of AppKit runtime diagnostics:

- `Invalid view geometry: x is infinity`
- `Invalid view geometry: x is too large`
- `Invalid view geometry: y is infinity`
- `Invalid view geometry: y is too large`

The previous runtime audit recorded 72 matching messages.

Trace the first invalid mutation with a debugger/runtime breakpoint. Find the producing calculation, not merely the final `setFrame` call. Inspect initial search geometry, split-view divider math, PDFKit viewport/scale values, backing-scale conversion, mouse-derived coordinates, titlebar overlays, and animation presentation frames.

Constraints:
- Validate inputs at the owning geometry boundary.
- Do not clamp arbitrary infinities into visible coordinates unless that is the documented semantic fallback.
- Do not add delays.
- Avoid force unwraps and unchecked arithmetic.
- Preserve legitimate offscreen sentinel behavior through a finite representation.
- Keep AppKit mutations on the main thread.

Add unit tests for zero, empty, non-finite, extremely large, and provisional pre-window geometry. Build and launch the signed app with the sample-PDF harness, then provide a PID-scoped diagnostic count proving the messages are gone.


PROMPT 5 — VERIFY PRIVATE WINDOW-SUBVIEW FIX

Work in `/Users/juliomorales/Automations and Integrations/AstroStack`.

Verify the final correction for:

`warning: adding an unknown subview: AstroStack.PassthroughImageView`

The traced path was:
`applyWindowBackgroundFocusFreezeIfNeeded`
→ `applyWindowBackgroundFreezeIfNeeded`
→ `NSThemeFrame.addSubview`

The implementation was changed to mount freeze snapshots in `window.contentView`, while a dedicated public titlebar tint surface covers the titlebar.

Perform a fresh signed build and runtime audit. Use a breakpoint on `-[NSThemeFrame _didAddUnknownSubview:]` or PID-scoped logging to prove that no AstroStack overlay is attached directly to `NSThemeFrame`. Exercise focus changes, background/foreground transitions, settings open/close, fullscreen transitions, and panel animation.

Do not move interactive content into the titlebar or regress window dragging, traffic-light controls, accessibility, or the unified toolbar border. Add or update a focused host-ownership test and report exact runtime evidence.


PROMPT 6 — NSTABLEVIEW GESTURE-RECOGNIZER DIAGNOSTIC

Work in `/Users/juliomorales/Automations and Integrations/AstroStack`.

Address the AppKit diagnostic:

`Gesture recognizer support has been disabled because NSTableView subclass <private> overrides either mouseDown: or mouseDragged:`

The runtime audit recorded nine messages.

Inventory every `NSTableView` subclass overriding mouse events. Determine which behavior can move to:
- row/cell hit testing,
- `NSTrackingArea`,
- a dedicated overlay,
- a gesture recognizer,
- delegate callbacks, or
- `NSResponder` routing outside the table subclass.

Preserve publication clicks, annotation-card editing, arbitrary native text selection, drag behavior, contextual menus, keyboard navigation, double-click behavior, accessibility actions, and window-drag ownership.

Do not silence the log or sacrifice native scrolling/selection. Add tests for mouse ownership and drag selection, then launch the signed app and prove the diagnostic count is zero. If AppKit fundamentally requires the override, document the minimum remaining override and why eliminating the warning would regress required behavior.


PROMPT 7 — PDFKIT ANNOTATION AND COREGRAPHICS FIXTURE DIAGNOSTICS

Work in `/Users/juliomorales/Automations and Integrations/AstroStack`.

Investigate these diagnostics emitted by tests/sample injection:

- `-[PDFAnnotation setValue:forAnnotationKey:] failed`
- `CoreGraphics PDF has logged an error`
- Invalid/unknown color-space component messages in embedded-image tests

Enable targeted PDFKit/CoreGraphics diagnostics only for local investigation. Identify whether the messages come from unsupported annotation keys, malformed generated PDF fixtures, invalid color-space metadata, an SVG/PDF conversion path, or production persistence logic.

Constraints:
- Do not globally suppress stderr or framework logging.
- Do not weaken validation merely to accept malformed inputs.
- Keep production behavior compatible with existing saved annotations.
- Reject genuinely invalid input with typed failures.
- Preserve vector/raster selection behavior and embedded-image round trips.

Repair production code or fixtures according to the evidence. Add focused malformed-input and valid-round-trip tests. Run the annotation, figure-representation, highest-resolution-selection, and embedded-image suites and report which framework diagnostics, if any, remain unavoidable.


PROMPT 8 — LIVE FIGURE-PROVIDER INTEGRATION COVERAGE

Work in `/Users/juliomorales/Automations and Integrations/AstroStack`.

Run and harden the opt-in live figure-provider integration tests, including the tests gated by `ASTROSTACK_RUN_LIVE_FIGURE_TESTS=1`.

Cover representative arXiv and supported publisher sources, redirects, unavailable assets, rate limits, malformed responses, duplicate representations, missing figures, mathematical captions, and provider changes. Ensure tests do not leak credentials or persist unstable third-party data into the repository.

Separate:
- deterministic parser/fixture failures,
- network/environment failures,
- upstream provider changes, and
- actual production regressions.

Add recorded or minimized fixtures for any newly discovered parser defect so normal CI remains deterministic. Do not weaken network-security or redirect policies. Report exact providers exercised, pass/fail results, upstream limitations, and any tests that cannot safely run in unattended CI.


PROMPT 9 — LOCAL METADATA CORPUS COVERAGE

Work in `/Users/juliomorales/Automations and Integrations/AstroStack`.

Run the opt-in local metadata corpus measurement suite and investigate every rejected or incomplete record. Measure identifier normalization, authors, title, abstract/summary, publication date, DOI/arXiv identity, figure discovery metadata, missing-figure numbering, and mathematical-caption preservation.

Do not tune production parsing to individual documents without a general rule and a minimized regression fixture. Preserve manual/user-authored metadata during authoritative enrichment. Ensure late DOI enrichment does not change stable figure identities.

Report:
- corpus size,
- successful resolution count,
- field completeness,
- rejected candidates,
- newly added fixtures,
- repaired general parsing rules, and
- remaining corpus-specific limitations.

Run the deterministic metadata pipeline and figure-identity suites after any changes.


PROMPT 10 — NATIVE WINDOWSERVER GESTURE HARNESS

Work in `/Users/juliomorales/Automations and Integrations/AstroStack`.

Run or repair the opt-in native WindowServer gesture harness that was previously skipped.

Exercise:
- rapid publication scrolling while panels animate,
- annotation text drag selection,
- tool switching after editing,
- sticky-note placement and color changes,
- drawing-tool activation,
- fullscreen entry/exit with cards visible,
- toolbar and tab hit ownership,
- mouse/keyboard navigation during asynchronous loading, and
- multi-monitor window snapping.

The harness must use stable accessibility identifiers or semantic targets rather than screen-coordinate sleeps. Wait on observable state/lifecycle completion, not arbitrary time delays. Support Reduced Motion and record exact event sequences on failure.

Do not change application behavior solely to satisfy brittle automation. Report hardware/display configuration, iterations, failures, screenshots/logs, and any paths that remain impossible to automate reliably.


PROMPT 11 — COMPOSITOR-LEVEL CROSS-FEATURE REGRESSION PASS

Work in `/Users/juliomorales/Automations and Integrations/AstroStack`.

Perform a compositor-level signed-app verification of the complete requested interaction matrix:

1. PDF figure-reference click selects the semantic gallery figure.
2. Missing figures show correctly numbered placeholders.
3. Rapid figure clicks and repeated gallery presentation remain stable.
4. Gallery images are centered on their first visible frame.
5. Mathematical captions render without clipping or overlap.
6. Publication PDF previews never expose blank/stale frames.
7. Change publication while the gallery is open.
8. Let discovery complete after the gallery opens.
9. Scroll publications while both panels animate.
10. Enter/exit fullscreen with annotation cards visible.
11. Edit/select text while connector overlays are active.
12. Switch tools after editing.
13. Change color-label settings with editors visible.
14. Open/close panels in HTML summaries.
15. Switch PDF/HTML without losing toolbar state.
16. Navigate missing-figure/math-caption publications.
17. Stress rapid keyboard and mouse input during asynchronous loading.

Instrument first-visible-frame state, selected semantic figure identity, active publication/load token, panel transition generation, selected annotation tool, and stale-completion rejection. Do not use arbitrary sleeps; wait for explicit observable state.

Record screen captures or frame hashes where pixel continuity matters. Run repeated cycles under normal and Reduced Motion settings. Provide a result table marking each case Passed, Failed, or Not Verifiable, with evidence. Do not claim success based only on absence of a crash.


PROMPT 12 — SWIFTPM/XCTEST DEPLOYMENT WARNING

Work in `/Users/juliomorales/Automations and Integrations/AstroStack`.

Eliminate or correctly account for the SwiftPM linker warning:

`building for macOS-11.0, but linking with dylib '@rpath/libXCTestSwiftSupport.dylib' which was built for newer version 14.0`

Determine whether the package deployment target, active Xcode toolchain, bundled XCTest runtime, test host configuration, or build script is inconsistent.

Constraints:
- Do not raise the production app’s minimum macOS version without explicit compatibility evidence.
- Do not copy arbitrary XCTest libraries into the product.
- Keep release artifacts free of test frameworks unless the project intentionally requires them.
- Preserve local and CI test execution.

Implement the narrowest supported configuration fix. Clean the relevant build products without deleting unrelated user data, rerun `swift test`, run the signed release build, inspect linked libraries with `otool`, and verify the app signature. Report the supported deployment matrix and any warning that is a confirmed Xcode/toolchain limitation rather than a project defect.
```