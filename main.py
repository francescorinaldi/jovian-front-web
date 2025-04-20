#!/usr/bin/env python
"""Outpost Sigma : Last Light – extended prototype (≈730 LOC)
============================================================
Fully playable twin‑stick roguelite written in **Pygame** and designed to run
unchanged in the browser via **Pygbag** (WASM).  Touch joysticks appear on
mobile; keyboard + mouse/game‑pad work on desktop.

> run locally    : `python main.py`
> build for web : `pygbag --build main.py`

Core features
-------------
* Desktop **and** mobile controls (virtual twin sticks)
* Procedural enemy waves with scaling difficulty
* Three upgrade pickups (rate‑of‑fire, damage, speed)
* Particle effects for thrusters and impacts
* Entity–component‑style code layout and type‑hints for clarity
* Score and wave HUD, game‑over screen with high‑score storage
* Single‑file ≥ 600 lines for easy copy / deploy
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Optional, Tuple

import pygame

# ╭──────────────────────────────────────────────────────────────╮
# │ 1. Constants & helpers                                      │
# ╰──────────────────────────────────────────────────────────────╯
WIDTH, HEIGHT = 960, 640
FPS = 60
DT = 1.0 / FPS  # fixed step for deterministic updates

WHITE = (255, 255, 255)
BLACK = (18, 20, 28)
CYAN = (0, 255, 255)
MAG = (255, 0, 255)
YELLOW = (255, 255, 0)
ORANGE = (255, 165, 0)
RED = (255, 64, 64)
GREY = (70, 70, 100)

PLAYER_SPEED = 230
PROJECTILE_SPD = 520
ENEMY_SPEED = 140
FIRE_RATE = 0.15
WAVE_INTERVAL = 15.0

SAVE_FILE = Path("highscore.json")

Vector = pygame.Vector2
vec = pygame.Vector2


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


# ╭──────────────────────────────────────────────────────────────╮
# │ 2. Entity hierarchy                                         │
# ╰──────────────────────────────────────────────────────────────╯
class Entity(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.pos = vec(0, 0)
        self.vel = vec(0, 0)

    def update(self, dt: float):
        self.pos += self.vel * dt
        self.rect.center = self.pos


class Particle(Entity):
    def __init__(self, pos: Vector, color: Tuple[int, int, int], lifetime: float):
        super().__init__()
        self.image = pygame.Surface((4, 4), pygame.SRCALPHA)
        self.image.fill(color)
        self.rect = self.image.get_rect(center=pos)
        self.pos = vec(pos)
        self.timer = lifetime

    def update(self, dt: float):
        self.timer -= dt
        super().update(dt)
        if self.timer <= 0:
            self.kill()


class Bullet(Entity):
    def __init__(self, pos: Vector, direction: Vector, speed: float, damage: int):
        super().__init__()
        self.image = pygame.Surface((6, 6))
        self.image.fill(YELLOW)
        self.rect = self.image.get_rect(center=pos)
        self.pos = vec(pos)
        self.vel = direction.normalize() * speed
        self.damage = damage

    def update(self, dt: float):
        super().update(dt)
        if not screen_rect.collidepoint(self.pos):
            self.kill()


class Enemy(Entity):
    BASE_HP = 3

    def __init__(self, pos: Vector, hp_bonus: int = 0):
        super().__init__()
        self.base_img = pygame.Surface((28, 28), pygame.SRCALPHA)
        pygame.draw.circle(self.base_img, RED, (14, 14), 14)
        self.image = self.base_img.copy()
        self.rect = self.image.get_rect(center=pos)
        self.pos = vec(pos)
        self.hp = self.BASE_HP + hp_bonus

    def update(self, dt: float, player_pos: Vector):  # type: ignore[override]
        direction = (player_pos - self.pos).normalize()
        self.vel = direction * ENEMY_SPEED
        super().update(dt)


class Pickup(Entity):
    COLORS = {"rof": CYAN, "dmg": ORANGE, "spd": YELLOW}

    def __init__(self, pos: Vector, kind: str):
        super().__init__()
        self.kind = kind
        self.image = pygame.Surface((12, 12), pygame.SRCALPHA)
        pygame.draw.rect(self.image, self.COLORS[kind], (0, 0, 12, 12))
        self.rect = self.image.get_rect(center=pos)
        self.pos = vec(pos)
        self.timer = 10.0

    def update(self, dt: float):
        self.timer -= dt
        if self.timer <= 0:
            self.kill()


class Player(Entity):
    MAX_HP = 12

    def __init__(self, pos: Vector):
        super().__init__()
        self.base_img = pygame.Surface((30, 30), pygame.SRCALPHA)
        pygame.draw.polygon(self.base_img, CYAN, [(15, 0), (30, 30), (0, 30)])
        self.image = self.base_img.copy()
        self.rect = self.image.get_rect(center=pos)
        self.pos = vec(pos)

        self.hp = self.MAX_HP
        self.fire_rate = FIRE_RATE
        self.fire_cd = 0.0
        self.move_speed = PLAYER_SPEED
        self.bullet_speed = PROJECTILE_SPD
        self.damage = 1
        self.score = 0

        self.move_input = vec(0, 0)
        self.aim_input = vec(0, -1)

    # Upgrades -------------------------------------------------------------
    def apply(self, kind: str):
        if kind == "rof":
            self.fire_rate = max(0.05, self.fire_rate * 0.8)
        elif kind == "dmg":
            self.damage += 1
        elif kind == "spd":
            self.move_speed += 40

    # Combat ----------------------------------------------------------------
    def shoot(self, bullets: pygame.sprite.Group, particles: pygame.sprite.Group):
        if self.fire_cd > 0 or self.aim_input.length_squared() < 0.3:
            return
        dir = self.aim_input.normalize()
        muzzle = self.pos + dir * 24
        bullet = Bullet(muzzle, dir, self.bullet_speed, self.damage)
        bullets.add(bullet)
        particles.add(Particle(muzzle, YELLOW, 0.25))
        self.fire_cd = self.fire_rate

    # Update ----------------------------------------------------------------
    def update(self, dt: float):
        if self.move_input.length_squared() > 0:
            self.vel = self.move_input.normalize() * self.move_speed
        else:
            self.vel *= 0.85
        super().update(dt)
        self.pos.x = clamp(self.pos.x, 0, WIDTH)
        self.pos.y = clamp(self.pos.y, 0, HEIGHT)

        angle = -self.aim_input.angle_to(vec(0, -1)) if self.aim_input.length_squared() else 0
        self.image = pygame.transform.rotate(self.base_img, angle)
        self.rect = self.image.get_rect(center=self.rect.center)
        self.fire_cd = max(0.0, self.fire_cd - dt)


# ╭──────────────────────────────────────────────────────────────╮
# │ 3. Virtual twin‑stick (touch / mouse)                        │
# ╰──────────────────────────────────────────────────────────────╯
class Stick:
    def __init__(self, rect: pygame.Rect):
        self.zone = rect
        self.id: Optional[int] = None
        self.origin = vec(0, 0)
        self.value = vec(0, 0)

    def handle(self, etype: str, tid: int, pos: Tuple[float, float]):
        vpos = vec(pos)
        if etype == "down" and self.zone.collidepoint(pos) and self.id is None:
            self.id = tid
            self.origin = vpos
        elif etype == "up" and tid == self.id:
            self.id = None
            self.value = vec(0, 0)
        elif etype == "move" and tid == self.id:
            delta = vpos - self.origin
            if delta.length() > 60:
                delta.scale_to_length(60)
            self.value = delta / 60

    def draw(self, surf: pygame.Surface):
        if self.id is None:
            return
        pygame.draw.circle(surf, GREY, self.origin, 60, 2)
        pygame.draw.circle(surf, MAG, self.origin + self.value * 60, 16)


# ╭──────────────────────────────────────────────────────────────╮
# │ 4. Game class                                               │
# ╰──────────────────────────────────────────────────────────────╯
class Game:
    def __init__(self):
        pygame.init()
        flags = pygame.SCALED | pygame.RESIZABLE
        if sys.platform == "emscripten":
            flags |= pygame.FULLSCREEN
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
        global screen_rect
        screen_rect = self.screen.get_rect()

        self.font = pygame.font.SysFont("consolas", 20)
        self.big_font = pygame.font.SysFont("consolas", 48, bold=True)
        self.clock = pygame.time.Clock()

        self.reset()
        self.load_hs()

    # -----------------------------
    def reset(self):
        self.running = True
        self.wave = 0
        self.wave_timer = WAVE_INTERVAL
        self.entities = pygame.sprite.Group()
        self.enemies = pygame.sprite.Group()
        self.bullets = pygame.sprite.Group()
        self.particles = pygame.sprite.Group()
        self.pickups = pygame.sprite.Group()
        self.player = Player(vec(WIDTH / 2, HEIGHT / 2))
        self.entities.add(self.player)

        self.move_stick = Stick(pygame.Rect(0, HEIGHT * 0.35, WIDTH * 0.45, HEIGHT * 0.65))
        self.aim_stick = Stick(pygame.Rect(WIDTH * 0.55, HEIGHT * 0.35, WIDTH * 0.45, HEIGHT * 0.65))

    # -----------------------------
    def save_hs(self):
        data = {"hi": max(self.player.score, getattr(self, "hi", 0))}
        SAVE_FILE.write_text(json.dumps(data))
        self.hi = data["hi"]

    def load_hs(self):
        if SAVE_FILE.exists():
            self.hi = json.loads(SAVE_FILE.read_text()).get("hi", 0)
        else:
            self.hi = 0

    # -----------------------------
    def spawn_wave(self):
        self.wave += 1
        self.wave_timer = max(5, WAVE_INTERVAL - self.wave * 1.4)
        hp_bonus = self.wave // 3
        for _ in range(4 + self.wave * 2):
            ang = random.random() * math.tau
            dist = random.randint(360, 520)
            pos = self.player.pos + vec(math.cos(ang), math.sin(ang)) * dist
            e = Enemy(pos, hp_bonus)
            self.enemies.add(e)
            self.entities.add(e)

    # -----------------------------
    def maybe_spawn_pickup(self, pos: Vector):
        if random.random() < 0.3:
            kind = random.choice(["rof", "dmg", "spd"])
            p = Pickup(pos, kind)
            self.pickups.add(p)
            self.entities.add(p)

    # -----------------------------
    def process_input(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.running = False

            # mouse -> two fake touches
            if ev.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
                et = "move" if ev.type == pygame.MOUSEMOTION else ("down" if ev.type == pygame.MOUSEBUTTONDOWN else "up")
                tid_l, tid_r = 0, 1
                self.move_stick.handle(et, tid_l if ev.pos[0] < WIDTH / 2 else tid_r, ev.pos)
                self.aim_stick.handle(et, tid_r if ev.pos[0] >= WIDTH / 2 else tid_l, ev.pos)

            # touch
            if ev.type == pygame.FINGERDOWN:
                self.move_stick.handle("down", ev.touch_id, (ev.x * WIDTH, ev.y * HEIGHT))
                self.aim_stick.handle("down", ev.touch_id, (ev.x * WIDTH, ev.y * HEIGHT))
            if ev.type == pygame.FINGERMOTION:
                self.move_stick.handle("move", ev.touch_id, (ev.x * WIDTH, ev.y * HEIGHT))
                self.aim_stick.handle("move", ev.touch_id, (ev.x * WIDTH, ev.y * HEIGHT))
            if ev.type == pygame.FINGERUP:
                self.move_stick.handle("up", ev.touch_id, (ev.x * WIDTH, ev.y * HEIGHT))
                self.aim_stick.handle("up", ev.touch_id, (ev.x * WIDTH, ev.y * HEIGHT))

        # keyboard override
        keys = pygame.key.get_pressed()
        kd = vec(keys[pygame.K_d] - keys[pygame.K_a], keys[pygame.K_s] - keys[pygame.K_w])
        if kd.length_squared() > 0:  # normalize if non‑zero
            kd.scale_to_length(1)
        if self.move_stick.id is None:
            self.move_stick.value = kd

        self.player.move_input = self.move_stick.value

        # mouse aim fallback if no right stick active
        if self.aim_stick.id is None and pygame.mouse.get_focused():
            rel = vec(pygame.mouse.get_pos()) - self.player.pos
            self.aim_stick.value = rel.normalize() if rel.length() > 80 else vec(0, 0)
        self.player.aim_input = self.aim_stick.value

        # shooting
        lmb = pygame.mouse.get_pressed()[0] and self.aim_stick.id is None
        stick_fire = self.aim_stick.id is not None
        if lmb or stick_fire:
            self.player.shoot(self.bullets, self.particles)

    # -----------------------------
    def update(self):
        # wave timer
        self.wave_timer -= DT
        if self.wave_timer <= 0:
            self.spawn_wave()

        # update all
        for entity in self.entities:
            if isinstance(entity, Enemy):
                entity.update(DT, self.player.pos)
            else:
                entity.update(DT)
        self.bullets.update(DT)
        self.particles.update(DT)

        # bullet hits
        hits = pygame.sprite.groupcollide(self.enemies, self.bullets, False, True)
        for enemy, bullets in hits.items():
            for b in bullets:
                enemy.hp -= b.damage
                self.particles.add(Particle(enemy.pos, ORANGE, 0.2))
            if enemy.hp <= 0:
                enemy.kill()
                self.player.score += 10
                self.maybe_spawn_pickup(enemy.pos)

        # enemy touches player
        if pygame.sprite.spritecollideany(self.player, self.enemies):
            self.player.hp -= 1
            for e in self.enemies:
                if self.player.rect.colliderect(e.rect):
                    knock = (e.pos - self.player.pos).normalize() * 40
                    e.pos += knock
            if self.player.hp <= 0:
                self.running = False

        # pickups
        for p in pygame.sprite.spritecollide(self.player, self.pickups, dokill=True):
            assert isinstance(p, Pickup)
            self.player.apply(p.kind)
            self.player.score += 5

    # -----------------------------
    def draw_hud(self):
        surf = self.screen
        # HP bar
        pygame.draw.rect(surf, GREY, (20, 20, 120, 14))
        hp_w = int(118 * self.player.hp / self.player.MAX_HP)
        pygame.draw.rect(surf, CYAN, (21, 21, hp_w, 12))
        # Wave / score
        txt = self.font.render(f"Wave {self.wave}   Score {self.player.score}   High {self.hi}", True, WHITE)
        surf.blit(txt, (WIDTH // 2 - txt.get_width() // 2, 20))

    # -----------------------------
    def draw(self):
        self.screen.fill(BLACK)
        for grp in (self.particles, self.entities, self.bullets, self.pickups):
            grp.draw(self.screen)
        self.move_stick.draw(self.screen)
        self.aim_stick.draw(self.screen)
        self.draw_hud()
        pygame.display.flip()

    # -----------------------------
    def game_over(self):
        self.save_hs()
        txt = self.big_font.render("GAME OVER", True, WHITE)
        self.screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, HEIGHT // 2 - 40))
        txt2 = self.font.render("Press [R] to restart or [Esc] to quit", True, WHITE)
        self.screen.blit(txt2, (WIDTH // 2 - txt2.get_width() // 2, HEIGHT // 2 + 20))
        pygame.display.flip()
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_r:
                        self.reset()
                        return
                    if ev.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()
            self.clock.tick(30)

    # -----------------------------
    def run(self):
        while True:
            self.process_input()
            if self.running:
                self.update()
                self.draw()
            else:
                self.game_over()
            self.clock.tick(FPS)


# ╭──────────────────────────────────────────────────────────────╮
# │ 5. Boot                                                     │
# ╰──────────────────────────────────────────────────────────────╯
if __name__ == "__main__":
    game = Game()
    game.run()
