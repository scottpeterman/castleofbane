# Wireframe Engine

A PyQt6/OpenGL engine for first-person wireframe dungeon crawlers, inspired by classic vector graphics.

## Overview

This engine provides grid-based dungeon rendering using BSP trees and hardware-accelerated OpenGL. It's designed for games with a retro vector graphics aesthetic - think amber or green phosphor CRT terminals.

```
┌─────────────────────────────────────────┐
│                                         │
│    ╱│         ┌──┐                      │
│   ╱ │      ┌──┤  ├──┐                   │
│  │  │      │  │  │  │                   │
│  │  │      │  └──┘  │                   │
│──┴──┴──────┴────────┴───────────────────│
│                                         │
└─────────────────────────────────────────┘
```

---

## Architecture

```
wireframe_engine/
├── __init__.py      # Public API exports
├── core.py          # Camera, transforms, projection, clipping (legacy)
├── objects.py       # GameObject, Projectile classes
├── renderer.py      # WireframeRenderer base class (legacy)
├── dungeon.py       # DungeonMap, Wall, CellType, grid system
└── bsp.py           # BSP tree for efficient wall traversal
```

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `core.py` | Math utilities, legacy software projection (deprecated for 3D rendering) |
| `objects.py` | Game entities: GameObject, Projectile, model format |
| `renderer.py` | Legacy PyQt6 rendering base class |
| `dungeon.py` | Grid-based level: cells, walls, automatic wall generation |
| `bsp.py` | Binary Space Partitioning tree for correct draw order |

---

## Rendering Approaches

### Recommended: Full OpenGL 3D (v0.3.0+)

Pass world coordinates directly to OpenGL. Let the GPU handle projection and depth testing.

```python
# Setup perspective projection
gluPerspective(fov, aspect, near, far)

# Camera transform
glRotatef(camera_angle, 0, 1, 0)
glTranslatef(-cam_x, -cam_y, -cam_z)

# Enable depth testing
glEnable(GL_DEPTH_TEST)

# Render walls - pass 3D world coords directly
for wall in bsp_tree.traverse_front_to_back(cam_x, cam_z):
    for quad, normal in wall.get_all_quads_with_normals():
        # Back-face culling
        if dot(normal, to_camera) < 0:
            continue
        
        # Draw fill
        glBegin(GL_POLYGON)
        for x, y, z in quad:
            glVertex3f(x, y, z)
        glEnd()
        
        # Draw wireframe
        glBegin(GL_LINE_LOOP)
        for x, y, z in quad:
            glVertex3f(x, y, z)
        glEnd()
```

**Advantages:**
- Hardware depth buffer handles occlusion perfectly
- No software projection math
- No depth value hacks
- BSP provides efficient traversal (early-z rejection)
- Clean separation of concerns

### Legacy: Software Projection + Painter's Algorithm

The original approach - software transforms to 2D, sort by depth, draw back-to-front.

**Limitations:**
- Sorting artifacts with complex geometry
- Can't easily retrofit hardware depth testing
- More code complexity

---

## Coordinate System

```
World Coordinates (top-down view):

        -Z (North/Forward)
              ^
              |
    -X <──────┼──────> +X (East/Right)
              |
              v
        +Z (South/Back)

Vertical axis:
    -Y = Up
    +Y = Down
```

### Dungeon Coordinates

Walls extend from `floor_y = 0` (ground) to `ceiling_y = -60` (ceiling, since -Y is up).

For a first-person camera at "eye level":
```python
cam_y = -15.0  # About 25% up from floor to ceiling
```

---

## BSP Tree

Binary Space Partitioning provides mathematically correct draw order.

### Building

```python
from wireframe_engine.bsp import build_bsp_from_dungeon

# Build once when level loads
bsp_tree = build_bsp_from_dungeon(dungeon)

stats = bsp_tree.get_stats()
# {'nodes': 45, 'splits': 3, 'depth': 8}
```

### Traversal

```python
# Back-to-front (painter's algorithm)
for wall in bsp_tree.traverse_back_to_front(camera_x, camera_z):
    render(wall)

# Front-to-back (with z-buffer, for early-z rejection)
for wall in bsp_tree.traverse_front_to_back(camera_x, camera_z):
    render(wall)
```

### How It Works

1. **Build time:** Recursively partition walls using splitting planes
2. **Render time:** Traverse tree based on camera position
   - Visit far side first, then splitter, then near side (back-to-front)
   - Or reverse for front-to-back

This is the algorithm Doom used. For grid dungeons it provides optimal traversal without runtime sorting.

---

## DungeonMap

Grid-based level structure where each cell is `CELL_SIZE × CELL_SIZE` world units (default 50).

```python
from wireframe_engine.dungeon import DungeonMap, CellType, CELL_SIZE

# Create empty dungeon (all solid)
dungeon = DungeonMap(width=20, height=20)

# Carve out rooms and corridors
dungeon.carve_room(5, 5, 10, 10)
dungeon.carve_corridor(7, 10, 7, 15)

# Generate wall geometry
dungeon.generate_walls()

# Query
is_floor = dungeon.is_walkable(gx, gz)
gx, gz = dungeon.world_to_grid(world_x, world_z)
world_x, world_z = dungeon.grid_to_world(gx, gz)
```

### Cell Types

| Type | Value | Walkable | Description |
|------|-------|----------|-------------|
| SOLID | 0 | No | Impassable wall/rock |
| FLOOR | 1 | Yes | Open floor |
| DOOR | 2 | Yes | Door (can be open/closed) |
| SECRET | 3 | No | Secret door (looks like wall) |
| PIT | 4 | No | Hole - can see through, can't walk |
| STAIRS_UP | 5 | Yes | Stairs to upper level |
| STAIRS_DOWN | 6 | Yes | Stairs to lower level |

### Wall

Walls are 3D boxes with 4 visible faces:

```python
@dataclass
class Wall:
    x1, z1: float          # Front face start
    x2, z2: float          # Front face end
    floor_y: float = 0.0   # Bottom
    ceiling_y: float = -60 # Top (-Y is up)
    thickness: float = 4.0
    face: WallFace         # NORTH, EAST, SOUTH, WEST

# Get all quads with normals for rendering
for quad, normal in wall.get_all_quads_with_normals():
    # quad = 4 corner points (x, y, z)
    # normal = outward-facing unit vector
```

---

## Collision Detection

### Basic Grid Collision

```python
def is_move_valid(new_x, new_z):
    gx, gz = dungeon.world_to_grid(new_x, new_z)
    return dungeon.is_walkable(gx, gz)
```

### With Buffer (Prevents Wall Clipping)

```python
def is_move_valid(new_x, new_z, radius=12.0):
    # Check multiple points around player
    for dx, dz in [(0,0), (radius,0), (-radius,0), (0,radius), (0,-radius)]:
        gx, gz = dungeon.world_to_grid(new_x + dx, new_z + dz)
        if not dungeon.is_walkable(gx, gz):
            return False
    return True
```

---

## OpenGL Setup

### Viewport and Projection

```python
# Handle HiDPI displays
ratio = self.devicePixelRatio()
vp_width = int(widget.width() * ratio)
vp_height = int(widget.height() * ratio)
glViewport(0, 0, vp_width, vp_height)

# Perspective projection
glMatrixMode(GL_PROJECTION)
glLoadIdentity()
gluPerspective(75.0, width/height, 1.0, 1000.0)

# Camera transform
glMatrixMode(GL_MODELVIEW)
glLoadIdentity()
glRotatef(cam_angle, 0, 1, 0)
glTranslatef(-cam_x, -cam_y, -cam_z)
```

### Depth Testing

```python
glEnable(GL_DEPTH_TEST)
glDepthFunc(GL_LESS)
glClearDepth(1.0)
glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
```

### Polygon Offset (Prevents Z-Fighting)

```python
# Push fills back slightly so wireframe outlines draw on top
glEnable(GL_POLYGON_OFFSET_FILL)
glPolygonOffset(1.0, 1.0)

# Draw fills...

glDisable(GL_POLYGON_OFFSET_FILL)
```

---

## Performance

### Target Specs

- **Resolution:** 800×600
- **Frame rate:** 60fps
- **Typical load:** 80-120 wall faces visible

### Optimization via BSP

Front-to-back traversal with z-buffer enables early-z rejection:
- Near walls write to depth buffer first
- Far wall fragments fail depth test early
- Reduces pixel shader work (overdraw)

### GPU Notes

Discrete GPU recommended. On Linux with Nvidia:

```bash
__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia python game.py
```

---

## Example: Minimal Game

```python
import math
from PyQt6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *
from OpenGL.GLU import gluPerspective

from wireframe_engine.dungeon import create_test_dungeon
from wireframe_engine.bsp import build_bsp_from_dungeon

class MyGame(QGraphicsView):
    def __init__(self):
        super().__init__()
        
        # Setup OpenGL
        self.setViewport(QOpenGLWidget())
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        
        # Load level
        self.dungeon = create_test_dungeon()
        self.bsp = build_bsp_from_dungeon(self.dungeon)
        
        # Camera
        self.cam_x, self.cam_z = self.dungeon.grid_to_world(9, 9)
        self.cam_y = -15.0
        self.cam_angle = 0.0
        
        # Game loop
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
    
    def tick(self):
        self.scene.invalidate()
    
    def drawBackground(self, painter, rect):
        painter.beginNativePainting()
        
        # Clear
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glEnable(GL_DEPTH_TEST)
        
        # Projection
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(75, 800/600, 1, 1000)
        
        # Camera
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glRotatef(self.cam_angle, 0, 1, 0)
        glTranslatef(-self.cam_x, -self.cam_y, -self.cam_z)
        
        # Render walls
        for wall in self.bsp.traverse_front_to_back(self.cam_x, self.cam_z):
            for quad, normal in wall.get_all_quads_with_normals():
                glColor3f(1.0, 0.7, 0.0)  # Amber
                glBegin(GL_LINE_LOOP)
                for x, y, z in quad:
                    glVertex3f(x, y, z)
                glEnd()
        
        glDisable(GL_DEPTH_TEST)
        painter.endNativePainting()

if __name__ == "__main__":
    app = QApplication([])
    game = MyGame()
    game.show()
    app.exec()
```

---

## Dependencies

- Python 3.10+
- PyQt6
- PyOpenGL

```bash
pip install PyQt6 PyOpenGL
```

---

## License

Educational/personal project.
