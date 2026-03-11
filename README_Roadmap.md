# Beneath the Castle of Bane - Development Roadmap

## Current State (v0.5.0) ✓

**Working:**
- Full OpenGL 3D rendering with BSP tree
- Data-driven level loading from `.level` files
- ASCII map format with header metadata
- Entity parsing and rendering (keys, enemies, doors, stairs, treasure)
- Billboarded wireframe entity models facing camera
- Wizard's staff with idle/walking sway
- Doors: Space to open, blocks movement when closed
- Locked doors: Red X visual, require gold key, consume on use
- Keys: Walk-over pickup (gold/silver), persist across levels
- Treasure: Collectible chests with running total
- Stairs: Level transitions (down = next, up = prev/escape)
- Three-level campaign with escape win state
- Inventory HUD (keys, treasure)
- Flash messages with fade-out
- Minimap with color-coded entity markers
- Multiple color schemes
- Collision detection with buffer + door blocking

**Project Structure:**
```
castle_of_bane/
├── bsp_dungeon_gl3d.py          # Main game (~1050 lines)
├── levels/
│   ├── level1.level             # The Dungeon Entrance
│   ├── level2.level             # The Skeleton Halls
│   └── level3.level             # The Ghost Chamber
├── wireframe_engine/
│   ├── __init__.py
│   ├── bsp.py                   # BSP tree
│   ├── dungeon.py               # Grid/wall system
│   └── level.py                 # Level loader
├── README.md
├── README_Engine.md
└── README_Roadmap.md
```

---

## Completed Sessions

### Session 1: Core Engine
- BSP tree for mathematically correct draw order
- Full OpenGL 3D with hardware depth buffer
- Wall occlusion via front-to-back traversal
- Polygon offset to prevent z-fighting
- HiDPI viewport support

### Session 2: Dungeon Feel
- Wizard's staff with idle sway and walking bob
- Data-driven level loading from `.level` files
- ASCII map format with header metadata (name, next, prev)
- Entity parsing (keys, enemies, doors, stairs, treasure)
- Multiple color schemes (Amber, Green, Blue, White)

### Session 3: Playable Game
- Wireframe entity models (skeleton, ghost, key, treasure, stairs, doors)
- Billboarded rendering — all entities face the camera
- Door interaction — Space to open, forgiving distance check
- Locked doors — red X pattern, consume gold key to unlock
- Key/treasure pickup — walk-over collection
- Inventory HUD — bottom-left key/treasure display
- Flash messages — centered text with fade-out
- Level transitions — stairs trigger next/prev level load
- BSP rebuild on door open (cell DOOR → FLOOR)
- Door collision — closed doors block movement
- Minimap entity markers — color-coded by type
- Three-level campaign: Dungeon Entrance → Skeleton Halls → Ghost Chamber → ESCAPE
- Game complete state with escape message and treasure total

---

## Technical Notes Discovered

### Entity Y-Axis Convention
Entity models rendered through `glPushMatrix` + billboard transform use **+Y = up**, which is inverted from the wall coordinate system (-Y = up). This is an artifact of the billboard rotation transform. All entity model definitions use positive Y for "up."

### Door Orientation
Door frame orientation is determined by checking neighboring solid cells:
- If east/west neighbors are solid → corridor runs N-S → door spans E-W
- If north/south neighbors are solid → corridor runs E-W → door spans N-S

### Door Collision Layering
`CellType.DOOR` returns `True` for `is_walkable()` at the engine level (required so wall generation creates corridor openings, not solid walls). The game layer adds a second collision check specifically blocking DOOR cells. When opened, the cell becomes `CellType.FLOOR`.

---

## Next Session: Combat

**Goal:** Make the skeletons and ghosts dangerous.

### Enemy AI
State machine per enemy:
- **Idle** — Stand in place (current behavior)
- **Alert** — Player spotted via line-of-sight raycast
- **Chase** — Pathfind toward player through grid cells
- **Attack** — Deal damage when adjacent to player

Line of sight via grid raycast (Bresenham or DDA through cells):
```python
def has_line_of_sight(dungeon, gx1, gz1, gx2, gz2) -> bool:
    # Step through grid cells between enemy and player
    # Return False if any SOLID cell blocks the line
```

### Spellcasting
- **Staff animation** — Quick forward thrust on Ctrl/Click
- **Projectile spawn** — Wireframe energy bolt from staff tip
- **Projectile movement** — Advance forward each tick, check grid collision
- **Hit detection** — Compare projectile grid position to enemy positions

### Health System
- Player HP (start at 100)
- Enemy HP (skeleton=2 hits, ghost=1 hit)
- Damage flash (screen border flash red on hit)
- Death state → restart level (keep inventory)

### Wireframe Models for Combat
- Projectile: small diamond/star shape, fast-moving
- Hit effect: expanding wireframe burst (few frames)
- Enemy death: wireframe collapse animation

---

## Future Sessions

### Session: Polish
- **Sound effects** — PyGame mixer or simpleaudio for footsteps, doors, combat, pickups
- **Screen flash** — Damage feedback (red border), spell cast (white flash)
- **Death state** — Game over screen, restart from current level
- **Title screen** — ASCII art title, New Game, Quit
- **Procedural levels** — Random room/corridor generation with guaranteed solvability
- **Secret doors** — Look like walls, open with Space, reveal hidden rooms

### Session: Extended Content
- **More levels** — Expand beyond 3 levels
- **New enemy types** — Rats (fast, low HP), Wraiths (phase through walls)
- **Potions** — Health restore pickups
- **Silver key mechanics** — Separate lock type
- **Score screen** — End-of-game summary (time, treasure, enemies killed)

---

## Adding New Entity Types

1. Add character to `CELL_CHARS` and `ENTITY_CHARS` in `wireframe_engine/level.py`
2. Define wireframe model dict in `bsp_dungeon_gl3d.py` (remember: +Y = up for entities)
3. Add to `ENTITY_MODELS` and `ENTITY_COLORS` dicts
4. Add rendering case in `_draw_entities()` if special handling needed
5. Add interaction logic in `_check_entity_collisions()` if collectible/triggerable
6. Add minimap marker style in `_draw_minimap()` if desired

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

| Session | Version | Features |
|---------|---------|----------|
| 1 | v0.3.0 | BSP tree, OpenGL 3D, depth buffer, wall occlusion |
| 2 | v0.4.0 | Wizard's staff, weapon bob, data-driven levels, entity parsing |
| 3 | v0.5.0 | Entity rendering, doors/keys/locks, treasure, level transitions, three-level campaign, win state |
| Next | v0.6.0 | Combat: enemy AI, spellcasting, health system |