"""
Wireframe Engine
----------------
A PyQt6/OpenGL engine for first-person wireframe dungeon crawlers.

Main components:
    - DungeonMap: Grid-based level structure
    - Wall: Wall segment geometry
    - BSPTree: Binary Space Partitioning for efficient rendering
    - create_test_dungeon: Sample dungeon generator
"""

from .dungeon import (
    DungeonMap,
    Wall,
    WallFace,
    CellType,
    CELL_SIZE,
    create_test_dungeon,
)

from .bsp import (
    BSPTree,
    BSPNode,
    build_bsp_from_dungeon,
)

__version__ = "0.3.0"
__all__ = [
    "DungeonMap",
    "Wall",
    "WallFace", 
    "CellType",
    "CELL_SIZE",
    "create_test_dungeon",
    "BSPTree",
    "BSPNode",
    "build_bsp_from_dungeon",
]
