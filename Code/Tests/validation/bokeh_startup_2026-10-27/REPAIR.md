# Bokeh startup performance — 2026-10-27

The installed local service has been restarted with this repair.

## Measured cause and change

Initial application composition repeatedly traversed the complete Bokeh model
reference graph as temporary component roots were attached, removed, styled,
and combined. A production-runtime profile recorded 300 full graph rebuilds,
consuming 78.44 of 81.58 profiled seconds before any document reached the browser.

`build_document` now batches reference resolution only while constructing a new,
empty document. It resolves the final graph once before returning the document.
Incremental live model/solution updates continue resolving references immediately;
the previously repaired browser reference-lifetime behavior is preserved.
Exceptions unwind the graph batching counter before propagating.

Catalog discovery for direct server opens now runs after DocumentReady on the
existing loader executor. Its result restores the same first-entry selection and
updates both dataset selectors. Explicit plot contexts still select their exact
recorded dataset. Hidden comparison datasets wait until comparison is enabled,
avoiding a second source load and Gaussian calculation during startup.

No solver equations, scientific arrays, native axes, filtering definitions, source
identities, or saved research products were changed by the repair.

## Timing

Same-process, unprofiled application construction in the deployed Python runtime,
using empty product/raw roots to isolate document construction from disk/FFT work:

| Measurement | Seconds | Bokeh objects |
| --- | ---: | ---: |
| Before | 43.2554 | 5,231 |
| After | 1.4782 | 5,231 |
| After, repeated | 1.4606 | 5,231 |

This is approximately 29 times faster for initial construction. The profiled
comparison was 81.58 to 3.29 seconds. These figures are document-construction
measurements, not total source-cube loading or solver/FFT completion times.

## Validation

47 distinct automated tests passed across three invocations:

- Six startup tests (4.81 seconds), including all five launch aliases, required
  entrypoint errors, exactly one initial graph rebuild in a live session,
  construction-exception recovery, discovery after DocumentReady, and deferred
  hidden-comparison loading.
- Two transport and three rendering/reference-lifetime tests passed as part of
  the 10-test initial focused run (400.19 seconds). Its five startup tests overlap
  the final six-test startup run and are counted only once.
- 36 numerical/filter/UI responsiveness tests passed (20.48 seconds), covering
  all seven models, native axes, signed physical arrays, Gaussian display,
  asynchronous lifecycle and client preview behavior. Three tests using a
  separate integration fixture were deselected in this invocation.

The deployed port-5013 service was restarted successfully and is listening.
A browser opened the exact previously recorded hx_50g 0–440 km simulation context.
Both the simulated phase-difference and Gaussian-filtered result plots populated,
and Save Filter Parameters became enabled. No data substitution was used.
A separate deterministic 12-by-40 native Fourier fixture was used for browser
model switching checks: all seven model selectors changed to the matching native
heading and returned to 3D MAG, retaining the 12-by-40 dataset grid. The browser
console recorded no errors during those checks. The service continues loading original cubes and
performing exact native FFT/filter/model work asynchronously; cold large-cube
work is not included in the construction timing.

The portable extracted application and ZIP were not rebuilt for this local-service
performance repair. Existing browser sessions require a reload to use new code.
