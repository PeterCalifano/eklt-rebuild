# AGENTS.md

Write to CONTEXT.md the context before compaction to prevent data loss.
After auto-compaction, read again AGENTS.md and CONTEXT.md before restarting.
## EKLT Project Contract

EKLT combines the original ROS1 frame-backed event tracker with a ROS-free
native core, FIBAR event reconstruction, generated Python/MATLAB adapters, and
an experimental ROS2 event-only overlay. Preserve the original frame-backed
and event-only initialization paths as first-class alternatives.

### Build and validation entrypoints

- `./build_lib.sh` builds the ROS-free native core and optional wrappers.
- `./build_lib.sh --python` builds the Python 3.12 gtwrap adapter.
- `./build_lib.sh --matlab` builds the MATLAB R2024b gtwrap adapter.
- `./build_lib.sh --profile` enables the parent profiling configuration.
- `./build_ros1.sh --import-dependencies` owns ROS1 Noetic catkin builds.
- `./build_ros2.sh` owns the independent ROS2 Jazzy colcon overlay.
- Native builds must remain out of source. Use an explicit build directory.
- `--clean` may remove only a named directory below `build/` whose CMake cache
  belongs to this checkout. Never weaken the path and ownership checks.
- Plans and staged work use Markdown checkboxes (`- [ ]` and `- [x]`) with
  explicit acceptance and stop conditions.

### Architecture and compatibility boundaries

- The original ROS1 tracker, ROS-free native library, FIBAR, wrappers, and the
  ROS2 overlay use C++17.
- Keep ROS-free code independent of catkin and ROS message types.
- Keep the ROS2 overlay confined to `ros2/` plus its documented root build
  helper, workflow, configuration, docs, and shared ROS-free API seams.
- Consult `doc/eklt_events_only.md`, `doc/ros2_event_only.md`, and
  `doc/developments/dataset_and_online_streaming_plan.md` before changing
  event-only or ROS2 behavior. Files under `doc/developments/archive/` are
  historical records, not current implementation authority.
- Preserve the project naming convention for new C++ types: `C*` classes,
  `S*` data structures, `E*` enums, and `T*` aliases.

### Wrapper and MATLAB policy

- External library checkouts live below `lib/`: FIBAR at `lib/fibar_lib` and
  gtwrap at `lib/wrap`. Both use the SSH origins recorded in `.gitmodules`.
  Do not restore a repository-root `extern/` directory. MATLAB SDK paths below
  `${Matlab_ROOT}/extern` are installation-owned and are not repository
  dependencies. Do not update or modify either external checkout during
  ordinary EKLT work.
- Wrapper declarations live in `wrap_interfaces/`; native dtype adaptation and
  wrapper-facing orchestration live in `src/wrap_adapters/`.
- Use Eigen-backed vectors and matrices for wrapper array exchange.
- Do not introduce wrapper classes that merely duplicate a native type. When a
  boundary class is required for dtype conversion or functional coordination,
  name it `*Adapter` or `*Orchestrator`.
- Do not hand-edit generated Python, MATLAB, MEX, or pybind output.
- Python wheels and CMake Python installs must co-locate every non-system
  shared-library dependency, use loader-relative runtime paths, and omit
  `_wrapper_build.py`.
- MATLAB support targets R2024b. Start MATLAB manually or with the existing
  workstation launcher while preloading the system `libgcc_s` and
  `libstdc++`; never add a repository-local MATLAB launcher.

### Template inheritance and feature policy

- Files inherited under `cmake/` are immutable in this derived repository.
  Do not patch them to work around target build failures.
- When an inherited helper fails, first correct EKLT's use of its documented
  API. If the helper itself is defective, report the evidence as an upstream
  parent-template issue and pause rather than changing the local copy. Sync a
  helper only after the parent fix is authorized and verified.
- Plain-CMake installation must list target-owned public headers explicitly.
  Do not export ROS1, Ceres, Eigen, or wrapper headers unless the corresponding
  target and package dependency are part of that configured install.
- OptiX, PTX, and ZeroMQ are not active EKLT features. Do not restore their
  options, dependencies, root includes, targets, workflows, or documentation.
  Historical inherited helper snapshots may remain untouched.
- CUDA, TBB, OpenMP, OpenGL, profiling, documentation, and wrappers remain
  opt-in.
- Use the parent workflow filenames and `verify_*` display-name convention:
  `build_linux.yml`, `build_ros1.yml`, `build_ros2_overlay.yml`, and
  `docs_pages.yml`.
- Do not copy donor template-conformance fixtures or recursive
  `VerifyTemplateProject*` tests into this product repository.

### Repository and external-tool safety

- Treat the live dirty worktree as authoritative and preserve unrelated user
  changes.
- Do not stage, commit, tag, or push unless the user explicitly authorizes the
  exact action.
- Do not edit parent, submodule, or other external repositories without
  explicit permission.
- If an external tool, dependency repository, or inherited helper prevents a
  required gate, report the exact issue and pause. Do not silently patch around
  the external boundary.

## Language-Specific Guidance

### Python

Use Python >= 3.12 and preserve the established
`event_vision_utils` public API and naming. Type hints must always be present
on hand-written callables. Prefer dataclasses to unstructured dictionaries and
enums to multi-value literals. Use matplotlib for ordinary plots, PIL or OpenCV
for image-specific work, and seaborn for statistics-oriented plots. Use PyTorch
for machine-learning work with scikit-learn support, and retain ONNX export
compatibility when applicable. New public classes or functions require
documentation and a runnable example with expected output.

### C++ and CUDA

Use C++17 consistently for the original ROS1 tracker, shared ROS1-facing
interfaces, the ROS-free native library, FIBAR, wrappers, and ROS2.
CUDA is optional and primarily targets versions newer than 12.6. Keep technical
answers direct and clear. Use Catch2 for native unit tests. Follow nearby code
and the `C*`/`S*`/`E*`/`T*` type convention. Prefer classes for
stateful behavior and structs for plain data contracts. Concepts are only
available in explicitly C++20-isolated code; do not introduce them into the
C++17 target graph.

### CMake and derived-project test policy

Do not copy template-conformance CMake verifiers into a derived project merely
because the donor template has them. In particular, do not register tests that
recursively configure and rebuild the same derived project inside its ordinary
CTest suite when a fresh configure/build/install/consumer command or CI job
already proves the contract.

For a derived project:

- prefer Catch2 or pytest for project runtime behavior;
- validate CMake options, headless/full feature matrices, installation,
  packaging, and external consumers through explicit fresh out-of-tree
  acceptance commands owned by local CI;
- use disposable consumer projects outside the normal test build when nested or
  installed consumption must be proven;
- add a permanent CMake-script test only when it is lightweight, target-owned,
  isolates behavior unavailable through an existing target/test, and does not
  recursively rebuild the project;
- never import `VerifyTemplateProject*` or other donor self-validation tests as
  product tests.

The template repository may retain broader conformance tests because it owns
generic generation and tailoring behavior. That exception does not make those
tests part of the derived-project contract.

### MATLAB

Use classes a lot also in MATLAB, with a python style, but do it only when it makes sense. Functions in MATLAB are often more efficient. Evaluate whether it makes sense to have stateful implementation. Use "self" instead of "obj". All variables names must specify the datatype of the variable since MATLAB does not (hungarian notation). The following list applies: d for double, f for float, b for bool, str for struct and not for strings, char for strings and chars, ui8 for uint8, i8 for int8.  All the other integers are similar to the latter. Specify "obj" as prefix if an object, cell if a cell, table if a table; "bus_" if a Simulink bus. The names are always in Pascal case including the prefix, for instance ui8MyVariable. Never nest functions definitions within other functions, always do them separate or at most in the same file (after the main function implementation). Add them as local in the same function file only when not re-used elsewhere, otherwise prefer a single implementation. Function names and static methods of classes starts with Capital letter. Local functions names ends with underscore meaning "private". Names of variables must be explicative and tell what the variable does. Short names are not allowed unless "very local in scope". Use underscore for those variables and preferably Tmp within the name. For codes that are intended to be algorithms of some kind (e.g. not plots or things to run on the host PC), make them always MATLAB codegen safe (especially if codegen directive is used). In that case names should be limited to 31 chars. Add the same template of doc to functions as below and always specify arguments-end block for input and output:
%% SIGNATURE
%
% -------------------------------------------------------------------------------------------------------------
%% DESCRIPTION
% -------------------------------------------------------------------------------------------------------------
%% INPUT
% -------------------------------------------------------------------------------------------------------------
%% OUTPUT
% -------------------------------------------------------------------------------------------------------------
%% CHANGELOG
% DD-MM-YYYY  Pietro Califano     First prototype.
% -------------------------------------------------------------------------------------------------------------
%% DEPENDENCIES
%
% -------------------------------------------------------------------------------------------------------------

%% Function code

## Staged-Code Review Quality Gate

Before handing staged changes to the user for commit review, inspect the complete
Git index with `git diff --cached`. Apply this gate to files staged by either the
user or the agent. This review does not authorize staging, committing, or
rewriting unrelated code.

For every staged source file that is new or substantially modified:

- Add or update both levels of applicable documentation: the file/module-level
  header and the public class/function/method documentation. Follow the
  established consolidated files for the relevant language and component.
- Organize related statements into visually separated blocks. Each block must
  implement one immediate objective or implementation step, not an entire broad
  feature.
- Introduce each non-obvious block with a concise comment explaining what it
  accomplishes and, when relevant, why that approach is required.
- Prefer purpose-, invariant-, and contract-oriented comments. Do not add
  comments that merely translate individual statements into prose.
- Preserve useful existing comments and documentation unless the staged change
  makes them incorrect.
- Review the staged result as a reader will receive it, rather than reviewing
  only the individual lines edited during implementation.

Limit cleanup to the intended scope of the staged work. Do not rewrite unrelated
legacy code merely because the same file is staged. Do not report the changes as
ready for review until this pass is complete; summarize any documentation or
readability cleanup performed during the pass.

### C++ and CUDA pattern

Use Doxygen for both the file header and public API documentation:

- Preserve compact grouped formatting when related call arguments or arithmetic
  terms remain readable on one continuation line. Wrap at semantic expression
  boundaries; do not mechanically place every argument on a separate line.
- In a multiline function declaration, definition, or call, keep the first
  argument on the same line as the function name and align later arguments with
  it. Put the opening parenthesis at the end of a line only for a genuinely
  multiline first argument whose own structure requires separation.
- Follow the surrounding hand-formatted style and preserve intentional
  whitespace used to separate functional blocks. Do not apply broad automatic
  reformatting to staged or user-owned code.
- Prefer this compact grouped layout:

```cpp
const float gx =
    0.5F * (PixelOrZero(image, width, height, x + 1, y) -
            PixelOrZero(image, width, height, x - 1, y));

SPhotometricPatch(int id,
                  const cv::Point2d &center,
                  int64_t t_us,
                  int patch_size);
```

  Do not expand the same calls into one line per argument unless an individual
  argument is itself a multiline expression whose structure requires it.

```cpp
/// @file observation_loader.cpp
/// @brief Loads validated observations from a delimited input file.
/// @details Owns parsing and validation; filtering policy remains with the
///          caller.

/// @brief Load and validate observations from disk.
/// @param inputPath Path to the delimited observation file.
/// @return Valid observations in input order.
/// @throws std::runtime_error When the file cannot be parsed.
std::vector<CObservation> LoadValidObservations(
    const std::filesystem::path& inputPath)
{
    // Parse the complete file first so malformed rows produce one consistent
    // diagnostic path.
    const std::vector<CObservation> parsedObservations =
        ParseObservations(inputPath);

    // Retain only observations satisfying the domain validity contract while
    // preserving their original order.
    std::vector<CObservation> validObservations;
    validObservations.reserve(parsedObservations.size());
    std::copy_if(parsedObservations.begin(),
                 parsedObservations.end(),
                 std::back_inserter(validObservations),
                 IsObservationValid);

    return validObservations;
}
```

### Python pattern

Use Google-style module, class, method, and function docstrings. Keep type hints
on every callable and follow the repository naming conventions:

```python
"""Load and validate observation records.

This module owns file parsing and domain validation. Selection policy remains
with the caller.

Example:
    observations = load_valid_observations(Path("observations.csv"))
    print(len(observations))

Output:
    3
"""


def load_valid_observations(input_path: Path) -> list[Observation]:
    """Load valid observations while preserving their input order.

    Args:
        input_path: Path to the delimited observation file.

    Returns:
        Valid observations in input order.

    Raises:
        ValueError: If an input row cannot be parsed.

    Example:
        observations = load_valid_observations(Path("observations.csv"))
        print(len(observations))

    Output:
        3
    """
    # Parse all rows through one path so malformed input produces consistent
    # diagnostics.
    parsed_observations = parse_observations(input_path)

    # Enforce the domain validity contract without changing source ordering.
    valid_observations = [
        observation
        for observation in parsed_observations
        if observation.is_valid()
    ]

    return valid_observations
```

### MATLAB pattern

For a primary MATLAB function file, the leading sectioned function
documentation is also the file-level entry documentation. Scripts require an
opening sectioned description, while class files require class help text plus
the same sectioned documentation on public methods. Keep the existing
`SIGNATURE`, `DESCRIPTION`, `INPUT`, `OUTPUT`, `CHANGELOG`, and `DEPENDENCIES`
template:

```matlab
function tableValidObservations = LoadValidObservations(charInputPath)
%% SIGNATURE
% tableValidObservations = LoadValidObservations(charInputPath)
% -------------------------------------------------------------------------------------------------------------
%% DESCRIPTION
% Load and validate observations while preserving their input order.
% -------------------------------------------------------------------------------------------------------------
%% INPUT
% charInputPath             Path to the delimited observation file.
% -------------------------------------------------------------------------------------------------------------
%% OUTPUT
% tableValidObservations    Valid observations in input order.
% -------------------------------------------------------------------------------------------------------------
%% CHANGELOG
% DD-MM-YYYY  Pietro Califano     First prototype.
% -------------------------------------------------------------------------------------------------------------
%% DEPENDENCIES
% ParseObservations
% -------------------------------------------------------------------------------------------------------------

arguments
    charInputPath (1, :) char
end

arguments (Output)
    tableValidObservations table
end

% Parse all rows through one path so malformed input produces consistent
% diagnostics.
tableParsedObservations = ParseObservations(charInputPath);

% Enforce the domain validity contract without changing source ordering.
bValidObservation = tableParsedObservations.bIsValid;
tableValidObservations = tableParsedObservations(bValidObservation, :);

end
```
