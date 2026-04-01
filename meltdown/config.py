# Application Global Variables
# This module serves as a way to share variables across different
# modules (global variables).

import os

# Flag that indicates to run in Debug mode or not. When running in Debug mode
# more information is written to the Text Command window. Generally, it's useful
# to set this to True while developing an add-in and set it to False when you
# are ready to distribute it.
DEBUG = True

# Gets the name of the add-in from the name of the folder the py file is in.
# This is used when defining unique internal names for various UI elements 
# that need a unique name. It's also recommended to use a company name as 
# part of the ID to better ensure the ID is unique.
ADDIN_NAME = os.path.basename(os.path.dirname(__file__))
COMPANY_NAME = 'ACME'

# Core infrastructure paths
ADDIN_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(ADDIN_DIR, 'lib')
SECRETS_PATH = os.path.join(ADDIN_DIR, '.secrets')

# Custom event IDs
BRIDGE_EVENT_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_BridgeEvent'

# Palettes
sample_palette_id = f'{COMPANY_NAME}_{ADDIN_NAME}_palette_id'

# Phase 3: Chat Interface
CHAT_PALETTE_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_chat_palette'
CHAT_PALETTE_NAME = 'Meltdown'
CHAT_PALETTE_WIDTH = 650   # Per D-04
CHAT_PALETTE_HEIGHT = 600  # Per D-04

# Phase 2: Agent and Visual Loop
MAX_VISUAL_ITERATIONS = 5  # Default iteration cap before asking user permission (D-06)
VIEWPORT_CAPTURE_WIDTH = 1920  # Visual review screenshot width
VIEWPORT_CAPTURE_HEIGHT = 1080  # Visual review screenshot height
AGENT_DISPATCH_TIMEOUT = 60.0  # Seconds to wait for a bridge operation result (modeling ops may be slow)

# Phase 4: Context System and Multi-Part
STANDARD_VIEWS = {
    'front': 3,   # adsk.core.ViewOrientations.FrontViewOrientation
    'back': 1,    # adsk.core.ViewOrientations.BackViewOrientation
    'top': 10,    # adsk.core.ViewOrientations.TopViewOrientation
    'bottom': 2,  # adsk.core.ViewOrientations.BottomViewOrientation
    'left': 8,    # adsk.core.ViewOrientations.LeftViewOrientation
    'right': 9,   # adsk.core.ViewOrientations.RightViewOrientation
    'iso': 7,     # adsk.core.ViewOrientations.IsoTopRightViewOrientation
}

# Default angles for visual_review multi-angle capture
VISUAL_REVIEW_ANGLES = ['front', 'right', 'top', 'iso']

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB limit for reference images -- keep in sync with chat.js

# Phase 8: Session Persistence
SESSION_DIR = os.path.join(ADDIN_DIR, '.sessions')
MAX_SESSIONS = 50  # Auto-prune beyond this limit (SESS-05)