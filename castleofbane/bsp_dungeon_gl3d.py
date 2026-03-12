"""
BSP Dungeon Renderer - Full OpenGL 3D
--------------------------------------
Beneath the Castle of Bane - v0.6.0

New in v0.6.0:
    - Combat: Spellcasting with F key, projectile bolts
    - Enemy AI: Idle/alert/chase/attack state machine
    - Health system: Player HP with damage flash
    - Death/respawn: Press R to restart level
    - Visual effects: Hit bursts, death collapse
    - Opaque doors: Brown (regular) and red (locked)
    - Upgraded staff: Brown wood, gold fittings, pulsing crystal
    - Resizable window with scaling HUD
    - New skeleton and wraith models
"""

from dataclasses import dataclass, field
import math
import time

from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QFont

from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QSurfaceFormat

from OpenGL.GL import (
    glEnable, glDisable, glClear, glClearColor, glClearDepth,
    glDepthFunc, glBegin, glEnd, glVertex3f, glColor3f, glColor4f,
    glMatrixMode, glLoadIdentity, glViewport,
    glLineWidth, glPushMatrix, glPopMatrix,
    glTranslatef, glRotatef,
    GL_DEPTH_TEST, GL_DEPTH_BUFFER_BIT, GL_COLOR_BUFFER_BIT,
    GL_LESS, GL_POLYGON, GL_LINE_LOOP, GL_LINES, GL_LINE_STRIP, GL_QUADS,
    GL_PROJECTION, GL_MODELVIEW,
    GL_POLYGON_OFFSET_FILL, glPolygonOffset,
    GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, glBlendFunc
)
from OpenGL.GLU import gluPerspective

from wireframe_engine.dungeon import DungeonMap, Wall, WallFace, CellType, create_test_dungeon, CELL_SIZE
from wireframe_engine.bsp import BSPTree, build_bsp_from_dungeon
from wireframe_engine.level import Level, Entity, load_level, parse_level, create_test_levels
from combat import CombatManager, PROJECTILE_MODEL


# --- Wireframe Entity Models ---------------------------------------------------

# All models: line segments ((x1,y1,z1), (x2,y2,z2))
# +Y = up for entity rendering (empirically confirmed)
# Feet at y=0 (floor), heads at positive Y (toward ceiling)

KEY_MODEL = {
    'lines': [
        # Ring (top)
        ((-4, 22, 0), (4, 22, 0)),
        ((4, 22, 0), (4, 16, 0)),
        ((4, 16, 0), (-4, 16, 0)),
        ((-4, 16, 0), (-4, 22, 0)),
        # Shaft
        ((0, 16, 0), (0, 4, 0)),
        # Teeth
        ((0, 8, 0), (4, 8, 0)),
        ((0, 4, 0), (4, 4, 0)),
    ],
    'scale': 1.2,
    'bob_speed': 2.0,
    'bob_amount': 3.0,
}

TREASURE_MODEL = {
    'lines': [
        # Chest base
        ((-8, 0, -5), (8, 0, -5)),
        ((8, 0, -5), (8, 0, 5)),
        ((8, 0, 5), (-8, 0, 5)),
        ((-8, 0, 5), (-8, 0, -5)),
        # Chest top
        ((-8, 8, -5), (8, 8, -5)),
        ((8, 8, -5), (8, 8, 5)),
        ((8, 8, 5), (-8, 8, 5)),
        ((-8, 8, 5), (-8, 8, -5)),
        # Vertical edges
        ((-8, 0, -5), (-8, 8, -5)),
        ((8, 0, -5), (8, 8, -5)),
        ((8, 0, 5), (8, 8, 5)),
        ((-8, 0, 5), (-8, 8, 5)),
        # Lid detail
        ((-8, 8, 0), (8, 8, 0)),
        # Gem on front
        ((0, 5, -5), (3, 4, -5)),
        ((3, 4, -5), (0, 3, -5)),
        ((0, 3, -5), (-3, 4, -5)),
        ((-3, 4, -5), (0, 5, -5)),
    ],
    'scale': 1.0,
    'bob_speed': 0.0,
    'bob_amount': 0.0,
}

SKELETON_MODEL = {
    'lines': [
        # === SKULL - Cranium (rounded top, wider than jaw) ===
        ((-7, 44, 0), (-4, 47, 0)),
        ((-4, 47, 0), (-1, 48, 0)),
        ((-1, 48, 0), (1, 48, 0)),
        ((1, 48, 0), (4, 47, 0)),
        ((4, 47, 0), (7, 44, 0)),
        # Temporal bones (sides of skull)
        ((7, 44, 0), (8, 41, 0)),
        ((8, 41, 0), (7, 38, 0)),
        ((-7, 44, 0), (-8, 41, 0)),
        ((-8, 41, 0), (-7, 38, 0)),
        # Cheekbones / zygomatic
        ((7, 38, 0), (6, 37, 0)),
        ((-7, 38, 0), (-6, 37, 0)),
        # === EYE SOCKETS (hollow triangles) ===
        ((-5, 42, 0), (-2, 42, 0)),
        ((-2, 42, 0), (-2, 39, 0)),
        ((-2, 39, 0), (-5, 39, 0)),
        ((-5, 39, 0), (-5, 42, 0)),
        ((-3.5, 42, 0), (-3.5, 39, 0)),  # Vertical crack
        ((2, 42, 0), (5, 42, 0)),
        ((5, 42, 0), (5, 39, 0)),
        ((5, 39, 0), (2, 39, 0)),
        ((2, 39, 0), (2, 42, 0)),
        ((3.5, 42, 0), (3.5, 39, 0)),    # Vertical crack
        # === NASAL CAVITY (inverted triangle) ===
        ((-1.5, 39, 0), (0, 37, 0)),
        ((1.5, 39, 0), (0, 37, 0)),
        ((-1.5, 39, 0), (1.5, 39, 0)),
        # === UPPER JAW / MAXILLA ===
        ((-6, 37, 0), (-5, 36, 0)),
        ((-5, 36, 0), (5, 36, 0)),
        ((5, 36, 0), (6, 37, 0)),
        # === TEETH (vertical lines) ===
        ((-4, 36, 0), (-4, 34.5, 0)),
        ((-2.5, 36, 0), (-2.5, 34.5, 0)),
        ((-1, 36, 0), (-1, 34.5, 0)),
        ((1, 36, 0), (1, 34.5, 0)),
        ((2.5, 36, 0), (2.5, 34.5, 0)),
        ((4, 36, 0), (4, 34.5, 0)),
        # === MANDIBLE (lower jaw, hinged) ===
        ((-5, 36, 0), (-6, 34, 0)),
        ((-6, 34, 0), (-4, 33, 0)),
        ((-4, 33, 0), (4, 33, 0)),
        ((4, 33, 0), (6, 34, 0)),
        ((6, 34, 0), (5, 36, 0)),
        # === CERVICAL SPINE (neck vertebrae) ===
        ((0, 33, 0), (0, 31.5, 0)),
        ((-1.5, 32, 0), (1.5, 32, 0)),
        ((-1, 31, 0), (1, 31, 0)),
        ((0, 31.5, 0), (0, 30, 0)),
        # === CLAVICLES (collar bones - angled up from sternum) ===
        ((0, 30, 0), (-6, 31, 0)),
        ((-6, 31, 0), (-11, 30, 0)),
        ((0, 30, 0), (6, 31, 0)),
        ((6, 31, 0), (11, 30, 0)),
        # === SCAPULA hints (shoulder blades) ===
        ((-11, 30, 0), (-12, 28, 0)),
        ((11, 30, 0), (12, 28, 0)),
        # === STERNUM ===
        ((0, 30, 0), (0, 22, 0)),
        # === RIBS (curved, connecting to spine) ===
        # Rib pair 1
        ((-2, 29, 0), (-7, 29.5, 0)),
        ((-7, 29.5, 0), (-9, 28, 0)),
        ((-9, 28, 0), (-8, 26, 0)),
        ((2, 29, 0), (7, 29.5, 0)),
        ((7, 29.5, 0), (9, 28, 0)),
        ((9, 28, 0), (8, 26, 0)),
        # Rib pair 2
        ((-2, 27, 0), (-8, 27.5, 0)),
        ((-8, 27.5, 0), (-10, 26, 0)),
        ((-10, 26, 0), (-8, 24, 0)),
        ((2, 27, 0), (8, 27.5, 0)),
        ((8, 27.5, 0), (10, 26, 0)),
        ((10, 26, 0), (8, 24, 0)),
        # Rib pair 3
        ((-2, 25, 0), (-8, 25.5, 0)),
        ((-8, 25.5, 0), (-9, 24, 0)),
        ((-9, 24, 0), (-7, 22.5, 0)),
        ((2, 25, 0), (8, 25.5, 0)),
        ((8, 25.5, 0), (9, 24, 0)),
        ((9, 24, 0), (7, 22.5, 0)),
        # Rib pair 4 (floating ribs - shorter)
        ((-2, 23, 0), (-6, 23.5, 0)),
        ((-6, 23.5, 0), (-7, 22, 0)),
        ((2, 23, 0), (6, 23.5, 0)),
        ((6, 23.5, 0), (7, 22, 0)),
        # === LUMBAR SPINE (lower back vertebrae) ===
        ((0, 22, 0), (0, 20, 0)),
        ((-1.5, 21, 0), (1.5, 21, 0)),
        ((0, 20, 0), (0, 18, 0)),
        ((-1.5, 19, 0), (1.5, 19, 0)),
        ((0, 18, 0), (0, 16, 0)),
        # === PELVIS (iliac crests + sacrum) ===
        ((0, 16, 0), (-3, 16, 0)),
        ((-3, 16, 0), (-7, 17, 0)),
        ((-7, 17, 0), (-8, 15, 0)),
        ((-8, 15, 0), (-5, 13, 0)),
        ((-5, 13, 0), (-2, 14, 0)),
        ((0, 16, 0), (3, 16, 0)),
        ((3, 16, 0), (7, 17, 0)),
        ((7, 17, 0), (8, 15, 0)),
        ((8, 15, 0), (5, 13, 0)),
        ((5, 13, 0), (2, 14, 0)),
        ((-2, 14, 0), (2, 14, 0)),  # Pubic symphysis
        # === LEFT LEG ===
        # Femur (thigh)
        ((-5, 13, 0), (-6, 8, 0)),
        # Knee joint
        ((-6, 8, 0), (-7, 7, 0)),
        ((-7, 7, 0), (-5, 7, 0)),
        ((-5, 7, 0), (-6, 8, 0)),
        # Tibia/fibula (shin)
        ((-6, 7, 0), (-5.5, 2, 0)),
        ((-7, 7, 0), (-6.5, 2, 0)),
        # Ankle
        ((-6, 2, 0), (-6, 1, 0)),
        # Foot
        ((-6, 1, 0), (-3, 0, 0)),
        ((-6, 1, 0), (-8, 0, 0)),
        # === RIGHT LEG ===
        # Femur
        ((5, 13, 0), (6, 8, 0)),
        # Knee joint
        ((6, 8, 0), (7, 7, 0)),
        ((7, 7, 0), (5, 7, 0)),
        ((5, 7, 0), (6, 8, 0)),
        # Tibia/fibula
        ((6, 7, 0), (5.5, 2, 0)),
        ((7, 7, 0), (6.5, 2, 0)),
        # Ankle
        ((6, 2, 0), (6, 1, 0)),
        # Foot
        ((6, 1, 0), (3, 0, 0)),
        ((6, 1, 0), (8, 0, 0)),
        # === LEFT ARM ===
        # Humerus (upper arm)
        ((-11, 30, 0), (-13, 23, 0)),
        # Elbow
        ((-13, 23, 0), (-14, 22, 0)),
        ((-14, 22, 0), (-12, 22, 0)),
        ((-12, 22, 0), (-13, 23, 0)),
        # Radius/ulna (forearm)
        ((-13, 22, 0), (-12, 15, 0)),
        ((-14, 22, 0), (-13.5, 15, 0)),
        # Hand bones (dangling)
        ((-12.5, 15, 0), (-11, 12, 0)),
        ((-12.5, 15, 0), (-13, 12, 0)),
        ((-12.5, 15, 0), (-14, 12.5, 0)),
        # === RIGHT ARM ===
        # Humerus
        ((11, 30, 0), (13, 23, 0)),
        # Elbow
        ((13, 23, 0), (14, 22, 0)),
        ((14, 22, 0), (12, 22, 0)),
        ((12, 22, 0), (13, 23, 0)),
        # Radius/ulna
        ((13, 22, 0), (12, 15, 0)),
        ((14, 22, 0), (13.5, 15, 0)),
        # Hand bones
        ((12.5, 15, 0), (11, 12, 0)),
        ((12.5, 15, 0), (13, 12, 0)),
        ((12.5, 15, 0), (14, 12.5, 0)),
    ],
    'scale': 1.0,
    'bob_speed': 0.0,
    'bob_amount': 0.0,
}

GHOST_MODEL = {
    'lines': [
        # === HOOD / COWL (pointed, ominous) ===
        ((0, 48, 0), (-5, 44, 0)),       # Hood peak to left
        ((0, 48, 0), (5, 44, 0)),        # Hood peak to right
        ((-5, 44, 0), (-8, 40, 0)),      # Hood left drape
        ((5, 44, 0), (8, 40, 0)),        # Hood right drape
        # Hood rim (shadowed face opening)
        ((-8, 40, 0), (-6, 38, 0)),
        ((-6, 38, 0), (-3, 37, 0)),
        ((-3, 37, 0), (3, 37, 0)),
        ((3, 37, 0), (6, 38, 0)),
        ((6, 38, 0), (8, 40, 0)),
        # Hood back connection
        ((-5, 44, 0), (-7, 42, 0)),
        ((-7, 42, 0), (-8, 40, 0)),
        ((5, 44, 0), (7, 42, 0)),
        ((7, 42, 0), (8, 40, 0)),
        # === EYES (angular hollow voids) ===
        ((-5, 43, 0), (-3, 44, 0)),
        ((-3, 44, 0), (-2, 42, 0)),
        ((-2, 42, 0), (-4, 41, 0)),
        ((-4, 41, 0), (-5, 43, 0)),
        # Inner eye glow
        ((-4, 43, 0), (-3, 42, 0)),
        ((2, 42, 0), (4, 41, 0)),
        ((4, 41, 0), (5, 43, 0)),
        ((5, 43, 0), (3, 44, 0)),
        ((3, 44, 0), (2, 42, 0)),
        # Inner eye glow
        ((3, 42, 0), (4, 43, 0)),
        # === GAPING MAW (dark void mouth) ===
        ((-2, 39, 0), (-1, 37.5, 0)),
        ((-1, 37.5, 0), (1, 37.5, 0)),
        ((1, 37.5, 0), (2, 39, 0)),
        ((-2, 39, 0), (2, 39, 0)),
        # === SHOULDERS / CLOAK TOP ===
        ((-8, 40, 0), (-12, 35, 0)),
        ((8, 40, 0), (12, 35, 0)),
        # === CLOAK BODY (flowing, wider toward bottom) ===
        ((-12, 35, 0), (-14, 28, 0)),
        ((-14, 28, 0), (-15, 20, 0)),
        ((12, 35, 0), (14, 28, 0)),
        ((14, 28, 0), (15, 20, 0)),
        # === REACHING ARMS (left - clawed) ===
        ((-12, 35, 0), (-16, 30, 0)),
        ((-16, 30, 0), (-18, 26, 0)),
        ((-18, 26, 0), (-19, 24, 0)),
        # Left claw fingers
        ((-19, 24, 0), (-21, 22, 0)),
        ((-19, 24, 0), (-20, 21, 0)),
        ((-19, 24, 0), (-18, 21.5, 0)),
        # === REACHING ARMS (right - clawed) ===
        ((12, 35, 0), (16, 30, 0)),
        ((16, 30, 0), (18, 26, 0)),
        ((18, 26, 0), (19, 24, 0)),
        # Right claw fingers
        ((19, 24, 0), (21, 22, 0)),
        ((19, 24, 0), (20, 21, 0)),
        ((19, 24, 0), (18, 21.5, 0)),
        # === INNER ROBE FOLDS (vertical drape lines) ===
        ((-4, 37, 0), (-6, 20, 0)),
        ((4, 37, 0), (6, 20, 0)),
        ((0, 37, 0), (0, 18, 0)),
        # Cross-fold
        ((-8, 30, 0), (8, 30, 0)),
        # === TATTERED BOTTOM (jagged, ragged edge) ===
        ((-15, 20, 0), (-13, 15, 0)),
        ((-13, 15, 0), (-11, 18, 0)),
        ((-11, 18, 0), (-9, 13, 0)),
        ((-9, 13, 0), (-6, 17, 0)),
        ((-6, 17, 0), (-4, 11, 0)),
        ((-4, 11, 0), (-1, 16, 0)),
        ((-1, 16, 0), (1, 10, 0)),
        ((1, 10, 0), (4, 16, 0)),
        ((4, 16, 0), (6, 12, 0)),
        ((6, 12, 0), (9, 17, 0)),
        ((9, 17, 0), (11, 13, 0)),
        ((11, 13, 0), (13, 18, 0)),
        ((13, 18, 0), (15, 20, 0)),
        # === TRAILING WISPS ===
        ((-4, 11, 0), (-5, 6, 0)),
        ((1, 10, 0), (0, 5, 0)),
        ((6, 12, 0), (7, 7, 0)),
        ((-13, 15, 0), (-14, 10, 0)),
        ((11, 13, 0), (12, 8, 0)),
    ],
    'scale': 1.0,
    'bob_speed': 1.2,
    'bob_amount': 3.5,
}

STAIRS_UP_MODEL = {
    'lines': [
        # Three steps going up (bottom to top)
        ((-10, 0, 8), (10, 0, 8)),
        ((10, 0, 8), (10, 0, 2)),
        ((-10, 0, 2), (-10, 0, 8)),
        ((-10, 6, 2), (10, 6, 2)),
        ((10, 6, 2), (10, 6, -4)),
        ((-10, 6, -4), (-10, 6, 2)),
        ((-10, 12, -4), (10, 12, -4)),
        ((10, 12, -4), (10, 12, -10)),
        ((-10, 12, -10), (-10, 12, -4)),
        ((-10, 12, -10), (10, 12, -10)),
        # Risers
        ((-10, 0, 2), (-10, 6, 2)),
        ((10, 0, 2), (10, 6, 2)),
        ((-10, 6, -4), (-10, 12, -4)),
        ((10, 6, -4), (10, 12, -4)),
        # Arrow pointing up
        ((0, 18, 0), (0, 30, 0)),
        ((0, 30, 0), (-4, 26, 0)),
        ((0, 30, 0), (4, 26, 0)),
    ],
    'scale': 1.0,
    'bob_speed': 0.0,
    'bob_amount': 0.0,
}

STAIRS_DOWN_MODEL = {
    'lines': [
        # Three steps going down (top to bottom)
        ((-10, 12, -10), (10, 12, -10)),
        ((10, 12, -10), (10, 12, -4)),
        ((-10, 12, -4), (-10, 12, -10)),
        ((-10, 6, -4), (10, 6, -4)),
        ((10, 6, -4), (10, 6, 2)),
        ((-10, 6, 2), (-10, 6, -4)),
        ((-10, 0, 2), (10, 0, 2)),
        ((10, 0, 2), (10, 0, 8)),
        ((-10, 0, 8), (-10, 0, 2)),
        ((-10, 0, 8), (10, 0, 8)),
        # Risers
        ((-10, 12, -4), (-10, 6, -4)),
        ((10, 12, -4), (10, 6, -4)),
        ((-10, 6, 2), (-10, 0, 2)),
        ((10, 6, 2), (10, 0, 2)),
        # Arrow pointing down
        ((0, 30, 0), (0, 18, 0)),
        ((0, 18, 0), (-4, 22, 0)),
        ((0, 18, 0), (4, 22, 0)),
    ],
    'scale': 1.0,
    'bob_speed': 0.0,
    'bob_amount': 0.0,
}

ENTITY_MODELS = {
    'key': KEY_MODEL,
    'key_silver': KEY_MODEL,
    'treasure': TREASURE_MODEL,
    'skeleton': SKELETON_MODEL,
    'ghost': GHOST_MODEL,
    'stairs_up': STAIRS_UP_MODEL,
    'stairs_down': STAIRS_DOWN_MODEL,
}

# Special colors for entity types (r, g, b) - overrides scheme color
ENTITY_COLORS = {
    'key': (1.0, 0.85, 0.0),
    'key_silver': (0.75, 0.75, 0.85),
    'treasure': (1.0, 0.85, 0.0),
    'skeleton': None,
    'ghost': None,
    'stairs_up': (0.4, 1.0, 0.4),
    'stairs_down': (0.4, 1.0, 0.4),
    'door': (0.55, 0.35, 0.17),
    'door_locked': (1.0, 0.3, 0.3),
}


# --- Flash Message -----------------------------------------------------------

@dataclass
class FlashMessage:
    text: str
    expire: float
    color: tuple = (1.0, 1.0, 1.0)


# --- Main Renderer -----------------------------------------------------------

class GL3DDungeonRenderer(QGraphicsView):
    """Full OpenGL 3D dungeon renderer with gameplay."""

    COLOR_SCHEMES = {
        'amber': '#FFB000',
        'green': '#00FFAA',
        'blue': '#00BFFF',
        'white': '#FFFFFF',
    }

    def __init__(self, width=800, height=600):
        super().__init__()

        self.win_width = width
        self.win_height = height

        self.scene = QGraphicsScene()
        self.scene.setSceneRect(0, 0, width, height)
        self.setScene(self.scene)

        self.setWindowTitle("BSP Dungeon GL3D - WASD move, C colors, Q quit")
        self.setMinimumSize(width, height)
        self.resize(width, height)
        self.base_width = width    # Reference size for scaling
        self.base_height = height
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheNone)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(Qt.GlobalColor.black))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setInteractive(False)

        gl_widget = QOpenGLWidget()
        fmt = QSurfaceFormat()
        fmt.setSamples(4)
        fmt.setSwapInterval(1)
        fmt.setDepthBufferSize(24)
        gl_widget.setFormat(fmt)
        self.setViewport(gl_widget)
        self.gl_widget = gl_widget

        # Camera
        self.cam_x = 0.0
        self.cam_y = -15.0
        self.cam_z = 0.0
        self.cam_angle = 0.0

        # Level state
        self.dungeon = None
        self.bsp_tree = None
        self.level = None
        self.entities = []
        self.level_dir = ""

        # Gameplay
        self.inventory_keys = 0
        self.inventory_silver_keys = 0
        self.treasure_count = 0
        self.flash_messages = []
        self.game_complete = False
        self.door_open_states = {}

        # Combat
        self.combat = CombatManager()

        # Input / rendering
        self.keys_pressed = set()
        self.color_name = 'amber'
        self.color = QColor(self.COLOR_SCHEMES['amber'])
        self.fill_intensity = 0.15

        # Animation
        self.bob_timer = 0.0
        self.is_moving = False
        self.entity_timer = 0.0

        # Stats
        self.walls_rendered = 0
        self.frame_count = 0

        # Game loop
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    @property
    def hud_scale(self) -> float:
        """Scale factor for HUD elements relative to 800x600 baseline."""
        sx = self.win_width / self.base_width
        sy = self.win_height / self.base_height
        return min(sx, sy)

    def resizeEvent(self, event):
        """Update dimensions when window is resized."""
        super().resizeEvent(event)
        self.win_width = self.width()
        self.win_height = self.height()
        self.scene.setSceneRect(0, 0, self.win_width, self.win_height)

    # --- Level Loading --------------------------------------------------------

    def load_level_file(self, filepath: str):
        from pathlib import Path
        self.level_dir = str(Path(filepath).parent)
        self.level = load_level(filepath)
        self._apply_level(self.level)
        print(f"Loaded: {self.level.name}")

    def load_level_string(self, content: str, name: str = "Unnamed"):
        self.level = parse_level(content, name)
        self._apply_level(self.level)
        print(f"Loaded: {self.level.name}")

    def _apply_level(self, level: Level):
        self.dungeon = level.dungeon
        self.bsp_tree = build_bsp_from_dungeon(self.dungeon)
        self.entities = list(level.entities)
        self.door_open_states = {}

        start_gx, start_gz = level.player_start
        self.cam_x, self.cam_z = self.dungeon.grid_to_world(start_gx, start_gz)
        self.cam_angle = 0.0

        # Init combat for this level (HP carries over)
        self.combat.init_level(self.entities, self.dungeon)

        stats = self.bsp_tree.get_stats()
        print(f"  BSP: {stats['nodes']} nodes, {stats['splits']} splits, depth {stats['depth']}")
        print(f"  Entities: {len(self.entities)}")
        print(f"  Enemies: {len(self.combat.enemies)}")
        self._flash(f"~ {level.name} ~", duration=3.0)

    def _load_next_level(self):
        from pathlib import Path
        if not self.level or not self.level.next_level:
            self.game_complete = True
            self._flash("YOU HAVE ESCAPED!", duration=60.0)
            self._flash("The Castle of Bane lies behind you.", duration=60.0)
            self._flash(f"Treasure collected: {self.treasure_count}", duration=60.0)
            print("\n*** GAME COMPLETE ***")
            return
        next_path = Path(self.level_dir) / self.level.next_level
        if next_path.exists():
            self._flash("Descending deeper...", duration=2.0)
            self.load_level_file(str(next_path))
        else:
            self._flash(f"Level not found: {self.level.next_level}")

    def _load_prev_level(self):
        from pathlib import Path
        if not self.level or not self.level.prev_level:
            # No prev level on level 3 means this is the EXIT
            self.game_complete = True
            self._flash("YOU HAVE ESCAPED!", duration=60.0)
            self._flash("The Castle of Bane lies behind you.", duration=60.0)
            self._flash(f"Treasure collected: {self.treasure_count}", duration=60.0)
            print("\n*** GAME COMPLETE ***")
            return
        prev_path = Path(self.level_dir) / self.level.prev_level
        if prev_path.exists():
            self._flash("Ascending...", duration=2.0)
            self.load_level_file(str(prev_path))
        else:
            self._flash(f"Level not found: {self.level.prev_level}")

    def load_test_dungeon(self):
        dungeon = create_test_dungeon()
        self.dungeon = dungeon
        self.bsp_tree = build_bsp_from_dungeon(dungeon)
        self.level = None
        self.entities = []
        start_x, start_z = self.dungeon.grid_to_world(9, 9)
        self.cam_x = start_x
        self.cam_z = start_z
        self.cam_angle = 0.0
        stats = self.bsp_tree.get_stats()
        print(f"BSP: {stats['nodes']} nodes, {stats['splits']} splits, depth {stats['depth']}")

    # --- Flash Messages -------------------------------------------------------

    def _flash(self, text: str, duration: float = 2.0, color: tuple = None):
        if color is None:
            color = (1.0, 1.0, 1.0)
        self.flash_messages.append(FlashMessage(text=text, expire=time.time() + duration, color=color))

    def _clean_flashes(self):
        now = time.time()
        self.flash_messages = [m for m in self.flash_messages if m.expire > now]

    # --- Game Logic -----------------------------------------------------------

    def _tick(self):
        if self.game_complete:
            self._clean_flashes()
            self.scene.invalidate(self.scene.sceneRect())
            return

        if self.combat.game_over:
            self._handle_death()
            self.scene.invalidate(self.scene.sceneRect())
            return

        self._handle_input()
        self._check_entity_collisions()

        # Combat update
        events = self.combat.update(
            self.cam_x, self.cam_z, self.cam_angle,
            self.dungeon, self.entities, self.door_open_states
        )

        if events['damage_taken'] > 0:
            self._flash(f"-{events['damage_taken']} HP", duration=0.8,
                        color=(1.0, 0.2, 0.2))

        for killed_entity in events['enemies_killed']:
            enemy_name = killed_entity.type.title()
            self._flash(f"{enemy_name} destroyed!", duration=1.5,
                        color=(0.6, 0.9, 1.0))

        if events['player_died']:
            self._flash("YOU HAVE FALLEN!", duration=60.0,
                        color=(1.0, 0.2, 0.2))
            self._flash("Press R to restart level", duration=60.0,
                        color=(1.0, 0.6, 0.2))

        self.entity_timer += 0.03
        self.frame_count += 1
        self._clean_flashes()
        self.scene.invalidate(self.scene.sceneRect())

    def _handle_input(self):
        speed = 3.0
        turn_speed = 2.0
        collision_radius = 12.0

        if Qt.Key.Key_A in self.keys_pressed or Qt.Key.Key_Left in self.keys_pressed:
            self.cam_angle -= turn_speed
        if Qt.Key.Key_D in self.keys_pressed or Qt.Key.Key_Right in self.keys_pressed:
            self.cam_angle += turn_speed

        new_x, new_z = self.cam_x, self.cam_z
        rad = math.radians(self.cam_angle)

        moving = False
        if Qt.Key.Key_W in self.keys_pressed or Qt.Key.Key_Up in self.keys_pressed:
            new_x += math.sin(rad) * speed
            new_z -= math.cos(rad) * speed
            moving = True
        if Qt.Key.Key_S in self.keys_pressed or Qt.Key.Key_Down in self.keys_pressed:
            new_x -= math.sin(rad) * speed
            new_z += math.cos(rad) * speed
            moving = True

        can_move = True
        for dx, dz in [(0, 0), (collision_radius, 0), (-collision_radius, 0),
                        (0, collision_radius), (0, -collision_radius)]:
            gx, gz = self.dungeon.world_to_grid(new_x + dx, new_z + dz)
            if not self.dungeon.is_walkable(gx, gz):
                can_move = False
                break
            # Closed doors block movement (opened doors become FLOOR)
            if self.dungeon.get_cell(gx, gz) == CellType.DOOR:
                can_move = False
                break

        if can_move:
            self.cam_x = new_x
            self.cam_z = new_z

        self.is_moving = moving and can_move
        if self.is_moving:
            self.bob_timer += 0.08
        else:
            self.bob_timer += 0.02

    def _try_open_door(self):
        """Try to open a door the player is facing."""
        rad = math.radians(self.cam_angle)
        # Check at multiple distances to be forgiving
        for dist in [CELL_SIZE * 0.6, CELL_SIZE * 0.3, CELL_SIZE * 0.9]:
            check_x = self.cam_x + math.sin(rad) * dist
            check_z = self.cam_z - math.cos(rad) * dist
            gx, gz = self.dungeon.world_to_grid(check_x, check_z)

            cell = self.dungeon.get_cell(gx, gz)
            if cell != CellType.DOOR:
                continue

            entity = self._get_entity_at(gx, gz)

            if entity and entity.type == 'door_locked':
                if self.inventory_keys > 0:
                    self.inventory_keys -= 1
                    self._open_door(gx, gz)
                    self.entities.remove(entity)
                    self._flash("Unlocked!", color=(1.0, 0.85, 0.0))
                else:
                    self._flash("Locked! Need a key.", color=(1.0, 0.3, 0.3))
            else:
                self._open_door(gx, gz)
                if entity and entity.type == 'door':
                    self.entities.remove(entity)
            return  # Only open one door per press

    def _open_door(self, gx: int, gz: int):
        self.dungeon.set_cell(gx, gz, CellType.FLOOR)
        self.door_open_states[(gx, gz)] = True
        self.dungeon.generate_walls()
        self.bsp_tree = build_bsp_from_dungeon(self.dungeon)
        self._flash("Door opened!")

    def _get_entity_at(self, gx: int, gz: int):
        for e in self.entities:
            if e.gx == gx and e.gz == gz:
                return e
        return None

    def _check_entity_collisions(self):
        gx, gz = self.dungeon.world_to_grid(self.cam_x, self.cam_z)

        to_remove = []
        for entity in self.entities:
            if entity.gx != gx or entity.gz != gz:
                continue

            if entity.type == 'key':
                self.inventory_keys += 1
                to_remove.append(entity)
                self._flash("Got a gold key!", color=(1.0, 0.85, 0.0))
            elif entity.type == 'key_silver':
                self.inventory_silver_keys += 1
                to_remove.append(entity)
                self._flash("Got a silver key!", color=(0.75, 0.75, 0.85))
            elif entity.type == 'treasure':
                self.treasure_count += 1
                to_remove.append(entity)
                self._flash(f"Treasure! ({self.treasure_count})", color=(1.0, 0.85, 0.0))
            elif entity.type == 'stairs_down':
                self._load_next_level()
                return
            elif entity.type == 'stairs_up':
                self._load_prev_level()
                return

        for entity in to_remove:
            self.entities.remove(entity)

    # --- Death / Restart ------------------------------------------------------

    def _handle_death(self):
        """Game over state — effects still animate."""
        self._clean_flashes()
        # Keep effects animating
        dt = 0.016
        for effect in self.combat.hit_effects:
            effect.update(dt)
        self.combat.hit_effects = [e for e in self.combat.hit_effects if e.alive]
        for effect in self.combat.death_effects:
            effect.update(dt)
        self.combat.death_effects = [e for e in self.combat.death_effects if e.alive]

    def _restart_level(self):
        """Restart current level, keep inventory."""
        if self.level:
            self._apply_level(self.level)
            self.combat.player_hp.hp = self.combat.player_hp.max_hp
            self.combat.game_over = False
            self.flash_messages.clear()
            self._flash("Try again...", duration=2.0, color=(1.0, 0.6, 0.2))

    # --- Key Events -----------------------------------------------------------

    def keyPressEvent(self, event):
        self.keys_pressed.add(event.key())

        if event.key() == Qt.Key.Key_C:
            names = list(self.COLOR_SCHEMES.keys())
            idx = (names.index(self.color_name) + 1) % len(names)
            self.color_name = names[idx]
            self.color = QColor(self.COLOR_SCHEMES[self.color_name])

        if event.key() == Qt.Key.Key_Space:
            if not self.game_complete:
                self._try_open_door()

        # Spellcast
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_F):
            if not self.game_complete and not self.combat.game_over:
                self.combat.cast_spell(self.cam_x, self.cam_z, self.cam_angle)

        # Restart after death
        if event.key() == Qt.Key.Key_R:
            if self.combat.game_over:
                self._restart_level()

        if event.key() in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.close()

    def keyReleaseEvent(self, event):
        self.keys_pressed.discard(event.key())

    # --- Monster Color --------------------------------------------------------

    # Contrast colors for enemies so they stand out from walls
    MONSTER_COLOR_BY_SCHEME = {
        'amber': (0.0, 0.75, 1.0),     # Blue when walls are amber
        'green': (1.0, 0.69, 0.0),     # Amber when walls are green
        'blue':  (1.0, 0.69, 0.0),     # Amber when walls are blue
        'white': (1.0, 0.69, 0.0),     # Amber when walls are white
    }

    def _get_monster_color(self):
        """Return (r, g, b) tuple for enemy rendering based on current scheme."""
        return self.MONSTER_COLOR_BY_SCHEME.get(self.color_name, (1.0, 0.69, 0.0))

    def _get_monster_qcolor(self):
        """Return QColor for enemy minimap markers."""
        r, g, b = self._get_monster_color()
        return QColor(int(r * 255), int(g * 255), int(b * 255))

    # --- Rendering ------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect):
        self.walls_rendered = 0
        painter.beginNativePainting()

        vp = self.viewport()
        ratio = self.devicePixelRatio()
        vp_width = int(vp.width() * ratio)
        vp_height = int(vp.height() * ratio)

        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClearDepth(1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LESS)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glViewport(0, 0, vp_width, vp_height)
        gluPerspective(75.0, vp_width / max(vp_height, 1), 1.0, 1000.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glRotatef(self.cam_angle, 0, 1, 0)
        glTranslatef(-self.cam_x, -self.cam_y, -self.cam_z)

        r = self.color.redF()
        g = self.color.greenF()
        b = self.color.blueF()
        fill_r = r * self.fill_intensity
        fill_g = g * self.fill_intensity
        fill_b = b * self.fill_intensity

        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(1.0, 1.0)
        glLineWidth(2.0)

        for wall in self.bsp_tree.traverse_front_to_back(self.cam_x, self.cam_z):
            self._render_wall_3d(wall, r, g, b, fill_r, fill_g, fill_b)
            self.walls_rendered += 1

        glDisable(GL_POLYGON_OFFSET_FILL)

        # Entities
        self._draw_entities(r, g, b)

        # Projectiles
        self._draw_projectiles()

        # Hit/death effects
        self._draw_effects()

        glLineWidth(1.0)

        # Staff overlay
        self._draw_staff()

        # Damage flash (red border overlay)
        if self.combat.player_hp.damage_flash > 0:
            self._draw_damage_flash()

        glDisable(GL_DEPTH_TEST)
        painter.endNativePainting()

        self._draw_hud(painter)

    def _render_wall_3d(self, wall: Wall, r, g, b, fill_r, fill_g, fill_b):
        quads_with_normals = wall.get_all_quads_with_normals()

        for quad, normal in quads_with_normals:
            cx = sum(v[0] for v in quad) / 4
            cz = sum(v[2] for v in quad) / 4
            to_cam_x = self.cam_x - cx
            to_cam_z = self.cam_z - cz
            dot = to_cam_x * normal[0] + to_cam_z * normal[2]
            if dot < 0:
                continue

            glColor3f(fill_r, fill_g, fill_b)
            glBegin(GL_POLYGON)
            for wx, wy, wz in quad:
                glVertex3f(wx, wy, wz)
            glEnd()

            glColor3f(r, g, b)
            glBegin(GL_LINE_LOOP)
            for wx, wy, wz in quad:
                glVertex3f(wx, wy, wz)
            glEnd()

    # --- Entity Rendering -----------------------------------------------------

    def _draw_entities(self, r, g, b):
        glLineWidth(2.0)

        for entity in self.entities:
            if entity.type in ('door', 'door_locked'):
                if self.door_open_states.get((entity.gx, entity.gz), False):
                    continue
                self._draw_door_entity(entity, r, g, b)
                continue

            model = ENTITY_MODELS.get(entity.type)
            if not model:
                continue

            # Use smooth world position for enemies, grid position for everything else
            enemy_info = None
            if entity.type in ('skeleton', 'ghost'):
                enemy_info = self.combat.get_enemy_for_entity(entity)

            if enemy_info:
                wx, wz = enemy_info.wx, enemy_info.wz
            else:
                wx, wz = self.dungeon.grid_to_world(entity.gx, entity.gz)

            ec = ENTITY_COLORS.get(entity.type)
            if ec:
                er, eg, eb = ec
            elif entity.type in ('skeleton', 'ghost'):
                er, eg, eb = self._get_monster_color()
            else:
                er, eg, eb = r, g, b

            # Billboard: face the camera
            dx = self.cam_x - wx
            dz = self.cam_z - wz
            angle = math.degrees(math.atan2(dx, -dz))

            bob_y = 0.0
            if model['bob_speed'] > 0:
                bob_y = math.sin(self.entity_timer * model['bob_speed']) * model['bob_amount']

            scale = model['scale']

            entity_y_offset = -40.0  # Lower entities toward floor level

            glPushMatrix()
            glTranslatef(wx, bob_y + entity_y_offset, wz)
            glRotatef(angle, 0, 1, 0)

            glColor3f(er, eg, eb)
            glBegin(GL_LINES)
            for (x1, y1, z1), (x2, y2, z2) in model['lines']:
                glVertex3f(x1 * scale, y1 * scale, z1 * scale)
                glVertex3f(x2 * scale, y2 * scale, z2 * scale)
            glEnd()

            glPopMatrix()

    def _draw_door_entity(self, entity, r, g, b):
        wx, wz = self.dungeon.grid_to_world(entity.gx, entity.gz)
        half = CELL_SIZE / 2

        ec = ENTITY_COLORS.get(entity.type)
        if ec:
            er, eg, eb = ec
        else:
            er, eg, eb = r, g, b

        # Darker fill color (25% of wireframe brightness)
        fr, fg, fb = er * 0.25, eg * 0.25, eb * 0.25

        gx, gz = entity.gx, entity.gz
        ew_solid = (self.dungeon.is_solid(gx - 1, gz) or self.dungeon.is_solid(gx + 1, gz))

        floor_y = 0.0
        ceil_y = -self.dungeon.wall_height
        mid_y = ceil_y / 2

        if ew_solid:
            # Door spans E-W (fixed Z, varying X)
            z = wz
            x1, x2 = wx - half + 4, wx + half - 4
            # Define quad corners for the door panel
            bl = (x1, floor_y, z)
            br = (x2, floor_y, z)
            tr = (x2, ceil_y, z)
            tl = (x1, ceil_y, z)
        else:
            # Door spans N-S (fixed X, varying Z)
            x = wx
            z1, z2 = wz - half + 4, wz + half - 4
            bl = (x, floor_y, z1)
            br = (x, floor_y, z2)
            tr = (x, ceil_y, z2)
            tl = (x, ceil_y, z1)

        # --- Filled quad (opaque door panel) ---
        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(1.0, 1.0)
        glColor3f(fr, fg, fb)
        glBegin(GL_QUADS)
        glVertex3f(*bl); glVertex3f(*br); glVertex3f(*tr); glVertex3f(*tl)
        glEnd()
        glDisable(GL_POLYGON_OFFSET_FILL)

        # --- Wireframe outline + detail lines ---
        glColor3f(er, eg, eb)
        glLineWidth(2.5)

        # Door frame outline
        glBegin(GL_LINE_LOOP)
        glVertex3f(*bl); glVertex3f(*br); glVertex3f(*tr); glVertex3f(*tl)
        glEnd()

        # Detail lines
        if ew_solid:
            z = wz
            x1, x2 = wx - half + 4, wx + half - 4
            glBegin(GL_LINES)
            glVertex3f(x1, mid_y, z); glVertex3f(x2, mid_y, z)
            if entity.type == 'door_locked':
                glVertex3f(x1, ceil_y, z); glVertex3f(x2, mid_y, z)
                glVertex3f(x2, ceil_y, z); glVertex3f(x1, mid_y, z)
            else:
                glVertex3f(x1, mid_y * 0.6, z); glVertex3f(x2, mid_y * 0.6, z)
                glVertex3f(x1, mid_y * 0.3, z); glVertex3f(x2, mid_y * 0.3, z)
            glEnd()
        else:
            x = wx
            z1, z2 = wz - half + 4, wz + half - 4
            glBegin(GL_LINES)
            glVertex3f(x, mid_y, z1); glVertex3f(x, mid_y, z2)
            if entity.type == 'door_locked':
                glVertex3f(x, ceil_y, z1); glVertex3f(x, mid_y, z2)
                glVertex3f(x, ceil_y, z2); glVertex3f(x, mid_y, z1)
            else:
                glVertex3f(x, mid_y * 0.6, z1); glVertex3f(x, mid_y * 0.6, z2)
                glVertex3f(x, mid_y * 0.3, z1); glVertex3f(x, mid_y * 0.3, z2)
            glEnd()

        glLineWidth(2.0)

    # --- Combat Rendering -----------------------------------------------------

    def _draw_projectiles(self):
        """Render spell projectiles in 3D world space."""
        if not self.combat.projectiles:
            return

        glLineWidth(2.0)
        model = PROJECTILE_MODEL
        cr, cg, cb = model['color']
        scale = model['scale']

        for proj in self.combat.projectiles:
            # Spin based on lifetime
            spin = (proj.created - time.time()) * 720  # 2 full spins per sec

            glPushMatrix()
            glTranslatef(proj.wx, -25.0, proj.wz)  # Mid-height in corridor
            glRotatef(self.cam_angle, 0, 1, 0)      # Billboard
            glRotatef(spin, 0, 0, 1)                 # Spin on facing axis

            # Glow pulse
            pulse = 0.7 + 0.3 * math.sin(time.time() * 15.0)
            glColor3f(cr * pulse, cg * pulse, cb * pulse)
            glBegin(GL_LINES)
            for (x1, y1, z1), (x2, y2, z2) in model['lines']:
                glVertex3f(x1 * scale, y1 * scale, z1 * scale)
                glVertex3f(x2 * scale, y2 * scale, z2 * scale)
            glEnd()

            glPopMatrix()

    def _draw_effects(self):
        """Render hit bursts and death collapse effects."""
        # Hit effects — expanding wireframe ring
        for effect in self.combat.hit_effects:
            r_size = effect.radius
            alpha = effect.alpha
            glPushMatrix()
            glTranslatef(effect.wx, -25.0, effect.wz)
            glRotatef(self.cam_angle, 0, 1, 0)

            glColor3f(0.6 * alpha, 0.9 * alpha, 1.0 * alpha)
            glLineWidth(2.0)
            # Expanding diamond
            glBegin(GL_LINE_LOOP)
            glVertex3f(0, r_size, 0)
            glVertex3f(r_size, 0, 0)
            glVertex3f(0, -r_size, 0)
            glVertex3f(-r_size, 0, 0)
            glEnd()
            # Cross
            glBegin(GL_LINES)
            glVertex3f(-r_size * 0.7, r_size * 0.7, 0)
            glVertex3f(r_size * 0.7, -r_size * 0.7, 0)
            glVertex3f(r_size * 0.7, r_size * 0.7, 0)
            glVertex3f(-r_size * 0.7, -r_size * 0.7, 0)
            glEnd()

            glPopMatrix()

        # Death effects — collapsing model
        for effect in self.combat.death_effects:
            collapse = effect.collapse_factor
            alpha = effect.alpha

            model = ENTITY_MODELS.get(effect.entity_type)
            if model is None:
                continue

            glPushMatrix()
            glTranslatef(effect.wx, -40.0, effect.wz)
            glRotatef(self.cam_angle, 0, 1, 0)

            mr, mg, mb = self._get_monster_color()
            glColor3f(mr * alpha, mg * alpha, mb * alpha)
            glLineWidth(1.5)
            scale = model['scale']
            glBegin(GL_LINES)
            for (x1, y1, z1), (x2, y2, z2) in model['lines']:
                # Collapse Y toward ground, spread X outward
                spread = 1.0 + (1.0 - collapse) * 0.5
                glVertex3f(x1 * scale * spread, y1 * scale * collapse,
                           z1 * scale)
                glVertex3f(x2 * scale * spread, y2 * scale * collapse,
                           z2 * scale)
            glEnd()

            glPopMatrix()

    def _draw_damage_flash(self):
        """Red border flash when player takes damage."""
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        from OpenGL.GLU import gluOrtho2D
        gluOrtho2D(0, self.base_width, self.base_height, 0)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)

        alpha = min(1.0, self.combat.player_hp.damage_flash / 0.2)
        border = 12

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1.0, 0.0, 0.0, alpha * 0.6)
        w, h = self.base_width, self.base_height

        # Top border
        glBegin(GL_QUADS)
        glVertex3f(0, 0, 0); glVertex3f(w, 0, 0)
        glVertex3f(w, border, 0); glVertex3f(0, border, 0)
        glEnd()
        # Bottom border
        glBegin(GL_QUADS)
        glVertex3f(0, h - border, 0); glVertex3f(w, h - border, 0)
        glVertex3f(w, h, 0); glVertex3f(0, h, 0)
        glEnd()
        # Left border
        glBegin(GL_QUADS)
        glVertex3f(0, 0, 0); glVertex3f(border, 0, 0)
        glVertex3f(border, h, 0); glVertex3f(0, h, 0)
        glEnd()
        # Right border
        glBegin(GL_QUADS)
        glVertex3f(w - border, 0, 0); glVertex3f(w, 0, 0)
        glVertex3f(w, h, 0); glVertex3f(w - border, h, 0)
        glEnd()

        glDisable(GL_BLEND)
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    # --- Staff Rendering ------------------------------------------------------

    def _draw_staff(self):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        from OpenGL.GLU import gluOrtho2D
        # Use base dimensions so staff scales proportionally with window
        gluOrtho2D(0, self.base_width, self.base_height, 0)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)

        cx = self.base_width // 2 + 80
        base_y = self.base_height + 40

        if self.is_moving:
            bob_x = math.sin(self.bob_timer) * 5
            bob_y = math.sin(self.bob_timer * 2) * 6
        else:
            bob_x = math.sin(self.bob_timer) * 2
            bob_y = math.sin(self.bob_timer * 0.7) * 2

        # Cast thrust animation — staff lunges forward (up on screen)
        cast_progress = self.combat.staff.cast_progress
        if cast_progress > 0:
            # Quick thrust up then return
            thrust = math.sin(cast_progress * math.pi) * 60
            base_y -= thrust
            bob_x *= (1.0 - cast_progress * 0.8)  # Dampen bob during cast
            bob_y *= (1.0 - cast_progress * 0.8)

        cx += bob_x
        base_y += bob_y

        # Staff colors
        wood_r, wood_g, wood_b = 0.55, 0.35, 0.17          # Brown wireframe
        wood_fr, wood_fg, wood_fb = 0.22, 0.13, 0.06       # Dark brown fill
        gold_r, gold_g, gold_b = 1.0, 0.85, 0.0            # Gold wireframe
        gold_fr, gold_fg, gold_fb = 0.4, 0.34, 0.0         # Dark gold fill
        crystal_r, crystal_g, crystal_b = 0.6, 0.9, 1.0    # Ice blue crystal wire
        crystal_fr, crystal_fg, crystal_fb = 0.15, 0.25, 0.35  # Crystal fill

        shaft_length = 280
        shaft_width = 8
        head_size = 35
        crystal_size = 20
        top_y = base_y - shaft_length
        head_y = top_y + head_size

        sw = shaft_width / 2

        # === SHAFT (filled brown rectangle) ===
        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(1.0, 1.0)
        glColor3f(wood_fr, wood_fg, wood_fb)
        glBegin(GL_QUADS)
        glVertex3f(cx - sw, base_y, 0)
        glVertex3f(cx + sw, base_y, 0)
        glVertex3f(cx + sw, head_y, 0)
        glVertex3f(cx - sw, head_y, 0)
        glEnd()
        glDisable(GL_POLYGON_OFFSET_FILL)

        # Shaft outline
        glLineWidth(2.0)
        glColor3f(wood_r, wood_g, wood_b)
        glBegin(GL_LINE_LOOP)
        glVertex3f(cx - sw, base_y, 0)
        glVertex3f(cx + sw, base_y, 0)
        glVertex3f(cx + sw, head_y, 0)
        glVertex3f(cx - sw, head_y, 0)
        glEnd()

        # Wood grain lines (subtle vertical detail)
        glLineWidth(1.0)
        glColor3f(wood_r * 0.6, wood_g * 0.6, wood_b * 0.6)
        glBegin(GL_LINES)
        glVertex3f(cx - sw + 2, base_y, 0)
        glVertex3f(cx - sw + 2, head_y, 0)
        glVertex3f(cx + sw - 2, base_y, 0)
        glVertex3f(cx + sw - 2, head_y, 0)
        glEnd()

        # === GRIP WRAPPINGS (gold bands) ===
        grip_h = 6
        glLineWidth(2.0)
        for i in range(3):
            gy = base_y - 50 - i * 40
            # Fill
            glEnable(GL_POLYGON_OFFSET_FILL)
            glPolygonOffset(1.0, 1.0)
            glColor3f(gold_fr, gold_fg, gold_fb)
            glBegin(GL_QUADS)
            glVertex3f(cx - sw - 2, gy, 0)
            glVertex3f(cx + sw + 2, gy, 0)
            glVertex3f(cx + sw + 2, gy - grip_h, 0)
            glVertex3f(cx - sw - 2, gy - grip_h, 0)
            glEnd()
            glDisable(GL_POLYGON_OFFSET_FILL)
            # Outline
            glColor3f(gold_r, gold_g, gold_b)
            glBegin(GL_LINE_LOOP)
            glVertex3f(cx - sw - 2, gy, 0)
            glVertex3f(cx + sw + 2, gy, 0)
            glVertex3f(cx + sw + 2, gy - grip_h, 0)
            glVertex3f(cx - sw - 2, gy - grip_h, 0)
            glEnd()
            # Cross-hatch detail on grip
            glBegin(GL_LINES)
            glVertex3f(cx - sw, gy, 0)
            glVertex3f(cx + sw, gy - grip_h, 0)
            glVertex3f(cx + sw, gy, 0)
            glVertex3f(cx - sw, gy - grip_h, 0)
            glEnd()

        # === HEAD (gold triangle cradle) ===
        # Outer triangle
        hx1 = cx - head_size / 2
        hx2 = cx + head_size / 2
        hpeak = top_y - 10

        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(1.0, 1.0)
        glColor3f(gold_fr, gold_fg, gold_fb)
        glBegin(GL_POLYGON)
        glVertex3f(cx, hpeak, 0)
        glVertex3f(hx1, head_y, 0)
        glVertex3f(hx2, head_y, 0)
        glEnd()
        glDisable(GL_POLYGON_OFFSET_FILL)

        glLineWidth(2.5)
        glColor3f(gold_r, gold_g, gold_b)
        glBegin(GL_LINE_LOOP)
        glVertex3f(cx, hpeak, 0)
        glVertex3f(hx1, head_y, 0)
        glVertex3f(hx2, head_y, 0)
        glEnd()

        # Inner triangle detail
        ix1 = cx - head_size / 3
        ix2 = cx + head_size / 3
        ipeak = top_y + 5

        glBegin(GL_LINE_LOOP)
        glVertex3f(cx, ipeak, 0)
        glVertex3f(ix1, head_y - 8, 0)
        glVertex3f(ix2, head_y - 8, 0)
        glEnd()

        # Filigree lines on head
        glLineWidth(1.5)
        glBegin(GL_LINES)
        # Left side accent
        glVertex3f(hx1 + 4, head_y - 3, 0)
        glVertex3f(cx - 2, hpeak + 10, 0)
        # Right side accent
        glVertex3f(hx2 - 4, head_y - 3, 0)
        glVertex3f(cx + 2, hpeak + 10, 0)
        glEnd()

        # === CRYSTAL (filled diamond with glow) ===
        crystal_y = top_y + head_size / 2 - 5
        ct = crystal_y - crystal_size / 2
        cb = crystal_y + crystal_size / 2
        cl = cx - crystal_size / 3
        cr_x = cx + crystal_size / 3

        # Crystal glow pulse
        pulse = 0.7 + 0.3 * math.sin(self.bob_timer * 3.0)

        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(1.0, 1.0)
        glColor3f(crystal_fr * pulse, crystal_fg * pulse, crystal_fb * pulse)
        glBegin(GL_QUADS)
        glVertex3f(cx, ct, 0)
        glVertex3f(cr_x, crystal_y, 0)
        glVertex3f(cx, cb, 0)
        glVertex3f(cl, crystal_y, 0)
        glEnd()
        glDisable(GL_POLYGON_OFFSET_FILL)

        glLineWidth(2.5)
        glColor3f(crystal_r * pulse, crystal_g * pulse, crystal_b * pulse)
        glBegin(GL_LINE_LOOP)
        glVertex3f(cx, ct, 0)
        glVertex3f(cr_x, crystal_y, 0)
        glVertex3f(cx, cb, 0)
        glVertex3f(cl, crystal_y, 0)
        glEnd()

        # Crystal inner lines
        glLineWidth(1.5)
        glBegin(GL_LINES)
        glVertex3f(cx, ct + 3, 0)
        glVertex3f(cx, cb - 3, 0)
        glVertex3f(cl + 3, crystal_y, 0)
        glVertex3f(cr_x - 3, crystal_y, 0)
        glEnd()

        glLineWidth(1.0)
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    # --- HUD ------------------------------------------------------------------

    def _draw_hud(self, painter: QPainter):
        s = self.hud_scale
        margin = int(10 * s)

        # Debug info (top-left)
        font = painter.font()
        font.setPointSize(max(7, int(10 * s)))
        painter.setFont(font)
        painter.setPen(QPen(self.color))
        gx, gz = self.dungeon.world_to_grid(self.cam_x, self.cam_z)

        line_h = int(20 * s)
        painter.drawText(margin, line_h, f"BSP GL3D - {self.color_name.title()}")
        painter.drawText(margin, line_h * 2, f"Pos: ({gx}, {gz}) Angle: {self.cam_angle:.0f}")
        painter.drawText(margin, line_h * 3, f"Walls rendered: {self.walls_rendered}")

        # HP Bar (bottom-left, above inventory)
        hp = self.combat.player_hp
        bar_w = int(150 * s)
        bar_h = int(12 * s)
        bar_x = margin
        bar_y = self.win_height - int(70 * s)

        # Bar background
        painter.setPen(QPen(QColor(80, 80, 80)))
        painter.setBrush(QBrush(QColor(40, 40, 40)))
        painter.drawRect(bar_x, bar_y, bar_w, bar_h)

        # Bar fill
        fill_w = int(bar_w * hp.hp_fraction)
        if hp.hp_fraction > 0.5:
            bar_color = QColor(0, 200, 0)
        elif hp.hp_fraction > 0.25:
            bar_color = QColor(200, 200, 0)
        else:
            bar_color = QColor(200, 0, 0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bar_color))
        if fill_w > 0:
            painter.drawRect(bar_x, bar_y, fill_w, bar_h)

        # HP text
        painter.setPen(QPen(QColor(255, 255, 255)))
        font = painter.font()
        font.setPointSize(max(6, int(8 * s)))
        painter.setFont(font)
        hp_text = f"HP: {hp.hp}/{hp.max_hp}"
        painter.drawText(bar_x + int(4 * s), bar_y + bar_h - int(2 * s), hp_text)

        # Reset brush
        painter.setBrush(QBrush(Qt.GlobalColor.transparent))

        # Inventory (bottom-left)
        inv_y = self.win_height - int(30 * s)
        font.setPointSize(max(7, int(10 * s)))
        painter.setFont(font)
        painter.setPen(QPen(self.color))
        inv_parts = []
        if self.inventory_keys > 0:
            inv_parts.append(f"Keys: {self.inventory_keys}")
        if self.inventory_silver_keys > 0:
            inv_parts.append(f"Silver Keys: {self.inventory_silver_keys}")
        if self.treasure_count > 0:
            inv_parts.append(f"Treasure: {self.treasure_count}")
        if inv_parts:
            painter.drawText(margin, inv_y, "  |  ".join(inv_parts))

        # Controls hint
        painter.setPen(QPen(QColor(self.color.red() // 2, self.color.green() // 2, self.color.blue() // 2)))
        painter.drawText(margin, inv_y + int(18 * s),
                         "WASD move | SPACE door | F cast | C color")

        # Flash messages (centered)
        if self.flash_messages:
            self._clean_flashes()
            font = painter.font()
            font.setPointSize(max(9, int(14 * s)))
            font.setBold(True)
            painter.setFont(font)

            y = self.win_height // 3
            for msg in self.flash_messages:
                cr, cg, cb = msg.color
                remaining = msg.expire - time.time()
                alpha = min(1.0, remaining / 0.5) if remaining < 0.5 else 1.0
                painter.setPen(QPen(QColor(int(cr * 255), int(cg * 255), int(cb * 255), int(alpha * 255))))
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(msg.text)
                painter.drawText((self.win_width - tw) // 2, y, msg.text)
                y += int(28 * s)

            font.setPointSize(max(7, int(10 * s)))
            font.setBold(False)
            painter.setFont(font)

        # Game complete
        if self.game_complete:
            painter.setPen(QPen(QColor(255, 200, 0)))
            font = painter.font()
            font.setPointSize(max(14, int(28 * s)))
            font.setBold(True)
            painter.setFont(font)
            text = "ESCAPED!"
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(text)
            painter.drawText((self.win_width - tw) // 2, self.win_height // 4, text)
            font.setPointSize(max(8, int(12 * s)))
            painter.setFont(font)

        self._draw_minimap(painter)

    def _draw_minimap(self, painter: QPainter):
        s = self.hud_scale
        map_size = int(120 * s)
        cell_size = map_size // max(self.dungeon.width, self.dungeon.height)
        if cell_size < 1:
            cell_size = 1
        margin = int(10 * s)
        offset_x = self.win_width - map_size - margin
        offset_y = margin

        dim_color = QColor(self.color)
        dim_color.setAlpha(60)

        for gz in range(self.dungeon.height):
            for gx in range(self.dungeon.width):
                cell = self.dungeon.get_cell(gx, gz)
                x = offset_x + gx * cell_size
                y = offset_y + gz * cell_size

                if cell == CellType.DOOR:
                    door_color = QColor(self.color)
                    door_color.setAlpha(140)
                    painter.setPen(QPen(door_color))
                    painter.drawRect(x, y, cell_size, cell_size)
                elif self.dungeon.is_walkable(gx, gz):
                    painter.setPen(QPen(dim_color))
                    painter.drawRect(x, y, cell_size, cell_size)

        # Entity markers
        mk = max(1, int(2 * s))  # marker half-size
        pen_w = max(1, int(2 * s))
        for entity in self.entities:
            if entity.type in ('door', 'door_locked') and self.door_open_states.get((entity.gx, entity.gz)):
                continue
            x = offset_x + entity.gx * cell_size + cell_size // 2
            y = offset_y + entity.gz * cell_size + cell_size // 2
            ec = ENTITY_COLORS.get(entity.type)
            if ec:
                er, eg, eb = ec
                painter.setPen(QPen(QColor(int(er * 255), int(eg * 255), int(eb * 255)), pen_w))
            elif entity.type in ('skeleton', 'ghost'):
                painter.setPen(QPen(self._get_monster_qcolor(), pen_w))
            else:
                painter.setPen(QPen(self.color, pen_w))

            if entity.type in ('key', 'key_silver'):
                painter.drawRect(x - mk, y - mk, mk * 2 + 1, mk * 2 + 1)
            elif entity.type == 'treasure':
                painter.drawRect(x - mk, y - mk, mk * 2 + 1, mk * 2 + 1)
            elif entity.type in ('skeleton', 'ghost'):
                painter.drawEllipse(QPoint(x, y), mk, mk)
            elif entity.type in ('stairs_up', 'stairs_down'):
                painter.drawLine(x - mk, y, x + mk, y)
                painter.drawLine(x, y - mk, x, y + mk)
            elif entity.type == 'door_locked':
                painter.drawLine(x - mk, y - mk, x + mk, y + mk)
                painter.drawLine(x + mk, y - mk, x - mk, y + mk)

        # Player
        pgx, pgz = self.dungeon.world_to_grid(self.cam_x, self.cam_z)
        px = offset_x + pgx * cell_size + cell_size // 2
        py = offset_y + pgz * cell_size + cell_size // 2
        player_r = max(2, int(3 * s))
        painter.setPen(QPen(self.color, pen_w))
        painter.drawEllipse(QPoint(px, py), player_r, player_r)
        rad = math.radians(self.cam_angle)
        heading_len = int(8 * s)
        dx = math.sin(rad) * heading_len
        dy = -math.cos(rad) * heading_len
        painter.drawLine(px, py, int(px + dx), int(py + dy))


# --- Main ---------------------------------------------------------------------

def main():
    import sys
    from pathlib import Path
    from PyQt6.QtWidgets import QApplication

    print("=" * 50)
    print("BENEATH THE CASTLE OF BANE")
    print("BSP Dungeon Engine - v0.6.0")
    print("=" * 50)

    app = QApplication(sys.argv)
    renderer = GL3DDungeonRenderer(800, 600)

    if len(sys.argv) > 1:
        level_path = sys.argv[1]
        if Path(level_path).exists():
            renderer.load_level_file(level_path)
        else:
            print(f"Level file not found: {level_path}")
            renderer.load_test_dungeon()
    else:
        default_level = Path(__file__).parent / "levels" / "level1.level"
        if default_level.exists():
            renderer.load_level_file(str(default_level))
        else:
            print("No level file found, loading test dungeon...")
            renderer.load_test_dungeon()

    renderer.show()

    print("\nControls:")
    print("  WASD / Arrows: Move")
    print("  Space: Open door")
    print("  F / Ctrl: Cast spell")
    print("  C: Cycle colors")
    print("  R: Restart level (after death)")
    print("  Q / Esc: Quit")
    print()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()