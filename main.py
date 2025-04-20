#!/usr/bin/env python
# Jovian Front: Echoes of War  – hard‑sci‑fi space‑combat prototype
# (c) 2025  – public‑domain / CC0

import pygame
import math
import random
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# --- configuration -----------------------------------------------------------
# -----------------------------------------------------------------------------
WIDTH, HEIGHT = 800, 600
FPS = 60

WHITE   = (255, 255, 255)
BLACK   = (0,   0,   0)
RED     = (255, 0,   0)
GREEN   = (0,   255, 0)
BLUE    = (0,   128, 255)
YELLOW  = (255, 255, 0)
ORANGE  = (255, 165, 0)
GREY    = (100, 100, 100)

# player
PLAYER_SIZE            = 26
PLAYER_THRUST          = 0.45
PLAYER_ROT_SPEED       = 4         # deg / frame
PLAYER_MAX_HEAT        = 100
PLAYER_COOL_RATE       = 0.18      # heat / frame
PLAYER_MAX_HP          = 150

# weapons
LASER = dict(speed=11, damage=12, heat=5,  cooldown=0.25, color=YELLOW, size=4)
RAIL  = dict(speed=15, damage=30, heat=15, cooldown=1.0,  color=ORANGE, size=5)
MISS  = dict(speed=5,  damage=60, heat=22, cooldown=2.0,  color=RED,    size=8,
             accel=0.12, lifetime=150)

POINT_DEF_RANGE        = 50
POINT_DEF_COOLDOWN     = 0.12
POINT_DEF_HEAT         = 2
POINT_DEF_SHOTS        = 6

# enemy
ENEMY_SIZE             = 24
ENEMY_SPEED            = 1.3
ENEMY_MAX_HP           = 120
ENEMY_MAX_HEAT         = 80
ENEMY_COOL_RATE        = 0.12
ENEMY_FIRE_COOLDOWN    = 1.4
ENEMY_LASER_HEAT       = 4
ENEMY_LASER_SPEED      = 9
ENEMY_LASER_DAMAGE     = 7

# -----------------------------------------------------------------------------
pygame.init()
pygame.display.set_caption("Jovian Front: Echoes of War – Prototype")
screen      = pygame.display.set_mode((WIDTH, HEIGHT))
screen_rect = screen.get_rect()
clock       = pygame.time.Clock()
FONT_SMALL  = pygame.font.SysFont("consolas,monospace", 14)
FONT_BIG    = pygame.font.SysFont("consolas,monospace", 32, bold=True)

# -----------------------------------------------------------------------------
# --- helpers -----------------------------------------------------------------
# -----------------------------------------------------------------------------
def wrap(sprite):
    """screen‑wrap a sprite rect and sync its float coords"""
    if sprite.rect.left > WIDTH:
        sprite.rect.right = 0
    elif sprite.rect.right < 0:
        sprite.rect.left = WIDTH
    if sprite.rect.top > HEIGHT:
        sprite.rect.bottom = 0
    elif sprite.rect.bottom < 0:
        sprite.rect.top = HEIGHT
    sprite.x, sprite.y = map(float, sprite.rect.center)

def rotate_point(origin, point, angle_deg):
    ox, oy = origin
    px, py = point
    rad = math.radians(angle_deg)
    qx = ox + math.cos(rad) * (px - ox) - math.sin(rad) * (py - oy)
    qy = oy + math.sin(rad) * (px - ox) + math.cos(rad) * (py - oy)
    return qx, qy

# -----------------------------------------------------------------------------
# --- sprite classes ----------------------------------------------------------
# -----------------------------------------------------------------------------
class Projectile(pygame.sprite.Sprite):
    def __init__(self, x, y, angle, spec, owner):
        super().__init__()
        self.spec   = spec
        self.owner  = owner
        self.angle  = angle
        self.speed  = spec["speed"]
        self.damage = spec["damage"]
        size        = spec["size"]
        self.image  = pygame.Surface((size, size))
        self.image.fill(spec["color"])
        self.rect   = self.image.get_rect(center=(int(x), int(y)))
        self.x, self.y = float(x), float(y)
        self.vx = self.speed * math.cos(math.radians(angle - 90))
        self.vy = self.speed * math.sin(math.radians(angle - 90))

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.rect.center = (int(self.x), int(self.y))
        if not screen_rect.colliderect(self.rect):
            self.kill()

class Missile(Projectile):
    def __init__(self, x, y, angle, spec, owner, target_group):
        super().__init__(x, y, angle, spec, owner)
        self.target_group = target_group
        self.accel        = spec["accel"]
        self.lifetime     = spec["lifetime"]

    def acquire_target(self):
        if not self.target_group:
            return None
        # pick closest living sprite
        living = [spr for spr in self.target_group if spr.alive()]
        if not living:
            return None
        return min(living, key=lambda s: math.hypot(s.rect.centerx - self.x,
                                                    s.rect.centery - self.y))

    def update(self):
        if self.lifetime <= 0:
            self.kill()
            return
        self.lifetime -= 1
        target = self.acquire_target()
        if target:
            dx = target.rect.centerx - self.x
            dy = target.rect.centery - self.y
            desired = math.degrees(math.atan2(dy, dx)) + 90
            diff = (desired - self.angle + 540) % 360 - 180
            self.angle += max(-4, min(4, diff))  # turn rate clamp

        # accelerate
        self.vx += self.accel * math.cos(math.radians(self.angle - 90))
        self.vy += self.accel * math.sin(math.radians(self.angle - 90))
        speed = math.hypot(self.vx, self.vy)
        if speed > self.spec["speed"] * 1.8:
            scale = self.spec["speed"] * 1.8 / speed
            self.vx *= scale
            self.vy *= scale

        super().update()

class Spacecraft(pygame.sprite.Sprite):
    def __init__(self, x, y, size, color):
        super().__init__()
        self.size  = size
        self.color = color
        # draw a simple “arrow” triangle
        img = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.polygon(img, color, [(size*0.5, 0),
                                         (size*0.1, size*0.85),
                                         (size*0.9, size*0.85)])
        self.original_image = img
        self.image  = img.copy()
        self.rect   = self.image.get_rect(center=(x, y))
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.angle = 0
        self.rot_speed = 0
        self.heat = 0
        self.max_heat = 100
        self.cool_rate = 0.1
        self.hp   = 100
        self.max_hp = 100

        self.projectiles = pygame.sprite.Group()

        # weapons dict entries: {cooldown, timer}
        self.weapons = {
            "laser":  dict(spec=LASER, timer=0.0),
            "rail":   dict(spec=RAIL,  timer=0.0),
            "miss":   dict(spec=MISS,  timer=0.0),
        }
        self.current_weapon = "laser"

        self.pd_cooldown = 0.0
        self.pd_shots    = POINT_DEF_SHOTS

    # ------------------------------------------------------------------------
    def rotate(self, direction):   # direction: −1 left, +1 right
        self.angle += direction * PLAYER_ROT_SPEED
        self.angle %= 360
        self.image = pygame.transform.rotate(self.original_image, -self.angle)
        old_center = self.rect.center
        self.rect  = self.image.get_rect(center=old_center)

    def apply_thrust(self, thrust):
        if self.is_overheated():
            return
        ax = thrust * math.cos(math.radians(self.angle - 90))
        ay = thrust * math.sin(math.radians(self.angle - 90))
        self.vx += ax
        self.vy += ay
        self.heat += 0.06  # engine heat

    def cooled(self, dt):
        self.heat = max(0, self.heat - self.cool_rate * dt)

    def is_overheated(self):
        return self.heat >= self.max_heat

    # ------------------------------------------------------------------------
    def update(self, dt):
        # position update -----------------------------------------------------
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rect.center = (int(self.x), int(self.y))
        wrap(self)

        # systems -------------------------------------------------------------
        self.cooled(dt)
        for wpn in self.weapons.values():
            wpn["timer"] = max(0, wpn["timer"] - dt)
        self.pd_cooldown = max(0, self.pd_cooldown - dt)

        self.projectiles.update()

    # ------------------------------------------------------------------------
    def fire(self, missile_targets=None):
        wpn = self.weapons[self.current_weapon]
        if wpn["timer"] > 0 or self.is_overheated():
            return
        spec = wpn["spec"]
        # muzzle position (front of ship)
        mx = self.rect.centerx + self.size*0.6*math.cos(math.radians(self.angle - 90))
        my = self.rect.centery + self.size*0.6*math.sin(math.radians(self.angle - 90))

        if self.current_weapon == "miss":
            proj = Missile(mx, my, self.angle, spec, self, missile_targets)
        else:
            proj = Projectile(mx, my, self.angle, spec, self)

        self.projectiles.add(proj)
        self.heat += spec["heat"]
        wpn["timer"] = spec["cooldown"]

    # ------------------------------------------------------------------------
    def point_defence(self, target):
        if self.pd_cooldown > 0 or self.pd_shots <= 0 or self.is_overheated() or not target:
            return
        # fire a green PD shot directly at the projectile
        dx = target.rect.centerx - self.rect.centerx
        dy = target.rect.centery - self.rect.centery
        angle = math.degrees(math.atan2(dy, dx)) + 90
        pd_spec = dict(speed=16, damage=99, heat=POINT_DEF_HEAT,
                       cooldown=0, color=GREEN, size=4)
        pd_proj = Projectile(self.rect.centerx, self.rect.centery, angle, pd_spec, self)
        self.projectiles.add(pd_proj)
        self.heat += POINT_DEF_HEAT
        self.pd_cooldown = POINT_DEF_COOLDOWN
        self.pd_shots -= 1

    def reload_pd(self):
        self.pd_shots = POINT_DEF_SHOTS

# -----------------------------------------------------------------------------
class Player(Spacecraft):
    def __init__(self, x, y):
        super().__init__(x, y, PLAYER_SIZE, BLUE)
        self.max_heat = PLAYER_MAX_HEAT
        self.cool_rate = PLAYER_COOL_RATE
        self.max_hp   = PLAYER_MAX_HP
        self.hp       = PLAYER_MAX_HP

# -----------------------------------------------------------------------------
class Enemy(Spacecraft):
    def __init__(self, x, y, target):
        super().__init__(x, y, ENEMY_SIZE, RED)
        self.speed       = ENEMY_SPEED
        self.target      = target
        self.max_heat    = ENEMY_MAX_HEAT
        self.cool_rate   = ENEMY_COOL_RATE
        self.max_hp      = ENEMY_MAX_HP
        self.hp          = ENEMY_MAX_HP
        # simplify: enemy only has laser
        self.weapons = {
            "laser": dict(spec=dict(speed=ENEMY_LASER_SPEED,
                                    damage=ENEMY_LASER_DAMAGE,
                                    heat=ENEMY_LASER_HEAT,
                                    cooldown=ENEMY_FIRE_COOLDOWN,
                                    color=RED,
                                    size=3),
                          timer=0.0)
        }
        self.current_weapon = "laser"

    # ------------------------------------------------------------------------
    def update(self, dt):
        if self.target and self.target.alive():
            # vector to player
            dx = self.target.rect.centerx - self.rect.centerx
            dy = self.target.rect.centery - self.rect.centery
            desired = math.degrees(math.atan2(dy, dx)) + 90
            diff = (desired - self.angle + 540) % 360 - 180
            self.rotate(1 if diff > 2 else -1 if diff < -2 else 0)

            # thrust gently toward target
            dist = math.hypot(dx, dy)
            if dist > 120:
                self.apply_thrust(self.speed * 0.08 * dt)

            # fire when in arc & range
            if dist < 350 and abs(diff) < 25:
                self.fire()
        else:
            # wander
            if random.random() < 0.01:
                self.rotate(random.choice([-1, 1]))
            self.apply_thrust(self.speed * 0.04 * dt)

        super().update(dt)

# -----------------------------------------------------------------------------
# --- utility draw functions --------------------------------------------------
# -----------------------------------------------------------------------------
def draw_bar(x, y, w, h, frac, col_fg, col_bg):
    pygame.draw.rect(screen, col_bg, (x, y, w, h))
    inner = pygame.Rect(x+1, y+1, int((w-2)*max(0, min(1, frac))), h-2)
    pygame.draw.rect(screen, col_fg, inner)

def draw_ui(player, enemy):
    # health & heat bars (player bottom‑left, enemy bottom‑right)
    bar_w, bar_h, pad = 120, 10, 6
    # player heat
    draw_bar(pad, HEIGHT - pad - bar_h*2, bar_w, bar_h,
             player.heat / player.max_heat, ORANGE, GREY)
    screen.blit(FONT_SMALL.render("heat", True, WHITE),
                (pad + bar_w + 4, HEIGHT - pad - bar_h*2))
    # player hp
    draw_bar(pad, HEIGHT - pad - bar_h, bar_w, bar_h,
             player.hp / player.max_hp, GREEN, GREY)
    screen.blit(FONT_SMALL.render("hull", True, WHITE),
                (pad + bar_w + 4, HEIGHT - pad - bar_h))

    # enemy bars
    draw_bar(WIDTH - pad - bar_w, HEIGHT - pad - bar_h*2,
             bar_w, bar_h, enemy.heat / enemy.max_heat, ORANGE, GREY)
    draw_bar(WIDTH - pad - bar_w, HEIGHT - pad - bar_h,
             bar_w, bar_h, enemy.hp / enemy.max_hp, RED, GREY)

    # weapon & pd status (top‑left)
    wpn_text = f"weapon: {player.current_weapon.upper()}  "
    wpn_text += f"cool: {player.weapons[player.current_weapon]['timer']:.1f}s"
    screen.blit(FONT_SMALL.render(wpn_text, True, WHITE), (pad, pad))

    pd_text = f"PD shots: {player.pd_shots}"
    screen.blit(FONT_SMALL.render(pd_text, True, WHITE), (pad, pad + 16))

# -----------------------------------------------------------------------------
# --- main loop ---------------------------------------------------------------
# -----------------------------------------------------------------------------
def game_loop():
    player = Player(WIDTH//2, HEIGHT//2)
    enemy  = Enemy(random.randint(80, WIDTH-80),
                   random.randint(80, HEIGHT-80),
                   player)

    all_sprites   = pygame.sprite.Group(player, enemy)
    enemy_group   = pygame.sprite.Group(enemy)
    player_group  = pygame.sprite.Group(player)

    # timers
    point_def_reset = 0

    running, victory = True, None
    while running:
        dt = clock.tick(FPS) / 1000.0  # seconds per frame

        # --------------------------------------------------------------------
        # input
        thrusting = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_1:
                    player.current_weapon = "laser"
                elif event.key == pygame.K_2:
                    player.current_weapon = "rail"
                elif event.key == pygame.K_3:
                    player.current_weapon = "miss"
                elif event.key == pygame.K_SPACE:
                    player.fire(missile_targets=enemy_group)
                elif event.key == pygame.K_p:
                    # pick nearest incoming enemy projectile within range
                    incoming = [proj for proj in enemy.projectiles
                                if math.hypot(proj.rect.centerx - player.rect.centerx,
                                              proj.rect.centery - player.rect.centery) < POINT_DEF_RANGE]
                    if incoming:
                        target = min(incoming,
                                     key=lambda pr: math.hypot(pr.rect.centerx - player.rect.centerx,
                                                               pr.rect.centery - player.rect.centery))
                        player.point_defence(target)
                elif event.key == pygame.K_r:
                    player.reload_pd()

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            player.rotate(-1)
        if keys[pygame.K_RIGHT]:
            player.rotate(1)
        if keys[pygame.K_UP]:
            thrusting = True
            player.apply_thrust(PLAYER_THRUST * dt)

        # --------------------------------------------------------------------
        # update sprites
        all_sprites.update(dt)
        player.projectiles.update()
        enemy.projectiles.update()

        # collect projectiles into global lists for collision
        player_bullets = player.projectiles
        enemy_bullets  = enemy.projectiles

        # --------------------------------------------------------------------
        # collisions ----------------------------------------------------------
        # player bullets → enemy
        for bullet in player_bullets:
            if enemy.rect.colliderect(bullet.rect):
                enemy.hp -= bullet.damage
                bullet.kill()
                if enemy.hp <= 0:
                    enemy.kill()
                    victory = True
                    running = False
                    break

        # enemy bullets → player
        for bullet in enemy_bullets:
            if player.rect.colliderect(bullet.rect):
                player.hp -= bullet.damage
                bullet.kill()
                if player.hp <= 0:
                    player.kill()
                    victory = False
                    running = False
                    break

        # PD bullets destroy any enemy bullet they touch
        for pd in [b for b in player_bullets if b.spec["damage"] >= 90]:
            hits = pygame.sprite.spritecollide(pd, enemy_bullets, dokill=True)
            if hits:
                pd.kill()

        # --------------------------------------------------------------------
        # drawing -------------------------------------------------------------
        screen.fill((10, 10, 20))
        all_sprites.draw(screen)
        player.projectiles.draw(screen)
        enemy.projectiles.draw(screen)
        draw_ui(player, enemy)
        pygame.display.flip()

    # ------------------------------------------------------------------------
    # end screen
    if victory is None:   # window closed
        return
    msg = "VICTORY!" if victory else "YOU WERE DESTROYED"
    txt = FONT_BIG.render(msg, True, WHITE)
    rect = txt.get_rect(center=(WIDTH//2, HEIGHT//2))
    screen.blit(txt, rect)
    pygame.display.flip()
    pygame.time.wait(2500)

# -----------------------------------------------------------------------------
if __name__ == "__main__":
    while True:
        game_loop()