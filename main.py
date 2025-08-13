
# main.py — Web-ready (pygbag) version using local assets
# - Async frame loop (await asyncio.sleep(0))
# - No network requests; loads from ./assets/
# - One US rooftop flag
# - Logo slides up at 10s, then BAKED into background to avoid FPS cost

import asyncio, sys, math, random, time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pygame

IS_WEB = (sys.platform == "emscripten")

# ---------- Config ----------
TARGET_FPS = 60
CITY_FRACTION = 0.30
PLANE_MAX_SIDE = 150
MAX_PLANES = 9
BOMB_RATE = (1.0, 2.0)
GRAVITY = 280.0
MAX_BOMBS = 30
EXPLOSION_TIME = 0.60
STAR_COUNT = 100

SHAKE_DURATION = 0.30
SHAKE_STRENGTH = 9
MAX_SMOKE = 220
MAX_FIRES = 18

AA_SPAWN_RATE = 1.2
AA_BATTERIES = 3
AA_MAX_SHOTS = 6
AA_MIN_ALT_FRAC = 0.22
AA_MAX_ALT_FRAC = 0.55
AA_SMOKE_PUFFS = (7, 11)
AA_PUFF_VY = (-36.0, -14.0)
AA_PUFF_R0 = (4.5, 8.0)
AA_PUFF_DR = (14.0, 22.0)
AA_PUFF_ALPHA0 = (120.0, 160.0)
AA_PUFF_DA = (130.0, 190.0)
AA_PUFF_SPREAD = 18.0

# ---------- Asset paths (local only) ----------
# Exactly 5 planes: plane1.png is PNG; others are JPG
PLANE_FILES = [
    ("assets/plane1.png", True),   # PNG with alpha
    ("assets/plane2.jpg", False),
    ("assets/plane3.jpg", False),
    ("assets/plane4.jpg", False),
    ("assets/plane5.jpg", False),
]

US_FLAG_FILE = "assets/us_flag.png"
FONT_FILE = "assets/Military.ttf"  # optional

# ---------- Helpers ----------
def load_surface(path: str, has_alpha: bool, max_side: Optional[int] = None) -> pygame.Surface:
    try:
        img = pygame.image.load(path)
        img = img.convert_alpha() if has_alpha else img.convert()
    except Exception:
        # Fallback box
        img = pygame.Surface((120, 40), pygame.SRCALPHA if has_alpha else 0)
        img.fill((200, 200, 200, 200) if has_alpha else (200,200,200))
        if has_alpha:
            img = img.convert_alpha()
        else:
            img = img.convert()

    if max_side:
        w, h = img.get_size()
        s = min(1.0, max_side / max(w, h))
        if s < 1.0:
            img = pygame.transform.smoothscale(img, (int(w*s), int(h*s)))
    return img

@dataclass
class Building:
    left: int
    right: int
    rect_top: int
    base_line_y: int
    has_peak: bool
    peak_x: int
    peak_y: int

def prerender_background(sw: int, sh: int) -> Tuple[pygame.Surface, int, List[Tuple[int,int]], List[Building]]:
    bg = pygame.Surface((sw, sh), pygame.SRCALPHA)

    # Night gradient
    top, bot = (5,10,20), (15,25,40)
    for y in range(sh):
        t = y/max(sh-1,1)
        col = (int(top[0]*(1-t)+bot[0]*t),
               int(top[1]*(1-t)+bot[1]*t),
               int(top[2]*(1-t)+bot[2]*t))
        pygame.draw.line(bg, col, (0,y), (sw,y))

    # Stars
    rng = random.Random(99)
    for _ in range(STAR_COUNT):
        x = rng.randint(0, sw-1); y = rng.randint(0, int(sh*0.7))
        s = rng.randint(1,2)
        pygame.draw.rect(bg, (230,230,255), (x,y,s,s))

    # Moon
    r = int(min(sw,sh)*0.05)
    moon = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
    pygame.draw.circle(moon, (240,240,220,220), (r,r), r)
    pygame.draw.circle(moon, (240,240,220,150), (r-4,r-6), int(r*0.85))
    bg.blit(moon, (int(sw*0.82)-r, int(sh*0.18)-r))

    # City
    city_h = int(sh*CITY_FRACTION)
    y_base = sh - city_h
    rng = random.Random(42)
    x = 0
    damage_spots: List[Tuple[int,int]] = []
    buildings: List[Building] = []
    while x < sw:
        bw = rng.randint(int(sw*0.04), int(sw*0.08))
        bh = rng.randint(int(city_h*0.4), city_h)
        left = x; top = y_base + (city_h - bh)
        shade = rng.randint(18,34)
        pygame.draw.rect(bg, (shade,shade,shade), pygame.Rect(left, top, bw, bh))
        has_peak = rng.random() < 0.5
        base_line_y = top + 6
        peak_x = left + bw//2
        peak_y = top - int(bh*0.18)
        if has_peak:
            pygame.draw.polygon(bg, (shade,shade,shade),
                                [(left, base_line_y), (peak_x, peak_y), (left+bw, base_line_y)])
        # windows
        win = pygame.Surface((bw,bh), pygame.SRCALPHA)
        for yy in range(12, bh-6, 12):
            for xx in range(6, bw-4, 12):
                if rng.random()<0.035:
                    pygame.draw.rect(win, (255,210,130, rng.randint(130,170)), (xx,yy,3,5), border_radius=1)
        bg.blit(win, (left, top))
        # damage
        if rng.random()<0.75:
            for _ in range(rng.randint(1,3)):
                hx = rng.randint(left+6, left+bw-6)
                hy = rng.randint(top+8, top+bh-8)
                rr = rng.randint(6,12)
                pygame.draw.circle(bg, (0,0,0), (hx,hy), rr)
                for k in range(1,4):
                    pygame.draw.circle(bg, (10,10,10,60//k), (hx,hy), rr+2*k, 1)
                if rng.random()<0.8:
                    damage_spots.append((hx, hy-2))
        buildings.append(Building(left, left+bw, top, base_line_y, has_peak, peak_x, peak_y))
        x += bw + rng.randint(int(sw*0.006), int(sw*0.018))

    try: bg = bg.convert()
    except Exception: pass

    random.shuffle(damage_spots)
    return bg, y_base, damage_spots[:20], buildings

def roofline_y_for_x(x: int, buildings: List[Building], default_y: int) -> int:
    for b in buildings:
        if b.left <= x <= b.right:
            if not b.has_peak:
                return b.rect_top
            if x <= b.peak_x:
                frac = (x - b.left) / max(1, b.peak_x - b.left)
                return int(b.base_line_y - frac * (b.base_line_y - b.peak_y))
            frac = (b.right - x) / max(1, b.right - b.peak_x)
            return int(b.base_line_y - frac * (b.base_line_y - b.peak_y))
    return default_y

# ---------- Entities ----------
@dataclass
class Bomb:
    x: float; y: float; vy: float
    exploded: bool=False; start: float=0.0; hit_y: float=0.0

@dataclass
class Plane:
    img: pygame.Surface; x: float; y: float; vx: float
    next_bomb: float; original_facing: str
    vy: float = 0.0
    angle: float = 0.0
    spin: float = 0.0
    on_fire: bool = False
    dying: bool = False
    invuln_until: float = 0.0

@dataclass
class Smoke:
    x: float; y: float; r: float; vy: float; a: float
    tone: int = 125

@dataclass
class Fire:
    x: float; y: float; base_r: float; phase: float

@dataclass
class AAShot:
    x: float; y: float; vx: float; vy: float; target_y: float; alive: bool=True

@dataclass
class AABurst:
    x: float; y: float; start: float; radius: float

# ---------- Effects ----------
def draw_explosion(surface: pygame.Surface, cx: int, cy: int, t: float):
    R = int(36 + 140*(1-t))
    a = int(255*(1-t))
    pygame.draw.circle(surface, (255,205,95,int(a*0.85)), (cx,cy), int(R*0.85))
    pygame.draw.circle(surface, (255,160,70,int(a*0.7)), (cx,cy), int(R*0.6))
    pygame.draw.circle(surface, (255,110,45,int(a*0.55)), (cx,cy), int(R*0.38))
    pygame.draw.circle(surface, (255,240,170,int(a*0.9)), (cx,cy), int(R*0.28))
    pygame.draw.circle(surface, (60,60,60,int(a*0.6)), (cx,cy), R, 3)

def draw_beam(screen, base_xy, angle_deg, length, width,
              alpha_outer=70, alpha_core=110, core_scale=0.42):
    x0, y0 = base_xy
    ang = math.radians(angle_deg)
    dx, dy = math.cos(ang), math.sin(ang)
    x1, y1 = x0 + dx*length, y0 + dy*length
    px, py = -dy, dx
    hw  = width * 0.5
    chw = hw * core_scale
    p1 = (int(x0 + px*hw),  int(y0 + py*hw))
    p2 = (int(x0 - px*hw),  int(y0 - py*hw))
    p3 = (int(x1 - px*hw),  int(y1 - py*hw))
    p4 = (int(x1 + px*hw),  int(y1 + py*hw))
    pygame.draw.polygon(screen, (235,235,255, alpha_outer), (p1,p2,p3,p4))
    c1 = (int(x0 + px*chw), int(y0 + py*chw))
    c2 = (int(x0 - px*chw), int(y0 - py*chw))
    c3 = (int(x1 - px*chw), int(y1 - py*chw))
    c4 = (int(x1 + px*chw), int(y1 + py*chw))
    pygame.draw.polygon(screen, (240,240,255, alpha_core), (c1,c2,c3,c4))

# ---------- Logo (slide-up, then bake) ----------
def try_load_font(size: int) -> pygame.font.Font:
    # Prefer bundled TTF if present
    try:
        return pygame.font.Font(FONT_FILE, size)
    except Exception:
        pass
    # Fallback to system stencil-ish fonts
    for name in ["stencil", "impact", "arialblack"]:
        try:
            return pygame.font.SysFont(name, size)
        except Exception:
            pass
    return pygame.font.SysFont(None, size)

def build_logo_card(sw: int, sh: int) -> Tuple[pygame.Surface, pygame.Rect]:
    big_size = max(36, int(sw*0.085))
    small_size = max(28, int(sw*0.065))
    big_font = try_load_font(big_size)
    small_font = try_load_font(small_size)
    title = "Zombie Bazi:"
    subtitle = "World war 2"
    bw = min(int(sw*0.9), 820)
    bh = min(int(sh*0.28), 240)
    surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
    pygame.draw.rect(surf, (0,0,0,140), (0,0,bw,bh), border_radius=18)
    t1 = big_font.render(title, True, (235,235,230))
    t2 = small_font.render(subtitle, True, (255,210,120))
    surf.blit(t1, (bw//2 - t1.get_width()//2, bh//2 - t1.get_height()))
    surf.blit(t2, (bw//2 - t2.get_width()//2, bh//2 + 12))
    try: surf = surf.convert_alpha()
    except Exception: pass
    rect = surf.get_rect()
    rect.centerx = sw // 2
    return surf, rect

# ---------- Main async game ----------
async def game():
    pygame.init()

    # Windowed canvas; pygbag scales it to browser window
    screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE | pygame.DOUBLEBUF)
    clock = pygame.time.Clock()

    # Load assets (local only; one PNG + four JPGs)
    plane_sprites: List[pygame.Surface] = []
    for path, has_alpha in PLANE_FILES:
        surf = load_surface(path, has_alpha, max_side=PLANE_MAX_SIDE)
        plane_sprites.append(surf)

    try:
        flag_img = load_surface(US_FLAG_FILE, True, max_side=max(44, int(min(*screen.get_size()) * 0.06)))
    except Exception:
        flag_img = None

    sw, sh = screen.get_size()
    bg, city_base_y, damage_spots, buildings = prerender_background(sw, sh)
    bg_with_logo = None
    using_baked_logo = False
    ground_y = sh - 2

    rng = random.Random(7)
    lanes = [sh*0.2, sh*0.28, sh*0.36]

    # Planes both directions
    planes: List[Plane] = []
    for i in range(min(MAX_PLANES, max(len(plane_sprites), MAX_PLANES))):
        img = plane_sprites[i % len(plane_sprites)]
        dir_right = (i % 2 == 0)
        speed = rng.uniform(sw*0.06, sw*0.10) * (1 if dir_right else -1)
        y = rng.choice(lanes)
        x = (-img.get_width() - rng.uniform(40,260)) if dir_right else (sw + rng.uniform(40,260))
        planes.append(Plane(img, x, y, speed, time.time()+rng.uniform(*BOMB_RATE), "left"))

    bombs: List[Bomb] = []
    smokes: List[Smoke] = []
    fires: List[Fire] = [Fire(x=sx+rng.uniform(-2,2),
                              y=sy+rng.uniform(-2,2),
                              base_r=rng.uniform(4,8),
                              phase=rng.uniform(0, math.tau))
                         for sx, sy in damage_spots[:MAX_FIRES]]

    # AA
    aa_bases = []
    if AA_BATTERIES > 0:
        step = sw // (AA_BATTERIES + 1)
        for i in range(1, AA_BATTERIES+1):
            aa_bases.append((i*step, city_base_y+2))
    aa_next_fire = [time.time() + rng.uniform(0.4, 1.1) for _ in aa_bases]
    aa_shots: List[AAShot] = []
    aa_bursts: List[AABurst] = []

    # Searchlights
    s_bases = [(int(sw*0.15), sh-2), (int(sw*0.50), sh-2), (int(sw*0.85), sh-2)]
    sl_phase = [rng.uniform(0, math.tau) for _ in s_bases]
    sl_speed = [0.50 + 0.25*i + rng.uniform(-0.08, 0.08) for i in range(len(s_bases))]
    sl_amp   = [14 + i*1.5 + rng.uniform(-2.0, 2.0) for i in range(len(s_bases))]

    # Flag anchor (US only)
    flag_anchor = None
    if flag_img is not None:
        xmid = int(sw * 0.5)
        roof_y = roofline_y_for_x(xmid, buildings, city_base_y)
        yflag = int(roof_y - flag_img.get_height() + 2)
        shadow = pygame.Surface(flag_img.get_size(), pygame.SRCALPHA); shadow.fill((0,0,0,95))
        try: shadow = shadow.convert_alpha()
        except Exception: pass
        flag_anchor = dict(x=xmid, y=yflag, roof_y=roof_y, img=flag_img, shadow=shadow, sway_seed=rng.uniform(0,1000))

    # Logo card (pre-rendered)
    logo_card, logo_rect = build_logo_card(sw, sh)
    logo_center_y = sh // 2
    logo_start_y  = sh + logo_rect.height // 2 + 20
    logo_rect.center = (sw // 2, logo_start_y)
    logo_show_time = time.time() + 10.0
    logo_slide_dur = 1.4
    logo_active = False
    logo_parked = False

    shake_until = 0.0; shake_strength = 0.0
    show_fps = False
    font = pygame.font.SysFont(None, 20)

    running = True
    while running:
        dt = clock.tick(TARGET_FPS)/1000.0
        now = time.time()

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif e.key == pygame.K_f:
                    show_fps = not show_fps
            elif e.type == pygame.VIDEORESIZE:
                sw, sh = e.w, e.h
                screen = pygame.display.set_mode((sw, sh), pygame.RESIZABLE | pygame.DOUBLEBUF)
                bg, city_base_y, damage_spots, buildings = prerender_background(sw, sh)
                lanes = [sh*0.2, sh*0.28, sh*0.36]
                s_bases = [(int(sw*0.15), sh-2), (int(sw*0.50), sh-2), (int(sw*0.85), sh-2)]
                aa_bases = []
                if AA_BATTERIES > 0:
                    step = sw // (AA_BATTERIES + 1)
                    for i in range(1, AA_BATTERIES+1):
                        aa_bases.append((i*step, city_base_y+2))
                aa_next_fire = [now + random.uniform(0.4,1.1) for _ in aa_bases]
                # resize flag
                try:
                    flag_img = load_surface(US_FLAG_FILE, True, max_side=max(44, int(min(sw, sh) * 0.06)))
                except Exception:
                    flag_img = None
                flag_anchor = None
                if flag_img is not None:
                    xmid = int(sw * 0.5)
                    roof_y = roofline_y_for_x(xmid, buildings, city_base_y)
                    yflag = int(roof_y - flag_img.get_height() + 2)
                    shadow = pygame.Surface(flag_img.get_size(), pygame.SRCALPHA); shadow.fill((0,0,0,95))
                    try: shadow = shadow.convert_alpha()
                    except Exception: pass
                    flag_anchor = dict(x=xmid, y=yflag, roof_y=roof_y, img=flag_img, shadow=shadow, sway_seed=random.uniform(0,1000))
                # rebuild logo card placement
                logo_card, logo_rect = build_logo_card(sw, sh)
                logo_center_y = sh // 2
                logo_start_y  = sh + logo_rect.height // 2 + 20
                if logo_parked:
                    logo_rect.center = (sw // 2, logo_center_y)
                else:
                    logo_rect.center = (sw // 2, logo_start_y)
                bg_with_logo = None
                using_baked_logo = False

        # Trigger logo slide
        if not logo_active and not logo_parked and now >= logo_show_time:
            logo_active = True
            logo_anim_start = now

        # Planes
        for p in planes:
            if p.dying:
                p.vy += GRAVITY*dt*0.6
                p.y  += p.vy*dt
                p.x  += p.vx*dt*0.5
                p.angle += p.spin*dt
                if random.random()<0.6:
                    smokes.append(Smoke(p.x + p.img.get_width()/2 + random.uniform(-8,8),
                                        p.y + p.img.get_height()/2 + random.uniform(-8,8),
                                        r=random.uniform(3.5,6.5),
                                        vy=random.uniform(-24,-8),
                                        a=random.uniform(110,150),
                                        tone=random.randint(60,90)))
                if p.y > sh + 120:
                    img = p.img
                    dir_right = (p.vx > 0)
                    p.on_fire = p.dying = False
                    p.vy = p.angle = p.spin = 0.0
                    p.invuln_until = 0.0
                    p.y = random.choice(lanes)
                    p.x = -img.get_width() - random.uniform(40,260) if dir_right else (sw + random.uniform(40,260))
            else:
                p.x += p.vx*dt

            if now >= p.next_bomb and not p.dying and len(bombs) < MAX_BOMBS:
                bombs.append(Bomb(p.x + p.img.get_width()/2,
                                  p.y + p.img.get_height()*0.85,
                                  160.0, False, now, sh-2))
                p.next_bomb = now + random.uniform(*BOMB_RATE)

            if not p.dying:
                if p.vx > 0 and p.x > sw + 60:
                    p.x = -p.img.get_width() - random.uniform(40,260); p.y = random.choice(lanes)
                elif p.vx < 0 and p.x + p.img.get_width() < -60:
                    p.x = sw + random.uniform(40,260); p.y = random.choice(lanes)

        # Bombs
        new_bombs=[]
        for b in bombs:
            if not b.exploded:
                b.vy += GRAVITY*dt
                b.y  += b.vy*dt
                if b.y >= b.hit_y:
                    b.exploded = True; b.start = now
                    shake_until = now + SHAKE_DURATION
                    shake_strength = min(SHAKE_STRENGTH, shake_strength + SHAKE_STRENGTH*0.6)
                new_bombs.append(b)
            else:
                if (now - b.start) < EXPLOSION_TIME:
                    new_bombs.append(b)
        bombs = new_bombs

        # AA spawn/update
        for i, base in enumerate(aa_bases):
            if now >= aa_next_fire[i] and len(aa_shots) < AA_MAX_SHOTS:
                top_alt  = int(sh*AA_MIN_ALT_FRAC)
                bot_alt  = int(sh*AA_MAX_ALT_FRAC)
                burst_y  = random.randint(top_alt, bot_alt)
                vx = random.uniform(-100.0, 100.0)
                vy = -500.0 - random.uniform(0,120)
                aa_shots.append(AAShot(x=base[0]+random.uniform(-6,6),
                                       y=base[1], vx=vx, vy=vy,
                                       target_y=burst_y, alive=True))
                aa_next_fire[i] = now + random.uniform(AA_SPAWN_RATE*0.8, AA_SPAWN_RATE*1.3)

        new_shots=[]; aa_bursts=[]
        for s in aa_shots:
            if s.alive:
                s.x += s.vx*dt; s.y += s.vy*dt
                if s.y <= s.target_y or s.y < 20:
                    s.alive=False
                    aa_bursts.append(AABurst(s.x, s.y, now, radius=48))
                    n = random.randint(*AA_SMOKE_PUFFS)
                    for _ in range(n):
                        ox = random.uniform(-AA_PUFF_SPREAD, AA_PUFF_SPREAD)
                        oy = random.uniform(-AA_PUFF_SPREAD*0.6, AA_PUFF_SPREAD*0.6)
                        smokes.append(Smoke(
                            x=s.x+ox, y=s.y+oy,
                            r=random.uniform(*AA_PUFF_R0),
                            vy=random.uniform(*AA_PUFF_VY),
                            a=random.uniform(*AA_PUFF_ALPHA0),
                            tone=random.randint(45,75)
                        ))
                else:
                    new_shots.append(s)
        aa_shots = new_shots[:AA_MAX_SHOTS]

        # AA burst → plane hit (short window)
        hit_window = 0.18
        for burst in aa_bursts:
            if now - burst.start > hit_window: continue
            bx, by, R = burst.x, burst.y, burst.radius
            R2 = R*R
            for p in planes:
                if p.dying or now < p.invuln_until: continue
                cx = p.x + p.img.get_width()/2
                cy = p.y + p.img.get_height()/2
                if (cx-bx)*(cx-bx) + (cy-by)*(cy-by) <= R2:
                    shake_until = max(shake_until, now + 0.22)
                    p.on_fire = True; p.dying = True
                    p.vy = -60.0
                    p.spin = random.uniform(-2.5, 2.5)
                    p.vx *= 0.65
                    p.invuln_until = now + 2.0
                    break

        # Smoke update
        new_smoke=[]
        for s in smokes:
            s.y += s.vy*dt
            s.r += random.uniform(AA_PUFF_DR[0], AA_PUFF_DR[1]) * dt
            s.a -= random.uniform(AA_PUFF_DA[0], AA_PUFF_DA[1]) * dt
            if s.a > 6: new_smoke.append(s)
        smokes = new_smoke[-MAX_SMOKE:]

        # Shake
        ox=oy=0
        if now < shake_until:
            t = (shake_until-now)/SHAKE_DURATION
            mag = shake_strength*t
            ox = int(random.uniform(-mag, mag))
            oy = int(random.uniform(-mag, mag))

        # ---------- DRAW ----------
        if using_baked_logo and bg_with_logo is not None:
            screen.blit(bg_with_logo, (ox, oy))
        else:
            screen.fill((0,0,0))
            screen.blit(bg, (ox, oy))

        # Searchlights
        beam_len = int(sh * 1.08)
        beam_w   = int(min(sw, sh) * 0.07)
        for i, base in enumerate(s_bases):
            sl_phase[i] += dt * sl_speed[i]
            ang = -90 + math.sin(sl_phase[i] + math.pi) * sl_amp[i]
            draw_beam(screen, (base[0]+ox, base[1]+oy), ang,
                      length=beam_len, width=beam_w,
                      alpha_outer=70, alpha_core=110, core_scale=0.42)
            pygame.draw.rect(screen, (40,40,48), (base[0]-6+ox, base[1]-8+oy, 12, 8))

        # Fires
        for f in fires:
            f.phase = (f.phase + dt*6.0) % math.tau
            size = f.base_r * (1.0 + 0.25*math.sin(f.phase) + 0.08*math.sin(3*f.phase))
            cx, cy = int(f.x)+ox, int(f.y)+oy
            pygame.draw.circle(screen, (255,120,40,80), (cx,cy), int(size*2.2))
            pygame.draw.circle(screen, (255,160,60,160), (cx,cy), int(size*1.5))
            pygame.draw.circle(screen, (255,200,110,180), (cx,cy), int(size*1.1))
            pygame.draw.circle(screen, (255,240,170,200), (cx,cy), max(1,int(size*0.7)))

        # Smoke draw
        for s in smokes:
            tone = max(30, min(200, s.tone))
            pygame.draw.circle(screen, (tone,tone,tone,int(s.a)), (int(s.x)+ox, int(s.y)+oy), int(s.r))

        # Bombs/explosions
        for b in bombs:
            if not b.exploded:
                pygame.draw.circle(screen, (225,225,235), (int(b.x)+ox, int(b.y)+oy), 2)
                pygame.draw.circle(screen, (40,40,40), (int(b.x)+ox, int(b.y)+oy), 4, 1)
            else:
                t = (now - b.start)/EXPLOSION_TIME
                if t <= 1.0:
                    draw_explosion(screen, int(b.x)+ox, int(b.hit_y)+oy, t)

        # Planes
        for p in planes:
            img = p.img
            flip = (p.vx > 0)  # assume original facing left
            if flip: img = pygame.transform.flip(img, True, False)
            if p.dying or p.angle != 0.0:
                rot_img = pygame.transform.rotozoom(img, -math.degrees(p.angle), 1.0)
                screen.blit(rot_img, (int(p.x)+ox, int(p.y)+oy))
            else:
                screen.blit(img, (int(p.x)+ox, int(p.y)+oy))

        # US Flag
        if flag_anchor is not None:
            wobble = math.sin((now*0.9) + flag_anchor["sway_seed"]) * 3.0
            px = int(flag_anchor["x"]) + ox
            py = int(flag_anchor["y"] + wobble) + oy
            pole_x = px - flag_anchor["img"].get_width()//2
            pole_bottom_y = flag_anchor["roof_y"] + oy + 1
            pygame.draw.line(screen, (220,220,230), (pole_x, pole_bottom_y), (pole_x, py), 3)
            screen.blit(flag_anchor["shadow"], (px - flag_anchor["img"].get_width()//2 + 2, py + 2))
            screen.blit(flag_anchor["img"], (px - flag_anchor["img"].get_width()//2, py))

        # Logo slide, then bake
        if not logo_parked and now >= logo_show_time:
            if not logo_active:
                logo_active = True
                logo_anim_start = now
            t = (now - logo_anim_start) / logo_slide_dur
            if t >= 1.0:
                logo_rect.center = (sw//2, logo_center_y)
                logo_parked = True
                logo_active = False
                # bake once
                bg_with_logo = bg.copy()
                bg_with_logo.blit(logo_card, logo_rect.topleft)
                try: bg_with_logo = bg_with_logo.convert()
                except Exception: pass
                using_baked_logo = True
            else:
                ease = 1 - (1 - t) ** 3
                cur_y = int(logo_start_y + (logo_center_y - logo_start_y) * ease)
                logo_rect.center = (sw//2, cur_y)

        if not using_baked_logo and now >= logo_show_time:
            screen.blit(logo_card, logo_rect.topleft)

        if show_fps:
            fps_text = font.render(f"{clock.get_fps():.0f} FPS", True, (220,220,230))
            screen.blit(fps_text, (12, 10))

        pygame.display.flip()

        # Yield to browser (pygbag requirement)
        await asyncio.sleep(0)

def main():
    asyncio.run(game())

if __name__ == "__main__":
    main()
