"""
THE JACKAL & THE DRUM
Based on the Panchatantra tale.

A deserted battlefield. You hear a drum — somewhere ahead.
Navigate using the compass and volume meter. Find the source.

Controls:
  WASD / Arrow keys  — move
  L                  — listen carefully (stand still for sharper signal)
  R                  — restart (on win/lose screen)
"""

import pygame
import math
import random
import sys
import time

pygame.init()

# ── Constants ─────────────────────────────────────────────────────────────────

TILE       = 44
COLS, ROWS = 22, 14
MAP_W      = COLS * TILE
MAP_H      = ROWS * TILE
HUD_H      = 130
WIDTH      = MAP_W
HEIGHT     = MAP_H + HUD_H
FPS        = 60

# Terrain
OPEN   = 0   # sand — clear
RUINS  = 1   # stone rubble — echoes, slow
FOREST = 2   # tall grass — dampens sound, good cover
TRENCH = 3   # dug trench — fast, concealed

TERRAIN_COLOR = {
    OPEN:   (194, 171, 120),
    RUINS:  ( 88,  80,  72),
    FOREST: ( 45,  90,  45),
    TRENCH: (101,  67,  33),
}

TERRAIN_SPEED = {OPEN: 1.0, RUINS: 0.55, FOREST: 0.70, TRENCH: 1.25}

# Direction noise per terrain (degrees of error in signal)
TERRAIN_NOISE = {OPEN: 12, RUINS: 38, FOREST: 8, TRENCH: 20}

# Palette
BLACK      = (  0,   0,   0)
WHITE      = (255, 255, 255)
DARK       = ( 18,  18,  18)
GRAY       = (100, 100, 100)
DGRAY      = ( 40,  40,  40)
RED        = (210,  40,  40)
ORANGE     = (220, 130,  20)
YELLOW     = (240, 210,  50)
SAND       = (194, 171, 120)
TAWNY      = (190, 140,  70)   # jackal fur
DRUM_BROWN = (120,  60,  20)


# ── Signal ────────────────────────────────────────────────────────────────────

class Signal:
    def __init__(self, direction: float, volume: float, clarity: float):
        self.direction = direction   # compass degrees (0=N, 90=E, 180=S, 270=W)
        self.volume    = volume      # 0.0–1.0
        self.clarity   = clarity     # 0.0–1.0  (affects needle wobble)


# ── Terrain map ───────────────────────────────────────────────────────────────

def build_map(drum_pos) -> list:
    grid = [[OPEN] * COLS for _ in range(ROWS)]

    # Ruin clusters
    for _ in range(28):
        rx, ry = random.randint(3, COLS-5), random.randint(1, ROWS-2)
        for dy in range(random.randint(1, 3)):
            for dx in range(random.randint(1, 3)):
                r, c = ry+dy, rx+dx
                if 0 <= r < ROWS and 0 <= c < COLS:
                    grid[r][c] = RUINS

    # Forest patches
    for _ in range(14):
        fx, fy = random.randint(3, COLS-5), random.randint(1, ROWS-2)
        for dy in range(random.randint(2, 4)):
            for dx in range(random.randint(2, 5)):
                r, c = fy+dy, fx+dx
                if 0 <= r < ROWS and 0 <= c < COLS:
                    grid[r][c] = FOREST

    # Horizontal trenches
    for _ in range(6):
        ty = random.randint(2, ROWS-3)
        tx = random.randint(2, COLS//2)
        for dx in range(random.randint(3, 8)):
            if tx+dx < COLS:
                grid[ty][tx+dx] = TRENCH

    # Clear spawn area (left edge)
    for dy in range(-2, 3):
        for dx in range(0, 3):
            r, c = ROWS//2+dy, dx
            if 0 <= r < ROWS and 0 <= c < COLS:
                grid[r][c] = OPEN

    # Clear drum area
    dx, dy = drum_pos
    for oy in range(-1, 2):
        for ox in range(-1, 2):
            r, c = dy+oy, dx+ox
            if 0 <= r < ROWS and 0 <= c < COLS:
                grid[r][c] = OPEN

    return grid


# ── Soldier ───────────────────────────────────────────────────────────────────

class Soldier:
    SPEED        = 0.035
    VISION       = 4.5
    ALERT_RISE   = 0.018
    ALERT_DECAY  = 0.004

    def __init__(self, patrol):
        self.patrol    = patrol
        self.idx       = 0
        self.pos       = list(map(float, patrol[0]))
        self.awareness = 0.0
        self.alerted   = False

    def update(self, jpos, jackal_stealth):
        # Patrol
        tx, ty = self.patrol[self.idx]
        dx, dy = tx - self.pos[0], ty - self.pos[1]
        d = math.hypot(dx, dy)
        if d < 0.12:
            self.idx = (self.idx + 1) % len(self.patrol)
        else:
            self.pos[0] += dx/d * self.SPEED
            self.pos[1] += dy/d * self.SPEED

        # Awareness
        dist = math.hypot(jpos[0] - self.pos[0], jpos[1] - self.pos[1])
        if dist < self.VISION * (1 - jackal_stealth * 0.5):
            self.awareness = min(1.0, self.awareness + self.ALERT_RISE)
        else:
            self.awareness = max(0.0, self.awareness - self.ALERT_DECAY)

        self.alerted = self.awareness >= 1.0

    def draw(self, surf):
        px = int(self.pos[0] * TILE + TILE//2)
        py = int(self.pos[1] * TILE + TILE//2)
        color = RED if self.alerted else (170, 55, 55)
        pygame.draw.circle(surf, color, (px, py), 10)
        pygame.draw.circle(surf, (220, 180, 140), (px, py+1), 6)  # head tint
        # Awareness arc
        if self.awareness > 0:
            rect = pygame.Rect(px-18, py-18, 36, 36)
            angle = self.awareness * 2 * math.pi
            try:
                pygame.draw.arc(surf, YELLOW, rect, 0, angle, 3)
            except Exception:
                pass


# ── Jackal ────────────────────────────────────────────────────────────────────

class Jackal:
    BASE_SPEED = 0.09

    def __init__(self):
        self.x       = 0.5
        self.y       = float(ROWS // 2)
        self.health  = 3
        self.listen  = False       # holding L
        self.stealth = 0.0         # 0=visible  1=hidden
        self.facing  = 1           # 1=right  -1=left
        self._hurt_timer = 0.0

    def move(self, dx, dy, grid):
        speed = self.BASE_SPEED * (0.5 if self.listen else 1.0)
        terrain = grid[int(self.y)][int(self.x)]
        speed *= TERRAIN_SPEED[terrain]

        nx = self.x + dx * speed
        ny = self.y + dy * speed
        if 0 <= nx < COLS and 0 <= ny < ROWS:
            self.x, self.y = nx, ny

        if dx > 0: self.facing = 1
        if dx < 0: self.facing = -1

        self.stealth = 0.6 if self.listen else (
            0.3 if grid[int(self.y)][int(self.x)] in (FOREST, TRENCH) else 0.0
        )

    def take_hit(self):
        self.health -= 1
        self._hurt_timer = 0.8

    def update(self, dt):
        if self._hurt_timer > 0:
            self._hurt_timer -= dt

    def draw(self, surf):
        px = int(self.x * TILE)
        py = int(self.y * TILE)
        f  = self.facing

        # Hurt flash
        if self._hurt_timer > 0 and int(self._hurt_timer * 8) % 2 == 0:
            return

        # Body
        pygame.draw.ellipse(surf, TAWNY,         (px+4,  py+10, 32, 18))
        # Belly
        pygame.draw.ellipse(surf, (220, 185, 130), (px+8,  py+16, 20, 10))

        # Head
        hx = px + (f * 20 + (TILE//2 - 10))
        pygame.draw.circle(surf, TAWNY,           (hx,    py+11), 10)
        pygame.draw.circle(surf, (220, 185, 130), (hx+f*2, py+13), 5)

        # Ears
        ear1 = [(hx-3*f, py+4), (hx-8*f, py-4), (hx+2*f, py+2)]
        ear2 = [(hx+3*f, py+4), (hx+7*f, py-5), (hx-1*f, py+2)]
        pygame.draw.polygon(surf, TAWNY,           ear1)
        pygame.draw.polygon(surf, TAWNY,           ear2)

        # Eye
        pygame.draw.circle(surf, BLACK, (hx + f*3, py+10), 2)
        pygame.draw.circle(surf, WHITE, (hx + f*3+1, py+9), 1)

        # Tail
        tail_pts = [
            (px + (TILE//2) - f*14, py+14),
            (px + (TILE//2) - f*20, py+9),
            (px + (TILE//2) - f*24, py+4),
        ]
        pygame.draw.lines(surf, TAWNY, False, tail_pts, 4)

        # Listen indicator
        if self.listen:
            pygame.draw.circle(surf, YELLOW,
                               (hx, py+2), 5, 2)


# ── Drum ──────────────────────────────────────────────────────────────────────

def draw_drum(surf, pos, reveal: bool):
    dx, dy = pos
    px, py = dx * TILE, dy * TILE
    if reveal:
        # Drum body
        pygame.draw.ellipse(surf, DRUM_BROWN, (px+6, py+8, TILE-12, TILE-16))
        pygame.draw.ellipse(surf, (90, 40, 10), (px+6, py+8, TILE-12, TILE-16), 3)
        # Drum skin
        pygame.draw.ellipse(surf, (210, 180, 130), (px+6, py+8, TILE-12, 10))
        # Branch
        pygame.draw.line(surf, (80, 55, 30),
                         (px + TILE//2 - 8, py - 4),
                         (px + TILE//2 + 4, py + 14), 4)


# ── Signal computation ────────────────────────────────────────────────────────

def compute_signal(jx: float, jy: float, drum_pos, grid, listening: bool) -> Signal:
    dx, dy = drum_pos
    ex, ey = dx - jx, dy - jy
    dist = math.hypot(ex, ey)

    # True compass bearing (N=0, clockwise)
    true_deg = (90 - math.degrees(math.atan2(-ey, ex))) % 360

    terrain = grid[int(jy)][int(jx)]
    noise = TERRAIN_NOISE[terrain] * (0.4 if listening else 1.0)
    noisy_dir = (true_deg + random.uniform(-noise, noise)) % 360

    max_dist = math.hypot(COLS, ROWS)
    volume  = max(0.0, 1.0 - (dist / max_dist)) ** 0.6
    clarity = max(0.0, 1.0 - (dist / max_dist) * 1.4)
    if listening:
        clarity = min(1.0, clarity * 1.6)

    return Signal(noisy_dir, volume, clarity)


# ── HUD ───────────────────────────────────────────────────────────────────────

def draw_compass(surf, cx, cy, signal: Signal, wobble: float):
    R = 46
    pygame.draw.circle(surf, DGRAY,  (cx, cy), R)
    pygame.draw.circle(surf, GRAY,   (cx, cy), R, 2)

    for label, deg in [("N", 0), ("E", 90), ("S", 180), ("W", 270)]:
        rad = math.radians(deg - 90)
        lx  = cx + int((R-14) * math.cos(rad))
        ly  = cy + int((R-14) * math.sin(rad))
        t   = FONT_SM.render(label, True, WHITE)
        surf.blit(t, (lx - t.get_width()//2, ly - t.get_height()//2))

    # Needle (shifts with clarity/wobble)
    effective_dir = signal.direction + wobble
    rad = math.radians(effective_dir - 90)
    r = R - 7
    nx  = cx + int(r * math.cos(rad))
    ny  = cy + int(r * math.sin(rad))
    v   = signal.clarity
    col = (int(255*(1-v) + 220*v), int(60*(1-v) + 210*v), int(40*(1-v) + 40*v))
    pygame.draw.line(surf, col, (cx, cy), (nx, ny), 3)
    pygame.draw.circle(surf, col, (nx, ny), 4)

    lab = FONT_SM.render("SIGNAL", True, GRAY)
    surf.blit(lab, (cx - lab.get_width()//2, cy + R + 4))


def draw_volume(surf, x, y, volume: float):
    W, H = 26, 70
    pygame.draw.rect(surf, DGRAY, (x, y, W, H))
    fh  = int(H * volume)
    col = (int(50 + 200*volume), int(160 - 60*volume), 30)
    if fh > 0:
        pygame.draw.rect(surf, col, (x, y + H - fh, W, fh))
    pygame.draw.rect(surf, WHITE, (x, y, W, H), 2)
    lab = FONT_SM.render("VOL", True, GRAY)
    surf.blit(lab, (x, y + H + 4))


def draw_hud(surf, jackal, signal, beat_count, beat_timer, max_beat_interval):
    # Background bar
    pygame.draw.rect(surf, (15, 15, 15), (0, MAP_H, WIDTH, HUD_H))
    pygame.draw.line(surf, GRAY, (0, MAP_H), (WIDTH, MAP_H), 2)

    # Lives
    for i in range(3):
        c = RED if i < jackal.health else DGRAY
        pygame.draw.circle(surf, c, (28 + i*30, MAP_H + 22), 10)
    surf.blit(FONT_SM.render("LIVES", True, GRAY), (14, MAP_H + 36))

    # Beat countdown bar
    bar_x, bar_y = WIDTH - 170, MAP_H + 10
    bar_w, bar_h  = 140, 14
    t_frac = max(0.0, 1.0 - beat_timer / max_beat_interval)
    pygame.draw.rect(surf, DGRAY, (bar_x, bar_y, bar_w, bar_h))
    if bar_w * t_frac > 0:
        pygame.draw.rect(surf, ORANGE, (bar_x, bar_y, int(bar_w * t_frac), bar_h))
    pygame.draw.rect(surf, WHITE, (bar_x, bar_y, bar_w, bar_h), 2)
    surf.blit(FONT_SM.render(f"NEXT BEAT", True, GRAY), (bar_x, bar_y + bar_h + 3))
    surf.blit(FONT_SM.render(f"BEATS: {beat_count}", True, YELLOW), (bar_x, bar_y + bar_h + 20))

    # Compass + volume
    if signal:
        draw_compass(surf, WIDTH//2, MAP_H + 65, signal, 0)
        draw_volume(surf, WIDTH//2 + 65, MAP_H + 28, signal.volume)

    # Controls
    hint = FONT_XS.render("WASD: move   |   L: listen (improves signal)", True, (60, 60, 60))
    surf.blit(hint, (WIDTH//2 - hint.get_width()//2, MAP_H + HUD_H - 18))


# ── Overlays ──────────────────────────────────────────────────────────────────

INTRO_LINES = [
    ("THE JACKAL & THE DRUM",   True,  YELLOW),
    ("",                        False, WHITE),
    ("A deserted battlefield.", False, WHITE),
    ("You hear something —",    False, WHITE),
    ("a sound, somewhere ahead.", False, WHITE),
    ("",                        False, WHITE),
    ("Find the drum.",          False, (180, 180, 180)),
    ("Trust your ears.",        False, (180, 180, 180)),
]

WIN_LINES = [
    ("YOU FOUND IT.",            True,  YELLOW),
    ("",                         False, WHITE),
    ("A drum.",                  False, WHITE),
    ("A branch.",                False, WHITE),
    ("Wind.",                    False, WHITE),
    ("",                         False, WHITE),
    ('"It was never a monster.', False, (180, 180, 180)),
    (' It was just a drum."',    False, (180, 180, 180)),
    ("",                         False, WHITE),
    ("Press R to play again.",   False, GRAY),
]

LOSE_LINES = [
    ("THE JACKAL FALLS.",        True,  RED),
    ("",                         False, WHITE),
    ("Fear won. This time.",     False, (180, 180, 180)),
    ("",                         False, WHITE),
    ("Press R to try again.",    False, GRAY),
]

def draw_overlay(surf, lines):
    ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 210))
    surf.blit(ov, (0, 0))
    y = 130
    for text, big, color in lines:
        font = FONT_BIG if big else FONT_MD
        t    = font.render(text, True, color)
        surf.blit(t, (WIDTH//2 - t.get_width()//2, y))
        y   += (48 if big else 34)


# ── Terrain legend ────────────────────────────────────────────────────────────

def draw_legend(surf):
    items = [
        (OPEN,   "Open field"),
        (RUINS,  "Ruins (echoes)"),
        (FOREST, "Tall grass (clearer)"),
        (TRENCH, "Trench (fast)"),
    ]
    x, y = 8, MAP_H - 22
    for t, label in items:
        pygame.draw.rect(surf, TERRAIN_COLOR[t], (x, y, 12, 12))
        pygame.draw.rect(surf, GRAY, (x, y, 12, 12), 1)
        lbl = FONT_XS.render(label, True, (200, 200, 200))
        surf.blit(lbl, (x + 16, y - 1))
        x  += lbl.get_width() + 36


# ── Fonts (loaded after pygame.init) ─────────────────────────────────────────

FONT_BIG = pygame.font.SysFont("monospace", 30, bold=True)
FONT_MD  = pygame.font.SysFont("monospace", 18)
FONT_SM  = pygame.font.SysFont("monospace", 14)
FONT_XS  = pygame.font.SysFont("monospace", 12)


# ── Game ──────────────────────────────────────────────────────────────────────

class Game:
    BEAT_INTERVAL     = 4.5   # seconds between drum beats
    REVEAL_DIST       = 2.0   # tiles — drum becomes visible
    DAMAGE_COOLDOWN   = 1.2   # seconds between damage ticks

    def __init__(self):
        self.drum_pos  = (random.randint(COLS-5, COLS-2),
                          random.randint(2,       ROWS-3))
        self.grid      = build_map(self.drum_pos)
        self.jackal    = Jackal()
        self.soldiers  = self._make_soldiers()

        self.signal         : Signal | None = None
        self.beat_count     = 0
        self.beat_timer     = 0.0          # time since last beat
        self.signal_age     = 99.0         # seconds since last signal received

        self.beat_flash     = 0.0
        self.dmg_cooldown   = 0.0

        self.state          = "intro"      # intro | playing | won | lost
        self.intro_timer    = 4.0

    def _make_soldiers(self):
        routes = [
            [(5, 2),  (11, 2),  (11, 6),  (5, 6)],
            [(9, 9),  (16, 9),  (16, 12), (9, 12)],
            [(13, 1), (18, 1),  (18, 5),  (13, 5)],
            [(3, 7),  (8,  7),  (8,  11), (3, 11)],
            [(14, 7), (19, 7),  (19, 11), (14, 11)],
        ]
        return [Soldier(r) for r in routes]

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt, keys):
        if self.state == "intro":
            self.intro_timer -= dt
            if self.intro_timer <= 0:
                self.state = "playing"
            return

        if self.state != "playing":
            return

        # Jackal movement
        dx = dy = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:  dx = -1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: dx =  1
        if keys[pygame.K_w] or keys[pygame.K_UP]:    dy = -1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:  dy =  1
        self.jackal.listen = keys[pygame.K_l]
        if dx or dy:
            self.jackal.move(dx, dy, self.grid)

        self.jackal.update(dt)

        # Drum beat
        self.beat_timer  += dt
        self.signal_age  += dt
        if self.beat_timer >= self.BEAT_INTERVAL:
            self.beat_timer = 0.0
            self.beat_count += 1
            self.signal     = compute_signal(
                self.jackal.x, self.jackal.y,
                self.drum_pos, self.grid,
                self.jackal.listen
            )
            self.signal_age = 0.0
            self.beat_flash = 0.5

        if self.beat_flash > 0:
            self.beat_flash = max(0.0, self.beat_flash - dt * 2.2)

        # Soldiers
        self.dmg_cooldown = max(0.0, self.dmg_cooldown - dt)
        for s in self.soldiers:
            s.update((self.jackal.x, self.jackal.y), self.jackal.stealth)
            if s.alerted and self.dmg_cooldown == 0.0:
                d = math.hypot(s.pos[0] - self.jackal.x, s.pos[1] - self.jackal.y)
                if d < 1.2:
                    self.jackal.take_hit()
                    self.dmg_cooldown = self.DAMAGE_COOLDOWN
                    if self.jackal.health <= 0:
                        self.state = "lost"
                    return

        # Win check
        dist = math.hypot(self.drum_pos[0] - self.jackal.x,
                          self.drum_pos[1] - self.jackal.y)
        if dist < 1.3:
            self.state = "won"

    # ── Draw ─────────────────────────────────────────────────────────────────

    def draw(self, surf):
        surf.fill(BLACK)

        # Terrain
        for row in range(ROWS):
            for col in range(COLS):
                t     = self.grid[row][col]
                color = TERRAIN_COLOR[t]
                rect  = (col*TILE, row*TILE, TILE, TILE)
                pygame.draw.rect(surf, color, rect)
                shade = tuple(max(0, c-30) for c in color)
                pygame.draw.rect(surf, shade, rect, 1)

        # Beat flash
        if self.beat_flash > 0:
            ov = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
            ov.fill((255, 210, 60, int(160 * self.beat_flash)))
            surf.blit(ov, (0, 0))

        # Drum (visible only when close)
        dist = math.hypot(self.drum_pos[0] - self.jackal.x,
                          self.drum_pos[1] - self.jackal.y)
        reveal = dist < self.REVEAL_DIST or self.state == "won"
        draw_drum(surf, self.drum_pos, reveal)

        # Soldiers
        for s in self.soldiers:
            s.draw(surf)

        # Jackal
        self.jackal.draw(surf)

        # Terrain legend
        draw_legend(surf)

        # HUD
        sig = self.signal if self.signal_age < 3.5 else None
        draw_hud(surf, self.jackal, sig, self.beat_count,
                 self.beat_timer, self.BEAT_INTERVAL)

        # Overlays
        if self.state == "intro":
            draw_overlay(surf, INTRO_LINES)
        elif self.state == "won":
            draw_overlay(surf, WIN_LINES)
        elif self.state == "lost":
            draw_overlay(surf, LOSE_LINES)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("The Jackal & The Drum — Panchatantra")
    clock  = pygame.time.Clock()
    game   = Game()

    while True:
        dt   = clock.tick(FPS) / 1000.0
        keys = pygame.key.get_pressed()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and game.state in ("won", "lost"):
                    game = Game()

        game.update(dt, keys)
        game.draw(screen)
        pygame.display.flip()


if __name__ == "__main__":
    main()
