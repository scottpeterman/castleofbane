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
├── bsp.py           # BSP tree for efficient wall traversal
├── dungeon.py       # DungeonMap, Wall, CellType, grid system
└── level.py         # Level loading from .level files
```

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `bsp.py` | Binary Space Partitioning tree for correct draw order |
| `dungeon.py` | Grid-based level: cells, walls, automatic wall generation |
| `level.py` | Data-driven level loading, entity parsing |

---

## Level System

### Loading Levels

```python
from wireframe_engine import load_level, Level

# Load from file
level = load_level("levels/level1.level")

print(level.name)           # "The Dungeon Entrance"
print(level.player_start)   # (1, 1) grid coordinates
print(level.next_level)     # "level2.level"
print(level.entities)       # [Entity(...), Entity(...), ...]

# Access dungeon
dungeon = level.dungeon
```

### Level File Format

```
name: The Dungeon Entrance
next: level2.level
prev: level0.level
---
####################
#@.......#....K....#
#........D.........#
#........#....E....#
####################
```

### Character Legend

| Char | Cell Type | Entity Type |
|------|-----------|-------------|
| `#` | SOLID | - |
| `.` | FLOOR | - |
| `@` | FLOOR | player_start |
| `D` | DOOR | door |
| `L` | DOOR | door_locked |
| `K` | FLOOR | key |
| `k` | FLOOR | key_silver |
| `E` | FLOOR | skeleton |
| `G` | FLOOR | ghost |
| `T` | FLOOR | treasure |
| `<` | STAIRS_UP | stairs_up |
| `>` | STAIRS_DOWN | stairs_down |
| `U` | STAIRS_UP | stairs_up |
| `V` | STAIRS_DOWN | stairs_down |
| `S` | SECRET | secret_door |
| `~` | PIT | - |

### Entity Class

```python
@dataclass
class Entity:
    type: str       # 'key', 'skeleton', 'ghost', 'treasure', etc.
    gx: int         # Grid X position
    gz: int         # Grid Z position
    properties: dict = field(default_factory=dict)

# Query entities
keys = level.get_entities_by_type('key')
entity = level.get_entity_at(5, 10)
level.remove_entity(entity)  # When collected/killed
```

---

## Rendering with OpenGL

### Recommended Approach

Pass world coordinates directly to OpenGL. Let the GPU handle projection and depth testing.

```python
# Setup perspective projection
gluPerspective(fov, aspect, near, far)

# Camera transform
glRotatef(camera_angle, 0, 1, 0)
glTranslatef(-cam_x, -cam_y, -cam_z)

# Enable depth testing
glEnable(GL_DEPTH_TEST)

# Render walls via BSP traversal
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

- Walls: `floor_y = 0` to `ceiling_y = -60`
- Eye level: `cam_y = -15.0`
- Cell size: 50 world units

---

## BSP Tree

Binary Space Partitioning provides mathematically correct draw order.

### Building

```python
from wireframe_engine import build_bsp_from_dungeon

# Build once when level loads
bsp_tree = build_bsp_from_dungeon(dungeon)

stats = bsp_tree.get_stats()
# {'nodes': 45, 'splits': 3, 'depth': 8}
```

### Traversal

```python
# Front-to-back (with z-buffer, for early-z rejection)
for wall in bsp_tree.traverse_front_to_back(camera_x, camera_z):
    render(wall)

# Back-to-front (painter's algorithm, no z-buffer needed)
for wall in bsp_tree.traverse_back_to_front(camera_x, camera_z):
    render(wall)
```

---

## DungeonMap

Grid-based level structure. Each cell is `CELL_SIZE × CELL_SIZE` world units (default 50).

```python
from wireframe_engine import DungeonMap, CellType, CELL_SIZE

# Create dungeon
dungeon = DungeonMap(width=20, height=20)

# Carve rooms and corridors
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

| Type | Walkable | Description |
|------|----------|-------------|
| SOLID | No | Impassable wall |
| FLOOR | Yes | Open floor |
| DOOR | Yes | Door (can be open/closed) |
| SECRET | No | Secret door (looks like wall) |
| PIT | No | Hole - see through, can't walk |
| STAIRS_UP | Yes | Stairs to upper level |
| STAIRS_DOWN | Yes | Stairs to lower level |

### Wall Geometry

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

### With Buffer (Prevents Wall Clipping)

```python
def is_move_valid(new_x, new_z, radius=12.0):
    for dx, dz in [(0,0), (radius,0), (-radius,0), (0,radius), (0,-radius)]:
        gx, gz = dungeon.world_to_grid(new_x + dx, new_z + dz)
        if not dungeon.is_walkable(gx, gz):
            return False
    return True
```

---

## OpenGL Setup

### Depth Testing

```python
glEnable(GL_DEPTH_TEST)
glDepthFunc(GL_LESS)
glClearDepth(1.0)
glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
```

### Polygon Offset (Prevents Z-Fighting)

```python
# Push fills back so wireframe outlines draw on top
glEnable(GL_POLYGON_OFFSET_FILL)
glPolygonOffset(1.0, 1.0)
# Draw fills...
glDisable(GL_POLYGON_OFFSET_FILL)
# Draw wireframes...
```

### HiDPI Support

```python
ratio = self.devicePixelRatio()
vp_width = int(widget.width() * ratio)
vp_height = int(widget.height() * ratio)
glViewport(0, 0, vp_width, vp_height)
```

---

## Example: Complete Game Loop

```python
from wireframe_engine import load_level, build_bsp_from_dungeon, CELL_SIZE

class Game:
    def __init__(self):
        # Load level
        self.level = load_level("levels/level1.level")
        self.dungeon = self.level.dungeon
        self.bsp = build_bsp_from_dungeon(self.dungeon)
        self.entities = list(self.level.entities)
        
        # Camera at player start
        gx, gz = self.level.player_start
        self.cam_x = gx * CELL_SIZE + CELL_SIZE / 2
        self.cam_z = gz * CELL_SIZE + CELL_SIZE / 2
        self.cam_y = -15.0
        self.cam_angle = 0.0
    
    def render(self):
        # Setup projection and camera...
        
        # Render walls
        for wall in self.bsp.traverse_front_to_back(self.cam_x, self.cam_z):
            self.render_wall(wall)
        
        # Render entities
        for entity in self.entities:
            self.render_entity(entity)
    
    def update(self):
        # Check for key pickup
        gx, gz = self.dungeon.world_to_grid(self.cam_x, self.cam_z)
        entity = self.level.get_entity_at(gx, gz)
        if entity and entity.type == 'key':
            self.inventory.append('key')
            self.entities.remove(entity)
        
        # Check for stairs
        if entity and entity.type == 'stairs_down':
            self.load_next_level()
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

## Performance

- **Target:** 60fps at 800×600
- **Typical load:** 80-230 wall faces
- **Optimization:** BSP front-to-back traversal enables early-z rejection

Discrete GPU recommended. On Linux with Nvidia:

```bash
__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia python game.py
```

---

## License

Educational/personal project.