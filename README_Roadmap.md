# Beneath the Castle of Bane - Development Roadmap

## Current State (v0.4.0) ✓

**Working:**
- Full OpenGL 3D rendering with BSP tree
- Data-driven level loading from `.level` files
- ASCII map format with header metadata
- Entity parsing (keys, enemies, doors, stairs, treasure)
- Wizard's staff with idle/walking sway
- Multiple color schemes
- Minimap
- Collision detection with buffer

**Project Structure:**
```
castle_of_bane/
├── bsp_dungeon_gl3d.py          # Main game (540 lines)
├── levels/
│   ├── level1.level             # The Dungeon Entrance
│   ├── level2.level             # The Skeleton Halls
│   └── level3.level             # The Ghost Chamber
├── wireframe_engine/
│   ├── __init__.py
│   ├── bsp.py                   # BSP tree
│   ├── dungeon.py               # Grid/wall system
│   └── level.py                 # Level loader
└── README.md
```

---

## Next Session: Entity Rendering

**Goal:** See keys, enemies, and doors in the world.

### 1. Wireframe Models
Define simple wireframe shapes for each entity type:

```python
# In new file: wireframe_engine/models.py

KEY_MODEL = {
    'lines': [
        # Ring
        ((0, 0, 0), (5, 0, 0)),
        ((5, 0, 0), (5, -8, 0)),
        ((5, -8, 0), (0, -8, 0)),
        ((0, -8, 0), (0, 0, 0)),
        # Shaft
        ((2.5, -8, 0), (2.5, -25, 0)),
        # Teeth
        ((2.5, -20, 0), (6, -20, 0)),
        ((2.5, -25, 0), (6, -25, 0)),
    ],
    'scale': 1.0,
    'y_offset': -30,  # Float at eye level
}

SKELETON_MODEL = {
    'lines': [
        # Skull
        ((0, 0, 0), (8, 0, 0)),
        ((8, 0, 0), (8, -10, 0)),
        # ... ribcage, spine, legs
    ],
    'scale': 1.5,
    'y_offset': -60,  # Standing on floor
}
```

### 2. Entity Renderer
Add to `bsp_dungeon_gl3d.py`:

```python
def _draw_entities(self):
    """Draw all entities in the world."""
    for entity in self.entities:
        wx, wz = entity.gx * CELL_SIZE + CELL_SIZE/2, entity.gz * CELL_SIZE + CELL_SIZE/2
        
        if entity.type == 'key':
            self._draw_wireframe_model(KEY_MODEL, wx, wz)
        elif entity.type == 'skeleton':
            self._draw_wireframe_model(SKELETON_MODEL, wx, wz)
        # etc.

def _draw_wireframe_model(self, model, wx, wz, rotation=0):
    """Draw a wireframe model at world position."""
    # Transform and draw lines
```

### 3. Billboarding (Optional)
Make entities always face the camera - classic Doom style.

---

## Future Sessions

### Session: Interaction
- **Space to open doors** - Check if facing a door, change cell type
- **Key pickup** - Collision with key entity, add to inventory
- **Locked doors** - Require key to open, consume key
- **Stairs** - Load next/prev level when stepping on stairs

### Session: Combat
- **Enemy AI** - State machine: idle → chase → attack
- **Line of sight** - Raycast through grid cells
- **Spellcasting** - Staff animation, spawn projectile
- **Projectiles** - Move forward, check collision with enemies
- **Health/damage** - Player HP, enemy HP, hit feedback

### Session: Polish
- **Sound effects** - PyGame mixer or simpleaudio
- **Screen flash** - Damage feedback, spell cast
- **Death state** - Game over screen, restart
- **Title screen** - New game, quit
- **Procedural levels** - Random room/corridor generation

---

## Technical Notes

### Adding New Entity Types

1. Add character to `CELL_CHARS` and `ENTITY_CHARS` in `level.py`
2. Create wireframe model in `models.py`
3. Add rendering case in `_draw_entities()`
4. Add interaction logic if needed

### Level File Format

```
name: Level Name
next: nextlevel.level
prev: prevlevel.level
---
####################
#@.......#....K....#
#........D.........#
#........#....E....#
####################
```

**Characters:**
| Char | Cell Type | Entity |
|------|-----------|--------|
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
| `S` | SECRET | secret_door |
| `~` | PIT | - |

---

## Commands

```bash
# Run with default level
python bsp_dungeon_gl3d.py

# Run specific level
python bsp_dungeon_gl3d.py levels/level2.level

# With Nvidia GPU
__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia python bsp_dungeon_gl3d.py
```

---

## Session Log

- **Session 1:** BSP tree, OpenGL 3D, depth buffer, wall occlusion
- **Session 2:** Wizard's staff, weapon bob, data-driven levels, entity parsing
- **Next:** Entity rendering, doors, keys