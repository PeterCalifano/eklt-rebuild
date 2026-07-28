# Native FIBAR adapter

`event_vision_utils.recon` is the optional extraction boundary to the generated
`eklt_rebuild` binding in the same distribution. It does not compile, scan for,
or privately load another extension module.

The adapter normalizes generic `EventArray` values, copies exact Eigen exchange
arrays through gtwrap, and returns owning NumPy image and patch data. FIBAR
reconstruction remains implemented only by `libeklt-rebuild`.

Build the generated binding before running the native adapter regression:

```bash
./build_lib.sh \
  --build-dir build/event-vision-utils-wrapper \
  --type Release \
  --python \
  --define WARNINGS_ARE_ERRORS=ON

PYTHONPATH="python" \
  python3.12 -m pytest -q \
  python/tests/event_vision_utils/test_recon_fibar_native.py
```

Expected output:

```text
4 passed
```

Without the generated wrapper, importing `event_vision_utils` and its generic
data modules still succeeds. Constructing `CFibarReconstructor` reports the
missing optional binding without falling back to an unrelated binary.
