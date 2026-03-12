"""
Castle of Bane - Combat System
------------------------------
Health, spellcasting, enemy AI, projectiles, and visual effects.

All game-layer combat logic lives here. The main renderer calls
update() each tick and queries state for rendering.
"""

import math
import time
from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import Optional

from wireframe_engine.dungeon import DungeonMap, CellType, CELL_SIZE


# ---------------------------------------------------------------------------
# Player Health
# ---------------------------------------------------------------------------

@dataclass
class PlayerHealth:
    hp: int = 100
    max_hp: int = 100
    damage_flash: float = 0.0   # Remaining flash time (seconds)
    invuln_until: float = 0.0   # Invulnerability after taking a hit

    def take_damage(self, amount: int) -> int:
        """Apply damage. Returns actual damage dealt."""
        now = time.time()
        if now < self.invuln_until:
            return 0
        actual = min(amount, self.hp)
        self.hp -= actual
        if actual > 0:
            self.damage_flash = 0.4
            self.invuln_until = now + 0.5
        return actual

    def heal(self, amount: int):
        self.hp = min(self.hp + amount, self.max_hp)

    @property
    def is_dead(self) -> bool:
        return self.hp <= 0

    @property
    def hp_fraction(self) -> float:
        return self.hp / self.max_hp if self.max_hp > 0 else 0.0

    def update(self, dt: float):
        self.damage_flash = max(0.0, self.damage_flash - dt)


# ---------------------------------------------------------------------------
# Projectiles
# ---------------------------------------------------------------------------

@dataclass
class Projectile:
    """A spell bolt fired from the staff."""
    wx: float               # World X position
    wz: float               # World Z position
    angle: float            # Direction in degrees
    speed: float = 8.0      # World units per tick
    lifetime: float = 2.0   # Seconds remaining
    size: float = 4.0       # Collision/render radius
    created: float = field(default_factory=time.time)

    def update(self, dt: float, dungeon: DungeonMap) -> bool:
        """Advance projectile. Returns False if expired or hit wall."""
        self.lifetime -= dt
        if self.lifetime <= 0:
            return False

        rad = math.radians(self.angle)
        self.wx += math.sin(rad) * self.speed
        self.wz -= math.cos(rad) * self.speed

        # Wall collision
        gx, gz = dungeon.world_to_grid(self.wx, self.wz)
        if not dungeon.is_walkable(gx, gz):
            return False
        # Treat closed doors as walls for projectiles
        if dungeon.get_cell(gx, gz) == CellType.DOOR:
            return False

        return True


# Projectile wireframe model (small diamond bolt)
PROJECTILE_MODEL = {
    'lines': [
        # Diamond shape
        ((0, 3, 0), (3, 0, 0)),
        ((3, 0, 0), (0, -3, 0)),
        ((0, -3, 0), (-3, 0, 0)),
        ((-3, 0, 0), (0, 3, 0)),
        # Trailing spikes
        ((0, 0, 3), (0, 3, 0)),
        ((0, 0, 3), (3, 0, 0)),
        ((0, 0, 3), (0, -3, 0)),
        ((0, 0, 3), (-3, 0, 0)),
        # Forward point
        ((0, 0, -4), (0, 3, 0)),
        ((0, 0, -4), (3, 0, 0)),
        ((0, 0, -4), (0, -3, 0)),
        ((0, 0, -4), (-3, 0, 0)),
        # Inner cross
        ((0, -2, 0), (0, 2, 0)),
        ((-2, 0, 0), (2, 0, 0)),
    ],
    'scale': 1.5,
    'color': (0.6, 0.9, 1.0),      # Ice blue (matches crystal)
}


# ---------------------------------------------------------------------------
# Hit / Death Effects
# ---------------------------------------------------------------------------

@dataclass
class HitEffect:
    """Expanding wireframe burst when a projectile hits."""
    wx: float
    wz: float
    age: float = 0.0
    duration: float = 0.3
    max_radius: float = 15.0

    @property
    def alive(self) -> bool:
        return self.age < self.duration

    @property
    def radius(self) -> float:
        return (self.age / self.duration) * self.max_radius

    @property
    def alpha(self) -> float:
        return 1.0 - (self.age / self.duration)

    def update(self, dt: float):
        self.age += dt


@dataclass
class DeathEffect:
    """Wireframe collapse when an enemy dies."""
    wx: float
    wz: float
    entity_type: str = 'skeleton'   # For model lookup by renderer
    model_lines: list = field(default_factory=list)
    age: float = 0.0
    duration: float = 0.8
    color: tuple = (1.0, 1.0, 1.0)

    @property
    def alive(self) -> bool:
        return self.age < self.duration

    @property
    def collapse_factor(self) -> float:
        """1.0 = full size, 0.0 = fully collapsed to ground."""
        return 1.0 - (self.age / self.duration)

    @property
    def alpha(self) -> float:
        return 1.0 - (self.age / self.duration)

    def update(self, dt: float):
        self.age += dt


# ---------------------------------------------------------------------------
# Enemy AI
# ---------------------------------------------------------------------------

class EnemyState(IntEnum):
    IDLE = 0
    ALERT = 1
    CHASE = 2
    ATTACK = 3


@dataclass
class EnemyInfo:
    """Combat state for an enemy entity."""
    entity_ref: object          # Reference to the Entity in the entity list
    state: EnemyState = EnemyState.IDLE
    hp: int = 2
    max_hp: int = 2
    damage: int = 10
    attack_range: float = 1.2   # Grid cells
    sight_range: float = 8.0    # Grid cells
    speed: float = 0.5          # Grid cells per second
    attack_cooldown: float = 0.0
    attack_interval: float = 1.5
    # Movement throttle (grid-step timing)
    move_timer: float = 0.0
    # Sub-cell position for smooth movement (world coords)
    wx: float = 0.0
    wz: float = 0.0
    # Target cell for smooth interpolation
    target_wx: float = 0.0
    target_wz: float = 0.0
    # Alert timer (enemy pauses briefly when spotting player)
    alert_timer: float = 0.0
    alert_duration: float = 0.5
    # LOS check throttle
    los_timer: float = 0.0
    los_interval: float = 0.25  # Only check LOS every 0.25s
    los_cached: bool = False    # Last LOS result


def create_enemy_info(entity, dungeon: DungeonMap) -> EnemyInfo:
    """Create EnemyInfo for an entity based on its type."""
    wx, wz = dungeon.grid_to_world(entity.gx, entity.gz)

    if entity.type == 'ghost':
        return EnemyInfo(
            entity_ref=entity,
            hp=1, max_hp=1,
            damage=15,
            speed=0.7,
            sight_range=10.0,
            attack_interval=1.2,
            wx=wx, wz=wz,
            target_wx=wx, target_wz=wz,
        )
    else:  # skeleton
        return EnemyInfo(
            entity_ref=entity,
            hp=2, max_hp=2,
            damage=10,
            speed=0.4,
            sight_range=7.0,
            attack_interval=1.5,
            wx=wx, wz=wz,
            target_wx=wx, target_wz=wz,
        )


# ---------------------------------------------------------------------------
# Line of Sight (DDA grid raycast)
# ---------------------------------------------------------------------------

def has_line_of_sight(dungeon: DungeonMap, gx1: int, gz1: int,
                      gx2: int, gz2: int) -> bool:
    """
    Check if two grid cells have unobstructed line of sight.
    Uses DDA stepping through grid cells.
    Returns True if no solid cells block the line.
    """
    dx = gx2 - gx1
    dz = gz2 - gz1
    steps = max(abs(dx), abs(dz))
    if steps == 0:
        return True

    x_inc = dx / steps
    z_inc = dz / steps

    x = gx1 + 0.5  # Start from cell center
    z = gz1 + 0.5

    for _ in range(steps):
        x += x_inc
        z += z_inc
        check_gx = int(x)
        check_gz = int(z)

        # Don't check the endpoints
        if check_gx == gx2 and check_gz == gz2:
            return True
        if check_gx == gx1 and check_gz == gz1:
            continue

        if dungeon.is_solid(check_gx, check_gz):
            return False
        # Closed doors block sight
        if dungeon.get_cell(check_gx, check_gz) == CellType.DOOR:
            return False

    return True


# ---------------------------------------------------------------------------
# Pathfinding (BFS through walkable cells)
# ---------------------------------------------------------------------------

def _cell_walkable_for_enemy(dungeon: DungeonMap, gx: int, gz: int,
                             door_open_states: dict) -> bool:
    """Check if an enemy can move into this cell."""
    if not dungeon.is_walkable(gx, gz):
        return False
    if (dungeon.get_cell(gx, gz) == CellType.DOOR and
            not door_open_states.get((gx, gz), False)):
        return False
    return True


# ---------------------------------------------------------------------------
# Staff Animation State
# ---------------------------------------------------------------------------

@dataclass
class StaffState:
    """Tracks staff casting animation."""
    is_casting: bool = False
    cast_timer: float = 0.0
    cast_duration: float = 0.2      # Quick thrust
    cooldown: float = 0.0
    cooldown_duration: float = 0.4  # Time between casts

    @property
    def cast_progress(self) -> float:
        """0.0 = start, 1.0 = fully thrust forward."""
        if not self.is_casting:
            return 0.0
        return min(1.0, self.cast_timer / self.cast_duration)

    def start_cast(self) -> bool:
        """Begin cast animation. Returns True if cast started."""
        if self.cooldown > 0 or self.is_casting:
            return False
        self.is_casting = True
        self.cast_timer = 0.0
        return True

    def update(self, dt: float) -> bool:
        """Update staff state. Returns True when cast completes (spawn projectile)."""
        spawn = False
        self.cooldown = max(0.0, self.cooldown - dt)

        if self.is_casting:
            self.cast_timer += dt
            if self.cast_timer >= self.cast_duration:
                self.is_casting = False
                self.cooldown = self.cooldown_duration
                spawn = True

        return spawn


# ---------------------------------------------------------------------------
# Combat Manager
# ---------------------------------------------------------------------------

class CombatManager:
    """
    Orchestrates all combat systems.

    Call update() each game tick. The main renderer queries state
    for rendering projectiles, effects, HP bar, damage flash.
    """

    def __init__(self):
        self.player_hp = PlayerHealth()
        self.staff = StaffState()
        self.projectiles: list[Projectile] = []
        self.enemies: list[EnemyInfo] = []
        self.hit_effects: list[HitEffect] = []
        self.death_effects: list[DeathEffect] = []
        self.game_over: bool = False
        self._last_time = time.time()

    def init_level(self, entities: list, dungeon: DungeonMap):
        """Set up combat state for a new level. Keeps player HP across levels."""
        self.projectiles.clear()
        self.enemies.clear()
        self.hit_effects.clear()
        self.death_effects.clear()
        self.game_over = False

        for entity in entities:
            if entity.type in ('skeleton', 'ghost'):
                self.enemies.append(create_enemy_info(entity, dungeon))

    def cast_spell(self, cam_x: float, cam_z: float, cam_angle: float) -> bool:
        """Player tries to cast. Returns True if spell fires."""
        return self.staff.start_cast()

    def update(self, cam_x: float, cam_z: float, cam_angle: float,
               dungeon: DungeonMap, entities: list,
               door_open_states: dict) -> dict:
        """
        Update all combat systems for one tick.

        Returns dict of events:
            'spell_fired': bool
            'enemies_killed': list of Entity refs
            'damage_taken': int
            'player_died': bool
        """
        now = time.time()
        dt = min(now - self._last_time, 0.1)  # Cap at 100ms
        self._last_time = now

        events = {
            'spell_fired': False,
            'enemies_killed': [],
            'damage_taken': 0,
            'player_died': False,
        }

        if self.game_over:
            return events

        # --- Staff animation ---
        spawn_projectile = self.staff.update(dt)
        if spawn_projectile:
            events['spell_fired'] = True
            rad = math.radians(cam_angle)
            # Spawn slightly ahead of camera
            spawn_dist = 15.0
            proj = Projectile(
                wx=cam_x + math.sin(rad) * spawn_dist,
                wz=cam_z - math.cos(rad) * spawn_dist,
                angle=cam_angle,
            )
            self.projectiles.append(proj)

        # --- Update projectiles ---
        surviving_projectiles = []
        for proj in self.projectiles:
            if proj.update(dt, dungeon):
                # Check hit against enemies
                hit_enemy = self._check_projectile_hit(proj, dungeon)
                if hit_enemy:
                    self._damage_enemy(hit_enemy, 1, entities, events, dungeon)
                    self.hit_effects.append(HitEffect(wx=proj.wx, wz=proj.wz))
                else:
                    surviving_projectiles.append(proj)
            else:
                # Projectile expired or hit wall — show fizzle
                self.hit_effects.append(HitEffect(
                    wx=proj.wx, wz=proj.wz,
                    duration=0.15, max_radius=8.0
                ))
        self.projectiles = surviving_projectiles

        # --- Update enemies ---
        player_gx, player_gz = dungeon.world_to_grid(cam_x, cam_z)
        for enemy in self.enemies:
            self._update_enemy(enemy, cam_x, cam_z,
                               player_gx, player_gz,
                               dungeon, door_open_states, dt, events)

        # --- Update effects ---
        for effect in self.hit_effects:
            effect.update(dt)
        self.hit_effects = [e for e in self.hit_effects if e.alive]

        for effect in self.death_effects:
            effect.update(dt)
        self.death_effects = [e for e in self.death_effects if e.alive]

        # --- Player HP ---
        self.player_hp.update(dt)
        if self.player_hp.is_dead:
            self.game_over = True
            events['player_died'] = True

        return events

    def _check_projectile_hit(self, proj: Projectile,
                              dungeon: DungeonMap) -> Optional[EnemyInfo]:
        """Check if projectile is close enough to hit an enemy."""
        proj_gx, proj_gz = dungeon.world_to_grid(proj.wx, proj.wz)
        hit_dist_sq = (CELL_SIZE * 0.6) ** 2

        for enemy in self.enemies:
            dx = proj.wx - enemy.wx
            dz = proj.wz - enemy.wz
            if dx * dx + dz * dz < hit_dist_sq:
                return enemy
        return None

    def _damage_enemy(self, enemy: EnemyInfo, amount: int,
                      entities: list, events: dict,
                      dungeon: DungeonMap):
        """Deal damage to an enemy."""
        enemy.hp -= amount

        if enemy.hp <= 0:
            events['enemies_killed'].append(enemy.entity_ref)
            # Spawn death effect
            self._spawn_death_effect(enemy)
            # Remove from our tracking
            self.enemies.remove(enemy)
            # Remove from entity list (stops rendering)
            if enemy.entity_ref in entities:
                entities.remove(enemy.entity_ref)
        else:
            # Getting hit alerts the enemy
            enemy.state = EnemyState.CHASE

    def _spawn_death_effect(self, enemy: EnemyInfo):
        """Create a collapsing wireframe death animation."""
        self.death_effects.append(DeathEffect(
            wx=enemy.wx,
            wz=enemy.wz,
            entity_type=enemy.entity_ref.type,
            color=(1.0, 1.0, 1.0),
        ))

    def _update_enemy(self, enemy: EnemyInfo,
                      cam_x: float, cam_z: float,
                      player_gx: int, player_gz: int,
                      dungeon: DungeonMap,
                      door_open_states: dict,
                      dt: float, events: dict):
        """Update one enemy's AI state machine."""
        entity = enemy.entity_ref
        e_gx, e_gz = dungeon.world_to_grid(enemy.wx, enemy.wz)

        # Squared distance to player in grid cells (avoid sqrt)
        dgx = player_gx - e_gx
        dgz = player_gz - e_gz
        grid_dist_sq = dgx * dgx + dgz * dgz

        enemy.attack_cooldown = max(0.0, enemy.attack_cooldown - dt)

        # Throttled LOS check
        enemy.los_timer = max(0.0, enemy.los_timer - dt)
        if enemy.los_timer <= 0:
            enemy.los_timer = enemy.los_interval
            if grid_dist_sq <= enemy.sight_range * enemy.sight_range:
                enemy.los_cached = has_line_of_sight(
                    dungeon, e_gx, e_gz, player_gx, player_gz)
            else:
                enemy.los_cached = False

        attack_range_sq = enemy.attack_range * enemy.attack_range
        sight_range_sq = enemy.sight_range * enemy.sight_range
        lose_range_sq = (enemy.sight_range * 1.5) ** 2

        # --- State transitions ---
        if enemy.state == EnemyState.IDLE:
            if grid_dist_sq <= sight_range_sq and enemy.los_cached:
                enemy.state = EnemyState.ALERT
                enemy.alert_timer = enemy.alert_duration

        elif enemy.state == EnemyState.ALERT:
            enemy.alert_timer -= dt
            if enemy.alert_timer <= 0:
                enemy.state = EnemyState.CHASE

        elif enemy.state == EnemyState.CHASE:
            if grid_dist_sq <= attack_range_sq:
                enemy.state = EnemyState.ATTACK
            elif grid_dist_sq > lose_range_sq and not enemy.los_cached:
                enemy.state = EnemyState.IDLE

        elif enemy.state == EnemyState.ATTACK:
            if grid_dist_sq > (enemy.attack_range * 1.5) ** 2:
                enemy.state = EnemyState.CHASE

        # --- Actions based on state ---
        if enemy.state == EnemyState.CHASE:
            self._move_enemy(enemy, cam_x, cam_z,
                             player_gx, player_gz,
                             dungeon, door_open_states, dt)

        elif enemy.state == EnemyState.ATTACK:
            if enemy.attack_cooldown <= 0:
                dmg = self.player_hp.take_damage(enemy.damage)
                if dmg > 0:
                    events['damage_taken'] += dmg
                enemy.attack_cooldown = enemy.attack_interval

        # Sync entity grid position from world position
        new_gx, new_gz = dungeon.world_to_grid(enemy.wx, enemy.wz)
        entity.gx = new_gx
        entity.gz = new_gz

    def _move_enemy(self, enemy: EnemyInfo,
                    cam_x: float, cam_z: float,
                    player_gx: int, player_gz: int,
                    dungeon: DungeonMap,
                    door_open_states: dict,
                    dt: float):
        """
        Doom-style greedy movement: try to move toward player,
        if blocked try perpendicular. No pathfinding needed —
        corridors do the funneling naturally.
        """
        # Interpolate toward current target
        dx = enemy.target_wx - enemy.wx
        dz = enemy.target_wz - enemy.wz
        dist_sq = dx * dx + dz * dz

        move_speed = enemy.speed * CELL_SIZE * dt

        if dist_sq > 1.0:
            # Still moving to target cell
            dist = math.sqrt(dist_sq)
            factor = min(1.0, move_speed / dist)
            enemy.wx += dx * factor
            enemy.wz += dz * factor
            return

        # Arrived at target cell — snap and pick next move
        enemy.wx = enemy.target_wx
        enemy.wz = enemy.target_wz

        # Throttle: one grid step per move interval
        enemy.move_timer -= dt
        if enemy.move_timer > 0:
            return
        enemy.move_timer = 1.0 / max(0.1, enemy.speed)

        e_gx, e_gz = dungeon.world_to_grid(enemy.wx, enemy.wz)
        dgx = player_gx - e_gx
        dgz = player_gz - e_gz

        # Determine preferred move directions (primary + perpendicular)
        # Primary: the axis with the greatest distance
        moves = []
        if abs(dgx) >= abs(dgz):
            # Primary: X axis, secondary: Z axis
            sx = 1 if dgx > 0 else -1 if dgx < 0 else 0
            sz = 1 if dgz > 0 else -1 if dgz < 0 else 0
            if sx != 0:
                moves.append((sx, 0))
            if sz != 0:
                moves.append((0, sz))
            # Try opposite perpendicular as last resort
            if sz != 0:
                moves.append((0, -sz))
            if sx != 0:
                moves.append((-sx, 0))
        else:
            # Primary: Z axis, secondary: X axis
            sz = 1 if dgz > 0 else -1 if dgz < 0 else 0
            sx = 1 if dgx > 0 else -1 if dgx < 0 else 0
            if sz != 0:
                moves.append((0, sz))
            if sx != 0:
                moves.append((sx, 0))
            if sx != 0:
                moves.append((-sx, 0))
            if sz != 0:
                moves.append((0, -sz))

        # Try each move direction
        for mx, mz in moves:
            nx, nz = e_gx + mx, e_gz + mz
            if _cell_walkable_for_enemy(dungeon, nx, nz, door_open_states):
                enemy.target_wx, enemy.target_wz = dungeon.grid_to_world(nx, nz)
                return

    def get_enemy_for_entity(self, entity) -> Optional[EnemyInfo]:
        """Look up combat info for an entity."""
        for enemy in self.enemies:
            if enemy.entity_ref is entity:
                return enemy
        return None