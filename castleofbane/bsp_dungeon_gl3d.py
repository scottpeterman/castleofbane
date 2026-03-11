"""
BSP Dungeon Renderer - Full OpenGL 3D
--------------------------------------
Let the GPU handle projection AND depth testing.
No more fighting between software projection and hardware depth buffer.

Key differences from hybrid approach:
    - Pass 3D WORLD coordinates to OpenGL
    - Use gluPerspective instead of glOrtho
    - Set up modelview matrix for camera
    - GPU handles projection, clipping, depth testing
    - BSP used for efficiency (front-to-back), not correctness
"""

from dataclasses import dataclass
import math

from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QSurfaceFormat

from OpenGL.GL import (
    glEnable, glDisable, glClear, glClearColor, glClearDepth,
    glDepthFunc, glBegin, glEnd, glVertex3f, glColor3f, glColor4f,
    glMatrixMode, glLoadIdentity, glViewport,
    glLineWidth, glPushMatrix, glPopMatrix,
    glTranslatef, glRotatef,
    GL_DEPTH_TEST, GL_DEPTH_BUFFER_BIT, GL_COLOR_BUFFER_BIT,
    GL_LESS, GL_POLYGON, GL_LINE_LOOP, GL_LINES,
    GL_PROJECTION, GL_MODELVIEW,
    GL_POLYGON_OFFSET_FILL, glPolygonOffset,
    GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, glBlendFunc
)
from OpenGL.GLU import gluPerspective

from wireframe_engine.dungeon import DungeonMap, Wall, WallFace, create_test_dungeon, CELL_SIZE
from wireframe_engine.bsp import BSPTree, build_bsp_from_dungeon
from wireframe_engine.level import Level, Entity, load_level, parse_level, create_test_levels


class GL3DDungeonRenderer(QGraphicsView):
    """
    Full OpenGL 3D dungeon renderer.
    
    No software projection - OpenGL handles everything.
    """

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

        # Scene setup
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

        # OpenGL setup with depth buffer
        gl_widget = QOpenGLWidget()
        fmt = QSurfaceFormat()
        fmt.setSamples(4)
        fmt.setSwapInterval(1)
        fmt.setDepthBufferSize(24)
        gl_widget.setFormat(fmt)
        self.setViewport(gl_widget)
        self.gl_widget = gl_widget

        # Camera - simple position and angle (Y-axis rotation only)
        # Note: dungeon.py uses +Y down, -Y up
        # Walls go from floor_y=0 to ceiling_y=-60
        # So eye level is around -15 to -20
        self.cam_x = 0.0
        self.cam_y = -15.0  # Eye height in dungeon coords (-Y is up)
        self.cam_z = 0.0
        self.cam_angle = 0.0  # Degrees, 0 = looking down -Z

        # Create dungeon and BSP tree
        self.dungeon = None
        self.bsp_tree = None
        self.level = None
        self.entities = []

        # Input and rendering options
        self.keys_pressed = set()
        self.color_name = 'amber'
        self.color = QColor(self.COLOR_SCHEMES['amber'])
        self.fill_intensity = 0.15  # Fill brightness relative to wireframe

        # Weapon bob animation
        self.bob_timer = 0.0
        self.is_moving = False

        # Stats
        self.walls_rendered = 0
        self.frame_count = 0

        # Game loop
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def load_level_file(self, filepath: str):
        """Load a level from a .level file."""
        self.level = load_level(filepath)
        self._apply_level(self.level)
        print(f"Loaded: {self.level.name}")
    
    def load_level_string(self, content: str, name: str = "Unnamed"):
        """Load a level from a string."""
        self.level = parse_level(content, name)
        self._apply_level(self.level)
        print(f"Loaded: {self.level.name}")
    
    def _apply_level(self, level: Level):
        """Apply a loaded level to the game."""
        self.dungeon = level.dungeon
        self.bsp_tree = build_bsp_from_dungeon(self.dungeon)
        self.entities = list(level.entities)  # Copy so we can modify
        
        # Place camera at player start
        start_gx, start_gz = level.player_start
        self.cam_x, self.cam_z = self.dungeon.grid_to_world(start_gx, start_gz)
        self.cam_angle = 0.0
        
        stats = self.bsp_tree.get_stats()
        print(f"BSP built: {stats['nodes']} nodes, {stats['splits']} splits, depth {stats['depth']}")
        print(f"Entities: {len(self.entities)}")
    
    def load_test_dungeon(self):
        """Load the built-in test dungeon."""
        dungeon = create_test_dungeon()
        self.dungeon = dungeon
        self.bsp_tree = build_bsp_from_dungeon(dungeon)
        self.level = None
        self.entities = []
        
        # Place camera in starting room
        start_x, start_z = self.dungeon.grid_to_world(9, 9)
        self.cam_x = start_x
        self.cam_z = start_z
        self.cam_angle = 0.0
        
        stats = self.bsp_tree.get_stats()
        print(f"BSP built: {stats['nodes']} nodes, {stats['splits']} splits, depth {stats['depth']}")

    def _tick(self):
        """Game loop."""
        self._handle_input()
        self.frame_count += 1
        self.scene.invalidate(self.scene.sceneRect())

    def _handle_input(self):
        """WASD movement with collision buffer."""
        speed = 3.0
        turn_speed = 2.0
        collision_radius = 12.0  # Buffer distance from walls

        if Qt.Key.Key_A in self.keys_pressed or Qt.Key.Key_Left in self.keys_pressed:
            self.cam_angle -= turn_speed
        if Qt.Key.Key_D in self.keys_pressed or Qt.Key.Key_Right in self.keys_pressed:
            self.cam_angle += turn_speed

        # Movement
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

        # Collision check with buffer - check multiple points around player
        can_move = True
        for dx, dz in [(0, 0), (collision_radius, 0), (-collision_radius, 0), 
                        (0, collision_radius), (0, -collision_radius)]:
            gx, gz = self.dungeon.world_to_grid(new_x + dx, new_z + dz)
            if not self.dungeon.is_walkable(gx, gz):
                can_move = False
                break

        if can_move:
            self.cam_x = new_x
            self.cam_z = new_z
        
        # Update weapon bob
        self.is_moving = moving and can_move
        if self.is_moving:
            self.bob_timer += 0.08  # Slower bob speed
        else:
            # Gentle idle sway
            self.bob_timer += 0.02

    def keyPressEvent(self, event):
        self.keys_pressed.add(event.key())

        if event.key() == Qt.Key.Key_C:
            names = list(self.COLOR_SCHEMES.keys())
            idx = (names.index(self.color_name) + 1) % len(names)
            self.color_name = names[idx]
            self.color = QColor(self.COLOR_SCHEMES[self.color_name])

        if event.key() in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.close()

    def keyReleaseEvent(self, event):
        self.keys_pressed.discard(event.key())

    def drawBackground(self, painter: QPainter, rect):
        """Main render loop - full OpenGL 3D."""
        self.walls_rendered = 0

        painter.beginNativePainting()

        # Viewport setup for HiDPI
        vp = self.viewport()
        ratio = self.devicePixelRatio()
        vp_width = int(vp.width() * ratio)
        vp_height = int(vp.height() * ratio)

        # Clear buffers
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClearDepth(1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Enable depth testing
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LESS)

        # Projection matrix - perspective
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glViewport(0, 0, vp_width, vp_height)
        
        # FOV, aspect ratio, near, far
        fov = 75.0
        aspect = self.win_width / self.win_height
        near = 1.0
        far = 1000.0
        gluPerspective(fov, aspect, near, far)

        # Modelview matrix - camera transform
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        # Camera rotation then translation (reverse order in OpenGL)
        glRotatef(self.cam_angle, 0, 1, 0)  # Rotate around Y
        glTranslatef(-self.cam_x, -self.cam_y, -self.cam_z)  # Move world opposite to camera

        # Get colors
        r = self.color.redF()
        g = self.color.greenF()
        b = self.color.blueF()
        fill_r = r * self.fill_intensity
        fill_g = g * self.fill_intensity
        fill_b = b * self.fill_intensity

        # Enable polygon offset for fills
        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(1.0, 1.0)
        
        glLineWidth(2.0)

        # Render walls using BSP front-to-back order
        # With proper depth testing, order is for efficiency (early z rejection)
        for wall in self.bsp_tree.traverse_front_to_back(self.cam_x, self.cam_z):
            self._render_wall_3d(wall, r, g, b, fill_r, fill_g, fill_b)
            self.walls_rendered += 1

        glDisable(GL_POLYGON_OFFSET_FILL)
        glLineWidth(1.0)
        
        # Draw weapon (staff) in screen space
        self._draw_staff()
        
        glDisable(GL_DEPTH_TEST)

        painter.endNativePainting()

        # Draw HUD with QPainter
        self._draw_hud(painter)

    def _render_wall_3d(self, wall: Wall, r, g, b, fill_r, fill_g, fill_b):
        """
        Render a wall in full 3D - pass world coordinates directly to OpenGL.
        """
        quads_with_normals = wall.get_all_quads_with_normals()

        for quad, normal in quads_with_normals:
            # Simple back-face culling based on view direction
            # Vector from wall to camera
            wall_center_x = sum(v[0] for v in quad) / 4
            wall_center_z = sum(v[2] for v in quad) / 4
            to_cam_x = self.cam_x - wall_center_x
            to_cam_z = self.cam_z - wall_center_z
            
            # Dot product with normal
            dot = to_cam_x * normal[0] + to_cam_z * normal[2]
            if dot < 0:
                continue  # Back face

            # Draw fill
            glColor3f(fill_r, fill_g, fill_b)
            glBegin(GL_POLYGON)
            for wx, wy, wz in quad:
                glVertex3f(wx, wy, wz)
            glEnd()

            # Draw outline
            glColor3f(r, g, b)
            glBegin(GL_LINE_LOOP)
            for wx, wy, wz in quad:
                glVertex3f(wx, wy, wz)
            glEnd()

    def _draw_staff(self):
        """
        Draw the wizard's staff in screen space (2D overlay).
        """
        # Switch to 2D orthographic projection for HUD/weapon
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        
        # Get viewport for proper scaling
        vp = self.viewport()
        ratio = self.devicePixelRatio()
        vp_width = int(vp.width() * ratio)
        vp_height = int(vp.height() * ratio)
        
        from OpenGL.GLU import gluOrtho2D
        gluOrtho2D(0, self.win_width, self.win_height, 0)
        
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        
        # Disable depth test for 2D overlay
        glDisable(GL_DEPTH_TEST)
        
        # Staff position - bottom center of screen
        cx = self.win_width // 2 + 80  # Slightly right of center (like holding in right hand)
        base_y = self.win_height + 40  # Base is off-screen
        
        # Apply weapon bob
        if self.is_moving:
            # Walking sway - smooth, gentle movement
            bob_x = math.sin(self.bob_timer) * 5
            bob_y = math.sin(self.bob_timer * 2) * 6
        else:
            # Idle sway - slow, subtle breathing motion
            bob_x = math.sin(self.bob_timer) * 2
            bob_y = math.sin(self.bob_timer * 0.7) * 2
        
        cx += bob_x
        base_y += bob_y
        
        # Get color
        r = self.color.redF()
        g = self.color.greenF()
        b = self.color.blueF()
        
        # Staff dimensions
        shaft_length = 280
        shaft_width = 6
        head_size = 35
        crystal_size = 20
        
        # Calculate staff top
        top_y = base_y - shaft_length
        
        glLineWidth(2.5)
        glColor3f(r, g, b)
        
        # === SHAFT ===
        # Two parallel lines for the shaft
        glBegin(GL_LINES)
        # Left edge of shaft
        glVertex3f(cx - shaft_width/2, base_y, 0)
        glVertex3f(cx - shaft_width/2, top_y + head_size, 0)
        # Right edge of shaft
        glVertex3f(cx + shaft_width/2, base_y, 0)
        glVertex3f(cx + shaft_width/2, top_y + head_size, 0)
        glEnd()
        
        # Cross pieces on shaft (grip detail)
        glBegin(GL_LINES)
        for i in range(3):
            y = base_y - 60 - i * 40
            glVertex3f(cx - shaft_width/2 - 4, y, 0)
            glVertex3f(cx + shaft_width/2 + 4, y, 0)
        glEnd()
        
        # === STAFF HEAD (decorative frame) ===
        head_y = top_y + head_size
        
        # Triangular/pointed head frame
        glBegin(GL_LINE_LOOP)
        glVertex3f(cx, top_y - 10, 0)                    # Top point
        glVertex3f(cx - head_size/2, head_y, 0)         # Bottom left
        glVertex3f(cx + head_size/2, head_y, 0)         # Bottom right
        glEnd()
        
        # Inner frame
        glBegin(GL_LINE_LOOP)
        glVertex3f(cx, top_y + 5, 0)                     # Top point
        glVertex3f(cx - head_size/3, head_y - 8, 0)     # Bottom left
        glVertex3f(cx + head_size/3, head_y - 8, 0)     # Bottom right
        glEnd()
        
        # === CRYSTAL (diamond shape) ===
        crystal_y = top_y + head_size/2 - 5
        
        glBegin(GL_LINE_LOOP)
        glVertex3f(cx, crystal_y - crystal_size/2, 0)    # Top
        glVertex3f(cx + crystal_size/3, crystal_y, 0)    # Right
        glVertex3f(cx, crystal_y + crystal_size/2, 0)    # Bottom
        glVertex3f(cx - crystal_size/3, crystal_y, 0)    # Left
        glEnd()
        
        # Crystal inner glow lines
        glLineWidth(1.5)
        glBegin(GL_LINES)
        glVertex3f(cx, crystal_y - crystal_size/3, 0)
        glVertex3f(cx, crystal_y + crystal_size/3, 0)
        glVertex3f(cx - crystal_size/4, crystal_y, 0)
        glVertex3f(cx + crystal_size/4, crystal_y, 0)
        glEnd()
        
        glLineWidth(1.0)
        
        # Restore matrices
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def _draw_hud(self, painter: QPainter):
        """Draw HUD overlay."""
        painter.setPen(QPen(self.color))

        gx, gz = self.dungeon.world_to_grid(self.cam_x, self.cam_z)

        painter.drawText(10, 20, f"BSP GL3D - {self.color_name.title()}")
        painter.drawText(10, 40, f"Pos: ({gx}, {gz}) Angle: {self.cam_angle:.0f}°")
        painter.drawText(10, 60, f"Walls rendered: {self.walls_rendered}")

        # Draw minimap
        self._draw_minimap(painter)

    def _draw_minimap(self, painter: QPainter):
        """Draw top-down minimap."""
        map_size = 120
        cell_size = map_size // self.dungeon.width
        offset_x = self.win_width - map_size - 10
        offset_y = 10

        # Draw cells
        dim_color = QColor(self.color)
        dim_color.setAlpha(60)
        painter.setPen(QPen(dim_color))

        for gz in range(self.dungeon.height):
            for gx in range(self.dungeon.width):
                if self.dungeon.is_walkable(gx, gz):
                    x = offset_x + gx * cell_size
                    y = offset_y + gz * cell_size
                    painter.drawRect(x, y, cell_size, cell_size)

        # Player position and direction
        pgx, pgz = self.dungeon.world_to_grid(self.cam_x, self.cam_z)
        px = offset_x + pgx * cell_size + cell_size // 2
        py = offset_y + pgz * cell_size + cell_size // 2

        painter.setPen(QPen(self.color, 2))
        painter.drawEllipse(QPoint(px, py), 3, 3)

        rad = math.radians(self.cam_angle)
        dx = math.sin(rad) * 8
        dy = -math.cos(rad) * 8
        painter.drawLine(px, py, int(px + dx), int(py + dy))


def main():
    """Run the GL3D dungeon demo."""
    import sys
    from pathlib import Path
    from PyQt6.QtWidgets import QApplication

    print("=" * 50)
    print("BENEATH THE CASTLE OF BANE")
    print("BSP Dungeon Engine - Full OpenGL 3D")
    print("=" * 50)

    app = QApplication(sys.argv)

    renderer = GL3DDungeonRenderer(800, 600)
    
    # Check for level file argument
    if len(sys.argv) > 1:
        level_path = sys.argv[1]
        if Path(level_path).exists():
            renderer.load_level_file(level_path)
        else:
            print(f"Level file not found: {level_path}")
            print("Loading test dungeon instead...")
            renderer.load_test_dungeon()
    else:
        # Try to load level1.level from levels/ directory
        default_level = Path(__file__).parent / "levels" / "level1.level"
        if default_level.exists():
            renderer.load_level_file(str(default_level))
        else:
            print("No level specified, loading test dungeon...")
            renderer.load_test_dungeon()
    
    renderer.show()

    print("\nControls:")
    print("  WASD / Arrows: Move")
    print("  C: Cycle colors")
    print("  Q / Esc: Quit")
    print()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
