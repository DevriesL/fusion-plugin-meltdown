## Project

**Meltdown — Fusion 360 AI Plugin**

A native Fusion 360 AI plugin that lets users without CAD experience design and iterate CNC-machinable structural parts through conversational interaction — similar to "vibe coding" but for 3D CAD. Users describe what they want in natural language, attach reference images, use @context references, and the AI modifies the current design through a visual agentic loop: modify model → capture viewport → Gemini vision reviews → continue or present to user.

**Core Value:** Users can continuously iterate mechanical parts in their current Fusion 360 design through natural language, without needing to know CAD operations — the AI sees its own work and keeps refining until the result matches the intent.

### Constraints

- **Runtime**: Fusion 360's embedded Python (3.10+), no arbitrary pip install — must bundle or vendor dependencies
- **Threading**: All Fusion API calls on main thread; async AI work must dispatch back via custom events
- **AI Model**: Gemini 3.1 Pro via PydanticAI (vision + reasoning)
- **UI**: Palette-based HTML/JS — no native Fusion dialogs for main interaction
- **Design Mode**: Hybrid design environment (first phase default)
- **No MCP**: AI reasoning is plugin-internal, no external AI orchestration protocol

## Technology Stack

## Languages
- Python 3.x - Fusion 360 add-in implementation and command handling
- JavaScript (ES6+) - Browser-based UI in palette components
- HTML5 - Palette UI structure
- SVG - Icon resources
## Runtime
- Autodesk Fusion 360 (desktop application runtime)
- Windows
- macOS
- Not applicable - No external Python package dependencies
## Frameworks
- Autodesk Fusion API (`adsk.core`, `adsk`) - Core Fusion 360 extension framework
- Fusion Add-In SDK - Python-based plugin system with manifest-driven configuration
## Key Dependencies
- `adsk.core` - Fusion 360 Application API, User Interface API, Command system
- `adsk` - Fusion 360 root module namespace for all Fusion APIs
## Configuration
- `DEBUG` flag in `config.py` - Controls logging verbosity
- Manifest-driven configuration via `meltdown.manifest`
## Platform Requirements
- Autodesk Fusion 360 (with Python API access enabled)
- Python 3.6+ (included with Fusion 360)
- IDE with Python support (VSCode with debugging configuration)
- Target: Autodesk Fusion 360 add-ins folder
- Manifest file: `meltdown.manifest` (JSON format)
- Icon: `AddInIcon.svg`
## Add-in Configuration
- Product: Fusion 360
- Type: Add-in
- Author: (empty - template)
- Description: (empty - template)
- Version: (empty - template)
- Startup behavior: `runOnStartup: false`
- Supported OS: Windows and macOS
- Edit enabled: true
- Icon file: `AddInIcon.svg`
- `meltdown/meltdown.py` - Primary add-in entry point

## Conventions

## Naming Patterns
- Module entry points: `entry.py` (e.g., `meltdown/commands/paletteShow/entry.py`)
- Configuration files: `config.py` (e.g., `meltdown/config.py`)
- Utility modules: `[function]_utils.py` (e.g., `general_utils.py`, `event_utils.py`)
- JavaScript: `[feature].js` (e.g., `palette.js`)
- Package markers: `__init__.py` for package directories
- snake_case for all function names
- Command handlers use descriptive names: `command_created`, `command_execute`, `command_destroy`, `command_validate_input`
- Event handlers use pattern: `[element]_[event]` (e.g., `palette_closed`, `palette_navigating`, `palette_incoming`)
- Utility functions: `[verb]_[object]` (e.g., `add_handler`, `clear_handlers`, `handle_error`)
- Private functions (internal only): prefix with underscore (e.g., `_create_handler`, `_define_handler`)
- Global module constants: UPPERCASE (e.g., `CMD_ID`, `CMD_NAME`, `WORKSPACE_ID`, `PALETTE_ID`)
- Local variables and parameters: snake_case
- Type-annotated parameters in utility functions
- Module-level lists for managing state: lowercase (e.g., `local_handlers`, `_handlers`)
- Type hints used in function signatures where clarity is needed
- Import types from `adsk.core` (e.g., `adsk.core.CommandCreatedEventArgs`)
- Cast command inputs with type annotations for clarity: `text_box: adsk.core.TextBoxCommandInput = inputs.itemById('text_box')`
## Code Style
- No detected linting/formatting tool (no .eslintrc, .prettierrc, .flake8, pyproject.toml)
- Follow PEP 8 style conventions by convention
- Indentation: 4 spaces (Python standard)
- Line length: appears to follow standard conventions without strict enforcement
- Spacing: blank lines between function definitions, logical sections within functions
- Not detected. Code quality is maintained through manual review patterns and adherence to template structure
## Import Organization
- Relative imports use parent directory notation: `from ... import config`, `from ...lib import fusionAddInUtils as futil`
- Star imports used sparingly in `__init__.py` for re-exporting utility functions: `from .general_utils import *`
- Module aliasing for command imports: `from .commandDialog import entry as commandDialog`
## Error Handling
- Try-except blocks in top-level entry points to catch all errors: `try: ... except: futil.handle_error('run')`
- Centralized error handling via `futil.handle_error(name)` utility function
- Error handler logs full traceback: `traceback.format_exc()`
- Event handlers wrapped with try-except to prevent callback failures from breaking the application
- Optional message box display for user-facing errors via `show_message_box` parameter
## Logging
- Log informational messages with consistent format: `futil.log(f'{CMD_NAME}: [Event description]')`
- Log errors using `adsk.core.LogLevels.ErrorLogLevel` severity
- Log to multiple outputs based on DEBUG flag:
- Optional forced console output with `force_console` parameter
- Use f-strings for message formatting
## Comments
- Function docstrings in utility functions explaining parameters and behavior
- Inline comments for non-obvious logic or Autodesk API quirks
- TODO comments for template placeholders requiring customization (e.g., `# TODO *** Change these names ***`)
- Section dividers using asterisks for code organization (e.g., `# ******** Add a button into the UI ********`)
- Event handler comments explaining when the handler fires and what it does
- Python docstrings using triple quotes for public utility functions
- Format: Description, Arguments section, Returns section
- Example from `general_utils.py`:
## Function Design
- Command handler callbacks take single `args` parameter with type annotation
- Keyword-only arguments for optional parameters in utility functions (e.g., `add_handler(..., *, name: str = None, local_handlers: list = None)`)
- Type hints used in utility function signatures
- Event handlers typically return nothing (side effects only)
- Utility functions return values when appropriate (e.g., `add_handler` returns the created handler)
- JSON serialization for inter-process communication: `json.dumps(data)` for sending to HTML, `json.loads(data)` for receiving
## Module Design
- Top-level modules export `start()` and `stop()` functions for lifecycle management
- Utility modules re-export all public functions in `__init__.py`
- Each command module is self-contained with its own handlers and configuration
- `meltdown/lib/fusionAddInUtils/__init__.py` uses star imports to expose utilities: `from .general_utils import *; from .event_utils import *`
- `meltdown/commands/__init__.py` imports command modules with aliases and maintains a list of command modules for lifecycle management
- Each command lives in its own directory with `entry.py` as the main module
- Resources (HTML, CSS, icons) organized in `resources/[type]` subdirectories
- Shared utilities grouped under `lib/[category]`
- Configuration module at root for global settings

## Architecture

## Pattern Overview
- Autodesk Fusion 360 add-in architecture with multiple discrete commands
- Event-driven command execution with handler pattern
- Separation between add-in lifecycle (startup/shutdown) and command execution
- HTML/JavaScript front-end communication for palette UI
- Centralized utility layer for event and error handling
## Layers
- Purpose: Add-in initialization and lifecycle management
- Location: `meltdown/meltdown.py`
- Contains: `run()` and `stop()` functions that manage add-in startup/shutdown
- Depends on: Commands module, Utilities module
- Used by: Fusion 360 add-in loader
- Purpose: Define and manage individual commands exposed to Fusion UI
- Location: `meltdown/commands/` directory
- Contains: Individual command modules (paletteShow, commandDialog, paletteSend)
- Depends on: Utilities layer, Fusion SDK (adsk.core)
- Used by: Entry point layer, Fusion UI event system
- Purpose: Each command encapsulates a complete feature
- Location: `meltdown/commands/{commandName}/entry.py`
- Contains: Start/stop functions, UI button registration, event handler definitions
- Depends on: Fusion SDK, utilities, config
- Used by: Commands registry (`meltdown/commands/__init__.py`)
- Purpose: Shared helpers for event handling, logging, and error management
- Location: `meltdown/lib/fusionAddInUtils/` (exported from `__init__.py`)
- Contains: Event handler wrapper utilities, logging, error handling
- Depends on: Fusion SDK
- Used by: All command implementations, entry point
- Purpose: Global configuration and constants
- Location: `meltdown/config.py`
- Contains: Debug flags, add-in metadata, palette IDs, company/product names
- Depends on: None
- Used by: All command implementations, utilities
- Purpose: Interactive UI within Fusion palette
- Location: `meltdown/commands/paletteShow/resources/html/`
- Contains: HTML markup, JavaScript event handlers, Fusion API calls
- Depends on: `adsk.fusionSendData()` global (provided by Fusion)
- Used by: Fusion palette container
## Data Flow
- **Local handlers:** Each command module maintains `local_handlers = []` list to keep references to event handlers and prevent garbage collection
- **Global handlers:** Utility layer maintains `_handlers = []` global list for handlers that aren't command-specific
- **Configuration state:** `meltdown/config.py` holds immutable configuration values accessed by all modules
- **Palette state:** Palette existence and visibility tracked by Fusion SDK; commands check `ui.palettes.itemById()` before reusing or creating palettes
## Key Abstractions
- Purpose: Encapsulate a single feature as a UI command
- Examples: `meltdown/commands/paletteShow/entry.py`, `meltdown/commands/commandDialog/entry.py`
- Pattern: Each module exports `start()` and `stop()` functions following the command lifecycle; handlers are defined as module-level functions
- Purpose: Create type-safe event handler classes that wrap callbacks with error handling
- Examples: `meltdown/lib/fusionAddInUtils/event_utils.py` - `add_handler()`, `_create_handler()`, `_define_handler()`
- Pattern: Dynamic class creation to match Fusion SDK's handler interface requirements; automatic error wrapping
- Purpose: Re-export all utilities from nested modules for clean imports
- Examples: `meltdown/lib/fusionAddInUtils/__init__.py` (wildcard imports)
- Pattern: Barrel file pattern allowing `from .lib import fusionAddInUtils as futil` to access `log()`, `handle_error()`, `add_handler()`, etc.
## Entry Points
- Location: `meltdown/meltdown.py`
- Triggers: Fusion 360 loads the add-in (via meltdown.manifest)
- Responsibilities: Call `run()` on startup to initialize commands; call `stop()` on shutdown to clean up
- Location: `meltdown/commands/__init__.py`
- Triggers: Fusion calls `meltdown.run()`
- Responsibilities: Import all command modules and coordinate their startup/shutdown via loops
- Location: `meltdown/commands/{commandName}/entry.py` (e.g., `paletteShow/entry.py`)
- Triggers: Called by `commands.start()` during add-in initialization
- Responsibilities: Register UI buttons, define event handlers, manage command lifecycle
## Error Handling
- **Add-in level** (`meltdown/meltdown.py`): Wraps `commands.start()` and `commands.stop()` in try-except, calls `futil.handle_error()` on failure
- **Handler level** (`meltdown/lib/fusionAddInUtils/event_utils.py`): Handler wrapper classes catch exceptions in `notify()` callback and call `handle_error()`
- **Utility function** (`meltdown/lib/fusionAddInUtils/general_utils.py`): `handle_error()` logs traceback to file and optionally shows message box based on `show_message_box` flag
## Cross-Cutting Concerns
- `meltdown/lib/fusionAddInUtils/general_utils.py` - `log()` function handles debug/info/error logging
- Uses Fusion SDK logging API with configurable levels
- Prints to console, optionally writes to Fusion log file and Text Command window based on `DEBUG` config flag
- Centralized in `meltdown/config.py`
- Imported by utilities and all commands
- Provides `COMPANY_NAME`, `ADDIN_NAME`, `DEBUG`, and palette ID constants
- Global handler registry in `meltdown/lib/fusionAddInUtils/event_utils.py` prevents garbage collection
- Per-command local handler lists override global registry for command-scoped cleanup
- Clear operations via `clear_handlers()` during add-in shutdown
