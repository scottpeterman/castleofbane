# Beneath the Castle of Bane

A first-person wireframe dungeon crawler in the style of Wolfenstein 3D, rendered with classic vector graphics aesthetics.

## Vision

**The Pitch:** You are a wizard trapped in the dungeons beneath the Castle of Bane. Armed with your staff, you must fight through monsters, find keys, unlock doors, and escape to the surface.

**The Feel:** 
- Wolfenstein 3D meets Battlezone
- Retro vector graphics (amber/green phosphor CRT look)
- Staff/wand always visible at bottom of screen (like Wolf3D's gun)
- Grid-based dungeon with doors, keys, enemies
- Simple but satisfying combat

**Inspirations:**
- Wolfenstein 3D (1992) - First-person shooter on a grid, weapon always visible
- Battlezone (1980) - Vector graphics aesthetic
- Ultima Underworld (1992) - Dungeon crawling atmosphere
- Eye of the Beholder (1991) - D&D dungeon feel

---

## Current State (v0.3.0)

**Working:**
- Full OpenGL 3D rendering with hardware depth buffer
- BSP tree for efficient front-to-back wall traversal
- Proper wall occlusion (no see-through artifacts)
- Grid-based dungeon with automatic wall generation
- Player movement with collision buffer
- Multiple color schemes (Amber, Green, Blue, etc.)
- Minimap
- 60fps on discrete GPU

**Screenshot:**
```
┌─────────────────────────────────────────┐
│ BSP GL3D - Amber                        │
│ Pos: (10, 10) Angle: 45°      ┌───┐     │
│ Walls rendered: 96            │ ▪ │     │
│                               └───┘     │
│    ╱│         ┌──┐                      │
│   ╱ │      ┌──┤  ├──┐                   │
│  │  │      │  │  │  │                   │
│  │  │      │  └──┘  │                   │
│──┴──┴──────┴────────┴───────────────────│
│                                         │
└─────────────────────────────────────────┘
```

**Key Improvements in v0.3.0:**
- Switched from software projection + painter's algorithm to full OpenGL 3D
- BSP tree handles traversal order; GPU depth buffer handles occlusion
- No more "see through walls" artifacts at angles or close range
- Cleaner architecture - let OpenGL do what it's designed for

---

## Roadmap

### Phase 1: Core Dungeon ✔
- [x] 3D wireframe rendering
- [x] BSP tree for wall ordering
- [x] Hardware depth buffer occlusion
- [x] Grid-based level structure
- [x] Player movement/collision with buffer
- [x] Minimap
- [x] Color schemes

### Phase 2: Interactivity (Next)
- [ ] **Weapon view** - Staff/wand at bottom of screen
- [ ] **Weapon bob** - Subtle movement while walking
- [ ] **Doors** - Locked and unlocked, open with Space
- [ ] **Keys** - Collectible items to unlock doors

### Phase 3: Combat
- [ ] **Enemies** - Simple wandering monsters
- [ ] **Spellcasting** - Fire projectile from staff
- [ ] **Enemy AI** - Chase player when spotted
- [ ] **Health system** - Player and enemy HP
- [ ] **Death/respawn** - Game over state

### Phase 4: Polish
- [ ] **Sound effects** - Footsteps, doors, combat
- [ ] **Procedural dungeons** - Random level generation
- [ ] **Multiple levels** - Stairs up/down
- [ ] **Title screen** - Start menu
- [ ] **Score/treasure** - Collectibles

---

## Technical Architecture

### Rendering Pipeline (v0.3.0)

```
World Geometry (3D coordinates)
     ↓
BSP Tree Traversal (front-to-back from camera position)
     ↓
For each wall:
  Back-face Culling (dot product with view direction)
     ↓
  Pass 3D vertices directly to OpenGL
     ↓
OpenGL handles:
  - Perspective projection (gluPerspective)
  - Near/far plane clipping
  - Depth testing (z-buffer)
  - Rasterization
     ↓
Draw: Polygon fill + wireframe outline
```

**Key insight:** Earlier versions tried to do software projection to 2D, then retrofit depth values for the z-buffer. This hybrid approach was fundamentally broken. The new approach lets OpenGL handle the entire 3D pipeline.

### File Structure

```
wireframe_engine/           # Reusable engine
├── core.py                 # Camera, projection, clipping (legacy)
├── objects.py              # GameObject base class  
├── renderer.py             # WireframeRenderer base (legacy)
├── dungeon.py              # DungeonMap, Wall, Cell types
└── bsp.py                  # BSP tree implementation

game files/
├── bsp_dungeon_gl3d.py     # Main game - full OpenGL 3D renderer
├── bsp_dungeon_demo.py     # Earlier hybrid approach (deprecated)
├── weapons.py              # Staff/wand rendering (TODO)
├── enemies.py              # Monster types and AI (TODO)
└── items.py                # Keys, treasures (TODO)
```

### BSP Tree

Binary Space Partitioning provides correct traversal order:

```python
# Build once at level load
bsp_tree = build_bsp_from_dungeon(dungeon)

# Each frame - traverse front-to-back for efficiency
for wall in bsp_tree.traverse_front_to_back(camera.x, camera.z):
    render_wall(wall)
```

With hardware depth testing, traversal order doesn't affect correctness - the z-buffer handles occlusion. But front-to-back order enables early-z rejection, reducing overdraw.

### OpenGL Setup

```python
# Perspective projection
gluPerspective(fov=75.0, aspect=width/height, near=1.0, far=1000.0)

# Camera transform via modelview matrix
glRotatef(cam_angle, 0, 1, 0)      # Yaw rotation
glTranslatef(-cam_x, -cam_y, -cam_z)  # Position

# Depth testing
glEnable(GL_DEPTH_TEST)
glDepthFunc(GL_LESS)

# Polygon offset prevents z-fighting between fills and outlines
glEnable(GL_POLYGON_OFFSET_FILL)
glPolygonOffset(1.0, 1.0)
```

---

## Controls

| Key | Action |
|-----|--------|
| W / ↑ | Move forward |
| S / ↓ | Move backward |
| A / ← | Turn left |
| D / → | Turn right |
| Space | Open door (TODO) |
| Ctrl / Click | Cast spell (TODO) |
| C | Cycle color scheme |
| Q / Esc | Quit |

---

## Color Schemes

| Name | Hex | Vibe |
|------|-----|------|
| **Amber** | #FFB000 | Classic terminal (default) |
| Green | #00FFAA | Battlezone |
| Blue | #00BFFF | Sci-fi terminal |
| White | #FFFFFF | Monochrome |

---

## Running

```bash
# Install dependencies
pip install PyQt6 PyOpenGL

# Run the game
python bsp_dungeon_gl3d.py

# On Linux with Nvidia GPU (recommended for smoothness)
__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia python bsp_dungeon_gl3d.py
```

---

## Development History

- **v0.1.0** - Basic painter's algorithm, flickering occlusion issues
- **v0.2.0** - Portal rendering, view-dependent culling, color schemes
- **v0.3.0** - Full OpenGL 3D with BSP tree, hardware depth buffer, proper occlusion

---

## License

Educational/personal project.

Wolfenstein 3D is © id Software.
Battlezone is © Atari.
