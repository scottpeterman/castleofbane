"""
BSP Dungeon Renderer - Full OpenGL 3D
--------------------------------------
Beneath the Castle of Bane - v0.5.0

New in v0.5.0:
    - Doors: Space to open, visual rendering
    - Locked doors: Require a key to open
    - Keys: Walk over to collect (gold/silver)
    - Stairs: Walk onto to transition levels
    - Entity rendering: Wireframe keys, doors, stairs in world
    - Inventory HUD and flash messages
    - Level complete / game complete states
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
    GL_LESS, GL_POLYGON, GL_LINE_LOOP, GL_LINES, GL_LINE_STRIP,
    GL_PROJECTION, GL_MODELVIEW,
    GL_POLYGON_OFFSET_FILL, glPolygonOffset,
    GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, glBlendFunc
)
from OpenGL.GLU import gluPerspective

from wireframe_engine.dungeon import DungeonMap, Wall, WallFace, CellType, create_test_dungeon, CELL_SIZE
from wireframe_engine.bsp import BSPTree, build_bsp_from_dungeon
from wireframe_engine.level import Level, Entity, load_level, parse_level, create_test_levels


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
        # === SKULL (large round head at TOP) ===
        ((-6, 42, 0), (-3, 45, 0)),
        ((-3, 45, 0), (3, 45, 0)),
        ((3, 45, 0), (6, 42, 0)),
        ((6, 42, 0), (7, 38, 0)),
        ((7, 38, 0), (5, 35, 0)),
        ((5, 35, 0), (2, 34, 0)),
        ((2, 34, 0), (-2, 34, 0)),
        ((-2, 34, 0), (-5, 35, 0)),
        ((-5, 35, 0), (-7, 38, 0)),
        ((-7, 38, 0), (-6, 42, 0)),
        # Eyes
        ((-4, 41, 0), (-2, 41, 0)),
        ((-2, 41, 0), (-2, 39, 0)),
        ((-2, 39, 0), (-4, 39, 0)),
        ((-4, 39, 0), (-4, 41, 0)),
        ((2, 41, 0), (4, 41, 0)),
        ((4, 41, 0), (4, 39, 0)),
        ((4, 39, 0), (2, 39, 0)),
        ((2, 39, 0), (2, 41, 0)),
        # Nose
        ((0, 39, 0), (-1, 37, 0)),
        ((0, 39, 0), (1, 37, 0)),
        # Teeth
        ((-3, 35, 0), (-1, 35, 0)),
        ((1, 35, 0), (3, 35, 0)),
        # === NECK ===
        ((0, 34, 0), (0, 31, 0)),
        # === SHOULDERS ===
        ((-10, 31, 0), (10, 31, 0)),
        # === SPINE ===
        ((0, 31, 0), (0, 16, 0)),
        # === RIBS ===
        ((-8, 29, 0), (8, 29, 0)),
        ((-9, 26, 0), (9, 26, 0)),
        ((-9, 23, 0), (9, 23, 0)),
        ((-8, 20, 0), (8, 20, 0)),
        # === PELVIS ===
        ((-6, 16, 0), (6, 16, 0)),
        ((-6, 16, 0), (-3, 14, 0)),
        ((6, 16, 0), (3, 14, 0)),
        # === LEGS (feet at y=0) ===
        ((-5, 16, 0), (-7, 0, 0)),
        ((5, 16, 0), (7, 0, 0)),
        # === ARMS ===
        ((-10, 31, 0), (-13, 20, 0)),
        ((-13, 20, 0), (-11, 12, 0)),
        ((10, 31, 0), (13, 20, 0)),
        ((13, 20, 0), (11, 12, 0)),
    ],
    'scale': 1.0,
    'bob_speed': 0.0,
    'bob_amount': 0.0,
}

GHOST_MODEL = {
    'lines': [
        # === HEAD (top) ===
        ((-8, 42, 0), (-5, 46, 0)),
        ((-5, 46, 0), (5, 46, 0)),
        ((5, 46, 0), (8, 42, 0)),
        # === BODY SIDES ===
        ((8, 42, 0), (10, 30, 0)),
        ((10, 30, 0), (9, 18, 0)),
        ((-8, 42, 0), (-10, 30, 0)),
        ((-10, 30, 0), (-9, 18, 0)),
        # === WAVY BOTTOM ===
        ((-9, 18, 0), (-6, 14, 0)),
        ((-6, 14, 0), (-3, 18, 0)),
        ((-3, 18, 0), (0, 14, 0)),
        ((0, 14, 0), (3, 18, 0)),
        ((3, 18, 0), (6, 14, 0)),
        ((6, 14, 0), (9, 18, 0)),
        # === EYES ===
        ((-5, 40, 0), (-3, 38, 0)),
        ((-3, 38, 0), (-5, 36, 0)),
        ((-5, 36, 0), (-5, 40, 0)),
        ((3, 40, 0), (5, 38, 0)),
        ((5, 38, 0), (3, 36, 0)),
        ((3, 36, 0), (3, 40, 0)),
        # === MOUTH ===
        ((-2, 33, 0), (2, 33, 0)),
        ((2, 33, 0), (2, 31, 0)),
        ((2, 31, 0), (-2, 31, 0)),
        ((-2, 31, 0), (-2, 33, 0)),
    ],
    'scale': 1.2,
    'bob_speed': 1.5,
    'bob_amount': 4.0,
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
    'door': None,
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
        self.setFixedSize(width, height)
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

        stats = self.bsp_tree.get_stats()
        print(f"  BSP: {stats['nodes']} nodes, {stats['splits']} splits, depth {stats['depth']}")
        print(f"  Entities: {len(self.entities)}")
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
        self._handle_input()
        self._check_entity_collisions()
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

        if event.key() in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.close()

    def keyReleaseEvent(self, event):
        self.keys_pressed.discard(event.key())

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
        gluPerspective(75.0, self.win_width / self.win_height, 1.0, 1000.0)

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
        glLineWidth(1.0)

        # Staff overlay
        self._draw_staff()

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

            wx, wz = self.dungeon.grid_to_world(entity.gx, entity.gz)

            ec = ENTITY_COLORS.get(entity.type)
            if ec:
                er, eg, eb = ec
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

        gx, gz = entity.gx, entity.gz
        ew_solid = (self.dungeon.is_solid(gx - 1, gz) or self.dungeon.is_solid(gx + 1, gz))

        floor_y = 0.0
        ceil_y = -self.dungeon.wall_height
        mid_y = ceil_y / 2

        glColor3f(er, eg, eb)
        glLineWidth(2.5)

        if ew_solid:
            # Walls east/west = corridor runs N-S, door spans E-W (fixed Z, varying X)
            z = wz
            x1, x2 = wx - half + 4, wx + half - 4
            glBegin(GL_LINES)
            glVertex3f(x1, floor_y, z); glVertex3f(x1, ceil_y, z)
            glVertex3f(x2, floor_y, z); glVertex3f(x2, ceil_y, z)
            glVertex3f(x1, ceil_y, z); glVertex3f(x2, ceil_y, z)
            glVertex3f(x1, mid_y, z); glVertex3f(x2, mid_y, z)
            if entity.type == 'door_locked':
                glVertex3f(x1, ceil_y, z); glVertex3f(x2, mid_y, z)
                glVertex3f(x2, ceil_y, z); glVertex3f(x1, mid_y, z)
            else:
                glVertex3f(x1, mid_y * 0.6, z); glVertex3f(x2, mid_y * 0.6, z)
                glVertex3f(x1, mid_y * 0.3, z); glVertex3f(x2, mid_y * 0.3, z)
            glEnd()
        else:
            # Walls north/south = corridor runs E-W, door spans N-S (fixed X, varying Z)
            x = wx
            z1, z2 = wz - half + 4, wz + half - 4
            glBegin(GL_LINES)
            glVertex3f(x, floor_y, z1); glVertex3f(x, ceil_y, z1)
            glVertex3f(x, floor_y, z2); glVertex3f(x, ceil_y, z2)
            glVertex3f(x, ceil_y, z1); glVertex3f(x, ceil_y, z2)
            glVertex3f(x, mid_y, z1); glVertex3f(x, mid_y, z2)
            if entity.type == 'door_locked':
                glVertex3f(x, ceil_y, z1); glVertex3f(x, mid_y, z2)
                glVertex3f(x, ceil_y, z2); glVertex3f(x, mid_y, z1)
            else:
                glVertex3f(x, mid_y * 0.6, z1); glVertex3f(x, mid_y * 0.6, z2)
                glVertex3f(x, mid_y * 0.3, z1); glVertex3f(x, mid_y * 0.3, z2)
            glEnd()

        glLineWidth(2.0)

    # --- Staff Rendering ------------------------------------------------------

    def _draw_staff(self):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        from OpenGL.GLU import gluOrtho2D
        gluOrtho2D(0, self.win_width, self.win_height, 0)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)

        cx = self.win_width // 2 + 80
        base_y = self.win_height + 40

        if self.is_moving:
            bob_x = math.sin(self.bob_timer) * 5
            bob_y = math.sin(self.bob_timer * 2) * 6
        else:
            bob_x = math.sin(self.bob_timer) * 2
            bob_y = math.sin(self.bob_timer * 0.7) * 2

        cx += bob_x
        base_y += bob_y

        r = self.color.redF()
        g = self.color.greenF()
        b = self.color.blueF()

        shaft_length = 280
        shaft_width = 6
        head_size = 35
        crystal_size = 20
        top_y = base_y - shaft_length

        glLineWidth(2.5)
        glColor3f(r, g, b)

        # Shaft
        glBegin(GL_LINES)
        glVertex3f(cx - shaft_width / 2, base_y, 0)
        glVertex3f(cx - shaft_width / 2, top_y + head_size, 0)
        glVertex3f(cx + shaft_width / 2, base_y, 0)
        glVertex3f(cx + shaft_width / 2, top_y + head_size, 0)
        glEnd()

        # Grip
        glBegin(GL_LINES)
        for i in range(3):
            y = base_y - 60 - i * 40
            glVertex3f(cx - shaft_width / 2 - 4, y, 0)
            glVertex3f(cx + shaft_width / 2 + 4, y, 0)
        glEnd()

        # Head
        head_y = top_y + head_size
        glBegin(GL_LINE_LOOP)
        glVertex3f(cx, top_y - 10, 0)
        glVertex3f(cx - head_size / 2, head_y, 0)
        glVertex3f(cx + head_size / 2, head_y, 0)
        glEnd()

        glBegin(GL_LINE_LOOP)
        glVertex3f(cx, top_y + 5, 0)
        glVertex3f(cx - head_size / 3, head_y - 8, 0)
        glVertex3f(cx + head_size / 3, head_y - 8, 0)
        glEnd()

        # Crystal
        crystal_y = top_y + head_size / 2 - 5
        glBegin(GL_LINE_LOOP)
        glVertex3f(cx, crystal_y - crystal_size / 2, 0)
        glVertex3f(cx + crystal_size / 3, crystal_y, 0)
        glVertex3f(cx, crystal_y + crystal_size / 2, 0)
        glVertex3f(cx - crystal_size / 3, crystal_y, 0)
        glEnd()

        glLineWidth(1.5)
        glBegin(GL_LINES)
        glVertex3f(cx, crystal_y - crystal_size / 3, 0)
        glVertex3f(cx, crystal_y + crystal_size / 3, 0)
        glVertex3f(cx - crystal_size / 4, crystal_y, 0)
        glVertex3f(cx + crystal_size / 4, crystal_y, 0)
        glEnd()

        glLineWidth(1.0)
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    # --- HUD ------------------------------------------------------------------

    def _draw_hud(self, painter: QPainter):
        painter.setPen(QPen(self.color))
        gx, gz = self.dungeon.world_to_grid(self.cam_x, self.cam_z)

        painter.drawText(10, 20, f"BSP GL3D - {self.color_name.title()}")
        painter.drawText(10, 40, f"Pos: ({gx}, {gz}) Angle: {self.cam_angle:.0f}")
        painter.drawText(10, 60, f"Walls rendered: {self.walls_rendered}")

        # Inventory (bottom-left)
        inv_y = self.win_height - 30
        painter.setPen(QPen(self.color))
        inv_parts = []
        if self.inventory_keys > 0:
            inv_parts.append(f"Keys: {self.inventory_keys}")
        if self.inventory_silver_keys > 0:
            inv_parts.append(f"Silver Keys: {self.inventory_silver_keys}")
        if self.treasure_count > 0:
            inv_parts.append(f"Treasure: {self.treasure_count}")
        if inv_parts:
            painter.drawText(10, inv_y, "  |  ".join(inv_parts))

        # Controls hint
        painter.setPen(QPen(QColor(self.color.red() // 2, self.color.green() // 2, self.color.blue() // 2)))
        painter.drawText(10, inv_y + 18, "WASD move | SPACE open door | C color")

        # Flash messages (centered)
        if self.flash_messages:
            self._clean_flashes()
            font = painter.font()
            font.setPointSize(14)
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
                y += 28

            font.setPointSize(10)
            font.setBold(False)
            painter.setFont(font)

        # Game complete
        if self.game_complete:
            painter.setPen(QPen(QColor(255, 200, 0)))
            font = painter.font()
            font.setPointSize(28)
            font.setBold(True)
            painter.setFont(font)
            text = "ESCAPED!"
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(text)
            painter.drawText((self.win_width - tw) // 2, self.win_height // 4, text)
            font.setPointSize(12)
            painter.setFont(font)

        self._draw_minimap(painter)

    def _draw_minimap(self, painter: QPainter):
        map_size = 120
        cell_size = map_size // max(self.dungeon.width, self.dungeon.height)
        if cell_size < 1:
            cell_size = 1
        offset_x = self.win_width - map_size - 10
        offset_y = 10

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
        for entity in self.entities:
            if entity.type in ('door', 'door_locked') and self.door_open_states.get((entity.gx, entity.gz)):
                continue
            x = offset_x + entity.gx * cell_size + cell_size // 2
            y = offset_y + entity.gz * cell_size + cell_size // 2
            ec = ENTITY_COLORS.get(entity.type)
            if ec:
                er, eg, eb = ec
                painter.setPen(QPen(QColor(int(er * 255), int(eg * 255), int(eb * 255)), 2))
            else:
                painter.setPen(QPen(self.color, 2))

            if entity.type in ('key', 'key_silver'):
                painter.drawRect(x - 1, y - 1, 3, 3)
            elif entity.type == 'treasure':
                painter.drawRect(x - 1, y - 1, 3, 3)
            elif entity.type in ('skeleton', 'ghost'):
                painter.drawEllipse(QPoint(x, y), 2, 2)
            elif entity.type in ('stairs_up', 'stairs_down'):
                painter.drawLine(x - 2, y, x + 2, y)
                painter.drawLine(x, y - 2, x, y + 2)
            elif entity.type == 'door_locked':
                painter.drawLine(x - 2, y - 2, x + 2, y + 2)
                painter.drawLine(x + 2, y - 2, x - 2, y + 2)

        # Player
        pgx, pgz = self.dungeon.world_to_grid(self.cam_x, self.cam_z)
        px = offset_x + pgx * cell_size + cell_size // 2
        py = offset_y + pgz * cell_size + cell_size // 2
        painter.setPen(QPen(self.color, 2))
        painter.drawEllipse(QPoint(px, py), 3, 3)
        rad = math.radians(self.cam_angle)
        dx = math.sin(rad) * 8
        dy = -math.cos(rad) * 8
        painter.drawLine(px, py, int(px + dx), int(py + dy))


# --- Main ---------------------------------------------------------------------

def main():
    import sys
    from pathlib import Path
    from PyQt6.QtWidgets import QApplication

    print("=" * 50)
    print("BENEATH THE CASTLE OF BANE")
    print("BSP Dungeon Engine - v0.5.0")
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
    print("  C: Cycle colors")
    print("  Q / Esc: Quit")
    print()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()