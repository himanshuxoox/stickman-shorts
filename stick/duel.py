"""
RAGDOLL DUEL — physics stickman fights (our own engine on pymunk, MIT licence).

Two floppy ragdoll stickmen (real joints, gravity, momentum) fight with a random weapon
each round: sword, axe, hammer, spear, boxing gloves or blaster. Hits are decided by the
physics: how fast the weapon is moving when it touches the other body (head hits =
CRITICAL). First to 3 round wins takes the match. K.O.s play in slow motion.

Everything is drawn in code; music and SFX are synthesized (stick/fightaudio.py).

    python -m stick.duel --seed 1 --out /tmp/x       # one test video
"""
import math, os, random, subprocess

import cairo
import pymunk

from . import fightaudio

W, H, FPS = 1080, 1920, 30
SUB = 4                                    # physics steps per frame (dt = 1/120 s)
DT = 1.0 / (FPS * SUB)
G = 2300.0
X0, X1 = 40.0, 1040.0                      # arena walls
FLOOR = 1560.0
CEIL = 300.0
WIN_ROUNDS = 3

HEAD_R, NECK, TORSO = 34.0, 8.0, 140.0
UARM, FARM, THIGH, SHIN = 72.0, 70.0, 88.0, 88.0
LEG = THIGH + SHIN

CT_GROUND, CT_BODY, CT_WEAPON, CT_BULLET, CT_HAZARD = 1, 2, 3, 4, 5

WEAPONS = {
    "sword":  dict(len=150, r=6, mass=1.0, mult=1.0, rate=(0.45, 0.9), reach=320),
    "axe":    dict(len=125, r=7, mass=1.6, mult=1.25, rate=(0.55, 1.0), reach=300),
    "hammer": dict(len=135, r=8, mass=2.6, mult=1.5, rate=(0.7, 1.2), reach=310),
    "spear":  dict(len=235, r=5, mass=1.1, mult=1.05, rate=(0.5, 0.95), reach=400),
    "gloves": dict(len=0, r=22, mass=0.9, mult=0.8, rate=(0.3, 0.6), reach=200),
    "blaster": dict(len=48, r=7, mass=0.7, mult=0.0, rate=(0.55, 0.85), reach=700),
}
RED = (1.0, 0.25, 0.32)
BLUE = (0.25, 0.62, 1.0)
GOLD = (1.0, 0.85, 0.2)
WHITE = (1.0, 1.0, 1.0)
THEMES = [
    dict(name="dojo", sky=((0.10, 0.04, 0.10), (0.55, 0.22, 0.12)), floor=(0.16, 0.09, 0.07), line=(1.0, 0.6, 0.3)),
    dict(name="neon", sky=((0.02, 0.02, 0.08), (0.10, 0.04, 0.22)), floor=(0.05, 0.04, 0.12), line=(0.4, 0.9, 1.0)),
    dict(name="storm", sky=((0.02, 0.04, 0.08), (0.12, 0.22, 0.3)), floor=(0.05, 0.07, 0.09), line=(0.6, 0.85, 1.0)),
    dict(name="volcano", sky=((0.08, 0.02, 0.02), (0.45, 0.1, 0.04)), floor=(0.12, 0.05, 0.04), line=(1.0, 0.4, 0.1)),
]
MAPS = ["flat", "platforms", "spikes", "platforms_spikes"]


def _no_gravity(body, gravity, damping, dt):
    pymunk.Body.update_velocity(body, (0, 0), 1.0, dt)


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


# ===================================================================== ragdoll (active ragdoll)
# Every joint has a motor (pymunk GearJoint): max_bias = how fast it moves (animation speed),
# max_force = how strong the muscle is. An animation state machine sets target angles for each
# limb (guard, walk cycle, windup, strike, recover, jump, stun, victory). Physics still decides
# everything else: hits knock the body around, stun weakens the muscles, K.O. switches them off.

def _deg_to_world(theta, facing):
    """theta: limb direction in degrees, 0 = straight down, +90 = forward (towards the foe), 180 = up."""
    t = math.radians(theta)
    return math.atan2(math.cos(t), facing * math.sin(t))


def _aim_theta(dx, dy, facing):
    return math.degrees(math.atan2(dx * facing, dy))


LEGS = {
    "stance": dict(th0=22, sn0=6, th1=-18, sn1=-6),
    "crouch": dict(th0=60, sn0=-12, th1=12, sn1=-62),
    "air":    dict(th0=72, sn0=-6, th1=8, sn1=-78),
    "lunge":  dict(th0=55, sn0=18, th1=-42, sn1=-30),
    "back":   dict(th0=8, sn0=-4, th1=-38, sn1=-20),
}

# arm poses per weapon: ua0/fa0 = weapon arm (upper/fore), ua1/fa1 = other arm; lean = degrees forward
ARMS = {
    "sword": {
        "guard":  dict(ua0=38, fa0=132, ua1=18, fa1=70, lean=6),
        "windA":  dict(ua0=168, fa0=222, ua1=-25, fa1=20, lean=-10),
        "strikeA": dict(ua0=82, fa0=40, ua1=-30, fa1=-10, lean=18),
        "windB":  dict(ua0=-55, fa0=-105, ua1=40, fa1=90, lean=-6),
        "strikeB": dict(ua0=105, fa0=98, ua1=-30, fa1=-20, lean=18),
    },
    "axe": {
        "guard":  dict(ua0=40, fa0=140, ua1=20, fa1=70, lean=6),
        "windA":  dict(ua0=170, fa0=230, ua1=-25, fa1=20, lean=-12),
        "strikeA": dict(ua0=78, fa0=30, ua1=-30, fa1=-10, lean=22),
        "windB":  dict(ua0=-60, fa0=-110, ua1=40, fa1=90, lean=-8),
        "strikeB": dict(ua0=108, fa0=100, ua1=-30, fa1=-20, lean=18),
    },
    "hammer": {
        "guard":  dict(ua0=42, fa0=150, ua1=35, fa1=140, lean=4),
        "windA":  dict(ua0=176, fa0=200, ua1=170, fa1=195, lean=-14),
        "strikeA": dict(ua0=72, fa0=12, ua1=70, fa1=15, lean=28),
        "windB":  dict(ua0=176, fa0=200, ua1=170, fa1=195, lean=-14),
        "strikeB": dict(ua0=72, fa0=12, ua1=70, fa1=15, lean=28),
    },
    "spear": {
        "guard":  dict(ua0=70, fa0=96, ua1=55, fa1=100, lean=8),
        "windA":  dict(ua0=10, fa0=96, ua1=0, fa1=100, lean=-10),
        "strikeA": dict(ua0=96, fa0=94, ua1=88, fa1=96, lean=22),
        "windB":  dict(ua0=120, fa0=150, ua1=100, fa1=150, lean=-8),
        "strikeB": dict(ua0=80, fa0=60, ua1=70, fa1=60, lean=20),
    },
    "gloves": {
        "guard":  dict(ua0=32, fa0=158, ua1=24, fa1=150, lean=10),
        "windA":  dict(ua0=10, fa0=150, ua1=30, fa1=160, lean=4),       # jab
        "strikeA": dict(ua0=96, fa0=94, ua1=26, fa1=155, lean=16),
        "windB":  dict(ua0=30, fa0=160, ua1=-10, fa1=120, lean=0),      # cross
        "strikeB": dict(ua0=30, fa0=155, ua1=98, fa1=94, lean=22),
        "windC":  dict(ua0=-10, fa0=40, ua1=24, fa1=150, lean=-6),      # uppercut
        "strikeC": dict(ua0=70, fa0=176, ua1=24, fa1=150, lean=10),
    },
    "blaster": {
        "guard":  dict(ua0=80, fa0=90, ua1=60, fa1=95, lean=0),
    },
}
VICTORY = dict(ua0=150, fa0=175, ua1=-35, fa1=35, lean=-6)      # weapon raised, other hand on hip
TIMING = {  # windup, strike, recover (seconds), arm speed (rad/s) for windup / strike
    "sword": (0.2, 0.14, 0.22, 14, 34), "axe": (0.26, 0.16, 0.26, 12, 30),
    "hammer": (0.34, 0.18, 0.32, 10, 30), "spear": (0.22, 0.12, 0.22, 14, 30),
    "gloves": (0.1, 0.09, 0.12, 22, 40), "blaster": (0.1, 0.1, 0.1, 18, 18),
}


class Ragdoll:
    def __init__(self, game, idx, x, facing, color, name, weapon):
        self.game, self.idx, self.color, self.name, self.weapon = game, idx, color, name, weapon
        self.facing = facing
        sp = game.space
        self.filt = pymunk.ShapeFilter(group=idx + 1)
        self.hp, self.alive = 100.0, True
        self.flash = -9.0
        self.parts, self.motors = [], {}
        hip = pymunk.Vec2d(x, FLOOR - LEG - 2)
        neck = hip - (0, TORSO)
        headp = neck - (0, NECK + HEAD_R)

        def seg(a, b, r, m, part):
            body = pymunk.Body()
            mid = (a + b) / 2
            body.position = mid
            sh = pymunk.Segment(body, a - mid, b - mid, r)
            sh.mass, sh.friction, sh.elasticity = m, 0.8, 0.1
            sh.filter, sh.collision_type = self.filt, CT_BODY
            sh.owner, sh.part = self, part
            sp.add(body, sh)
            self.parts.append(sh)
            body.a0 = math.atan2(b.y - a.y, b.x - a.x)     # direction of the limb at angle 0
            body.seg = sh
            return body

        self.torso = seg(neck, hip, 11, 6.0, "torso")
        self.torso_sh = self.torso.seg
        self.head = pymunk.Body()
        self.head.position = headp
        hs = pymunk.Circle(self.head, HEAD_R)
        hs.mass, hs.friction, hs.elasticity = 1.6, 0.8, 0.2
        hs.filter, hs.collision_type, hs.owner, hs.part = self.filt, CT_BODY, self, "head"
        sp.add(self.head, hs)
        self.parts.append(hs)
        self.pin(self.torso, self.head, neck - (0, 2))
        self.limit(self.torso, self.head, -0.7, 0.7)
        self.motor("head", sp.static_body, self.head, 3e5, 8)
        # balance motor: holds the torso at the wanted lean (the "game cheat" every ragdoll game uses)
        self.motor("torso", sp.static_body, self.torso, 2.2e7, 9)

        sh_pt = neck + (0, 10)
        self.arms = []
        for k in range(2):
            elbow = sh_pt + (0, UARM)
            hand = elbow + (0, FARM)
            ua = seg(sh_pt, elbow, 7, 0.8, "limb")
            fa = seg(elbow, hand, 7, 0.8, "limb")
            self.pin(self.torso, ua, sh_pt)
            self.pin(ua, fa, elbow)
            self.limit(ua, fa, -2.7, 2.7)
            self.motor(f"ua{k}", self.torso, ua, 6e6, 14)
            self.motor(f"fa{k}", ua, fa, 4e6, 14)
            self.arms.append((ua, fa, sh_pt, elbow, hand))
        self.legs = []
        for k in range(2):
            knee = hip + (0, THIGH)
            foot = knee + (0, SHIN)
            th = seg(hip, knee, 9, 1.3, "limb")
            sn = seg(knee, foot, 8, 1.2, "limb")
            self.pin(self.torso, th, hip)
            self.pin(th, sn, knee)
            self.limit(self.torso, th, -2.0, 2.0)
            self.limit(th, sn, -2.5, 2.5)
            self.motor(f"th{k}", self.torso, th, 5e6, 12)
            self.motor(f"sn{k}", th, sn, 4e6, 12)
            sn.seg.friction = 0.25            # feet slide a little; the walk cycle sells the steps
            self.legs.append((th, sn, hip, knee, foot))

        # weapon in the front hand, in line with the forearm (gloves: both hands)
        wd = WEAPONS[weapon]
        self.wshapes = []
        ua, fa, _, elbow, hand = self.arms[0]
        self.wbody = fa
        if weapon == "gloves":
            for (_, fa2, _, _, hand2) in self.arms:
                c = pymunk.Circle(fa2, wd["r"], fa2.world_to_local(hand2))
                self._weapon_shape(c, wd)
        else:
            p0 = fa.world_to_local(hand)
            p1 = fa.world_to_local(hand + (0, wd["len"]))
            self._weapon_shape(pymunk.Segment(fa, p0, p1, wd["r"]), wd)
            self.w_p0, self.w_p1 = p0, p1
        # animation / AI state
        r = game.rng
        self.state, self.state_t, self.state_end = "guard", 0.0, 0.0
        self.seq = []
        self.move = "A"
        self.walk_phase = r.uniform(0, 6.28)
        self.want_vx = 0.0
        self.stun_until, self.stun_amt = -9.0, 0.0
        self.next_think = 0.5 + r.uniform(0, 0.4)
        self.style = r.uniform(0.0, 1.0)
        self.last_shot = -9.0
        self.trail = []
        self.combo = 0
        self.air_attack = 9e9
        self.jump_dx = self.jump_dy = 0.0
        self.blocked = 0.0
        self.last_jump = -9.0

    # ---------------------------------------------------------------- building helpers
    def _weapon_shape(self, s, wd):
        s.mass, s.friction, s.elasticity = wd["mass"], 0.5, 0.2
        s.filter, s.collision_type = self.filt, CT_WEAPON
        s.owner, s.kind = self, self.weapon
        self.game.space.add(s)
        self.wshapes.append(s)

    def pin(self, a, b, pt):
        j = pymunk.PivotJoint(a, b, pt)
        j.collide_bodies = False
        self.game.space.add(j)

    def limit(self, a, b, lo, hi):
        self.game.space.add(pymunk.RotaryLimitJoint(a, b, lo, hi))

    def motor(self, name, parent, child, force, speed):
        g = pymunk.GearJoint(parent, child, child.angle - parent.angle, 1.0)
        g.max_force, g.max_bias = force, speed
        g.error_bias = pow(0.3, 60)
        self.game.space.add(g)
        self.motors[name] = [g, parent, child, force]

    @property
    def bodies(self):
        out = [self.torso, self.head]
        for a in self.arms:
            out += [a[0], a[1]]
        for l in self.legs:
            out += [l[0], l[1]]
        return out

    @property
    def mass(self):
        return sum(b.mass for b in self.bodies)

    def go_limp(self):
        for g, *_ in self.motors.values():
            g.max_force = 0.0

    def hip(self):
        return self.torso.local_to_world(self.torso_sh.b)

    def neck(self):
        return self.torso.local_to_world(self.torso_sh.a)

    def grounded(self):
        for th, sn, *_ in self.legs:
            p = sn.local_to_world(sn.seg.b)
            if self.game.ground_below(p) - p.y < 42:
                return True
        return False

    def weapon_tip(self):
        if self.weapon == "gloves":
            return self.arms[0][1].local_to_world(self.wshapes[0].offset)
        return self.wbody.local_to_world(self.w_p1)

    def weapon_base(self):
        if self.weapon == "gloves":
            return self.arms[0][1].local_to_world(self.wshapes[0].offset)
        return self.wbody.local_to_world(self.w_p0)

    # ---------------------------------------------------------------- pose -> motors
    def _target_body_angle(self, body, theta):
        return _deg_to_world(theta, self.facing) - body.a0

    def apply_pose(self, pose, legs, arm_speed=14, leg_speed=12, strength=1.0):
        f = self.facing
        torso_t = _deg_to_world(-pose.get("lean", 0), f) - self.torso.a0
        targets = {"torso": torso_t}
        for k, (ua, fa, *_) in enumerate(self.arms):
            targets[f"ua{k}"] = self._target_body_angle(ua, pose[f"ua{k}"])
            targets[f"fa{k}"] = self._target_body_angle(fa, pose[f"fa{k}"])
        for k, (th, sn, *_) in enumerate(self.legs):
            targets[f"th{k}"] = self._target_body_angle(th, legs[f"th{k}"])
            targets[f"sn{k}"] = self._target_body_angle(sn, legs[f"sn{k}"])
        targets["head"] = torso_t
        parent_t = {"torso": 0.0, "head": 0.0}
        for name, (g, parent, child, force) in self.motors.items():
            if name in ("torso", "head"):
                rel_t = targets[name]
                cur = child.angle - (parent.angle if name == "torso" else 0.0)
            else:
                pname = "torso" if name[:2] in ("ua", "th") else name.replace("fa", "ua").replace("sn", "th")
                rel_t = targets[name] - targets[pname]
                cur = child.angle - parent.angle
            g.phase = cur + _wrap(rel_t - cur)
            spd = arm_speed if name[:2] in ("ua", "fa") else (leg_speed if name[:2] in ("th", "sn") else 9)
            g.max_bias = spd
            # legs stay fairly strong while stunned (no splits); the upper body goes floppy
            g.max_force = force * (max(strength, 0.55) if name[:2] in ("th", "sn") else strength)

    # ---------------------------------------------------------------- per-step control
    def control(self, t, dt):
        g = self.game
        if not self.alive:
            return
        foe = g.fighters[1 - self.idx]
        dx = foe.torso.position.x - self.torso.position.x
        if abs(dx) > 40 and self.state in ("guard", "walk"):
            self.facing = 1 if dx > 0 else -1
        # muscle strength: weak while stunned, comes back smoothly
        if t < self.stun_until:
            strength = 0.08 + 0.15 * (1 - self.stun_amt)
        else:
            strength = min(1.0, 0.25 + (t - self.stun_until) * 3.0)
        grounded = self.grounded()
        # stand: spring the hip to leg height (scaled by strength so stunned bodies sag)
        hip = self.hip()
        gy = g.ground_below(hip)
        crouch = 0.3 if self.state in ("crouch",) else (0.12 if self.state.startswith("wind") else 0.0)
        target = gy - LEG * (0.99 - 0.35 * crouch)
        if hip.y > target - 120 and self.state != "air":
            mt = self.mass
            fy = (target - hip.y) * 3200 - self.torso.velocity.y * 560
            fy = max(-mt * G * 2.4, min(0.0, fy)) * min(1.0, strength * 1.2)
            self.torso.apply_force_at_world_point((0, fy), self.torso.position)
        # horizontal movement
        if g.phase == "fight" and t >= self.stun_until:
            vx = self.torso.velocity.x
            acc = 6.0 if grounded else 1.5
            self.torso.apply_force_at_world_point(((self.want_vx - vx) * self.mass * acc, 0), self.torso.position)
        # state machine
        if t >= self.state_end and self.seq:
            self._enter(t, *self.seq.pop(0))
        elif t >= self.state_end and self.state not in ("guard", "walk", "air"):
            self._enter(t, "guard", 0.0)
        landed = grounded or (abs(self.torso.velocity.y) < 60 and t - self.state_t > 0.35)
        if self.state == "air" and landed and t - self.state_t > 0.15:
            self.seq = []
            self._enter(t, "guard", 0.0)
        if self.state == "air" and t >= self.air_attack:
            self.air_attack = 9e9
            wind, strike, rec, *_ = TIMING[self.weapon]
            self.seq = [("strike", strike, None), ("air", 1.0, None)]
            self._enter(t, "wind", min(0.16, wind), "A")
        # pose for this state
        arms = ARMS[self.weapon]
        st = self.state
        wind_s, strike_s = TIMING[self.weapon][3], TIMING[self.weapon][4]
        arm_speed, leg_speed = 12, 12
        if g.phase in ("ko", "end") and g.round_winner is self:
            pose, legs = VICTORY, LEGS["stance"]
            arm_speed = 8
        elif st == "wind":
            pose = arms.get("wind" + self.move, arms["guard"])
            legs = LEGS["back"] if self.weapon != "hammer" else LEGS["crouch"]
            arm_speed = wind_s
        elif st == "strike":
            pose = arms.get("strike" + self.move, arms["guard"])
            legs = LEGS["lunge"]
            arm_speed, leg_speed = strike_s, 18
        elif st == "crouch":
            pose, legs = arms["guard"], LEGS["crouch"]
            leg_speed = 20
        elif st == "air":
            pose, legs = arms["guard"], LEGS["air"]
        else:
            pose = arms["guard"]
            legs = self._walk_legs(dt)
        if self.weapon == "blaster" and g.phase == "fight":
            pose = self._aim_pose(foe)
            arm_speed = 16
        elif self.weapon == "spear" and st in ("guard", "walk", "strike"):
            pose = dict(pose)
            a = _aim_theta(*(foe.torso.position - self.neck()), self.facing)
            a = max(40, min(140, a))
            for k in ("fa0", "fa1"):
                pose[k] = a
        self.apply_pose(pose, legs, arm_speed, leg_speed, strength)
        if g.phase == "fight":
            if t >= self.next_think and t >= self.stun_until and self.state in ("guard", "walk"):
                self.think(t, foe, abs(dx), grounded)
        elif g.phase in ("ko", "end") and g.round_winner is self:
            self.want_vx = 0.0
            if grounded and g.rng.random() < 0.004 and t > g.ko_t + 1.0:
                self.torso.apply_impulse_at_world_point((0, -self.mass * 950), self.torso.position)
                self._enter(t, "air", 0.6)
        else:
            self.want_vx = 0.0

    def _walk_legs(self, dt):
        vx = self.torso.velocity.x * self.facing
        sp = abs(vx)
        if sp < 40:
            return LEGS["stance"]
        self.walk_phase += dt * sp / 38.0
        p = self.walk_phase
        s0, s1 = math.sin(p), math.sin(p + math.pi)
        d = 1 if vx > 0 else -1
        return dict(th0=d * 32 * s0 + 6, sn0=d * 32 * s0 + 6 - 38 * max(0.0, math.cos(p)),
                    th1=d * 32 * s1 - 4, sn1=d * 32 * s1 - 4 - 38 * max(0.0, math.cos(p + math.pi)))

    def _aim_pose(self, foe):
        sh = self.neck() + (0, 10)
        a = _aim_theta(*(foe.head.position - sh), self.facing)
        a = max(20, min(170, a))
        return dict(ua0=a, fa0=a, ua1=a - 12, fa1=a + 6, lean=-4 if self.game.t - self.last_shot < 0.15 else 2)

    def _enter(self, t, state, dur, move=None):
        if move:
            self.move = move
        self.state, self.state_t, self.state_end = state, t, t + dur
        g = self.game
        if state == "strike":
            m = self.mass
            if self.weapon != "blaster":
                self.torso.apply_impulse_at_world_point((self.facing * m * (260 + 160 * self.style), -m * 60),
                                                        self.torso.position)
                g.sfx(t, "whoosh", 0.1)
        elif state == "jump":
            self.last_jump = t
            m = self.mass
            self.torso.apply_impulse_at_world_point((self.facing * m * self.jump_dx, -m * self.jump_dy),
                                                    self.torso.position)
            self.state, self.state_end = "air", t + 1.2
            g.sfx(t, "whoosh", 0.15)
        elif state == "shoot":
            self.shoot(t, g.fighters[1 - self.idx])
            self.state, self.state_end = "guard", t + 0.05

    # ---------------------------------------------------------------- AI
    def think(self, t, foe, dist, grounded):
        r = self.game.rng
        wd = WEAPONS[self.weapon]
        wind, strike, rec, *_ = TIMING[self.weapon]
        self.next_think = t + r.uniform(0.08, 0.2)
        reach = wd["reach"]
        careful = self.hp < 35 and self.style < 0.5
        can_jump = grounded and t - self.last_jump > 1.4
        # dodge a foe that is winding up
        if can_jump and foe.state.startswith("wind") and dist < reach + 60 and r.random() < 0.18 + 0.2 * (1 - self.style):
            self.jump_dx, self.jump_dy = -r.uniform(380, 520), r.uniform(650, 850)
            self.seq = [("jump", 0.0, None)]
            self._enter(t, "crouch", 0.09)
            return
        if self.weapon == "blaster":
            self.want_vx = -self.facing * 260 if dist < 380 else (self.facing * 220 if dist > 640 else 0.0)
            if t - self.last_shot > r.uniform(0.45, 0.8):
                self._enter(t, "shoot", 0.0)
            if can_jump and ((dist < 260 and r.random() < 0.35) or r.random() < 0.03):
                self.jump_dx, self.jump_dy = -r.uniform(380, 520), r.uniform(1150, 1350)
                self.seq = [("jump", 0.0, None)]
                self._enter(t, "crouch", 0.1)
            return
        foe_high = foe.head.position.y < self.head.position.y - 170
        tip_close = min((foe.torso.position - self.weapon_tip()).length,
                        (foe.head.position - self.weapon_tip()).length) < 90
        # blocked (e.g. by a long spear) -> jump in over it
        if abs(self.want_vx) > 200 and abs(self.torso.velocity.x) < 50:
            self.blocked += 0.15
        else:
            self.blocked = 0.0
        if can_jump and self.blocked > 0.6:
            self.blocked = 0.0
            self.jump_dx, self.jump_dy = r.uniform(450, 600), r.uniform(1150, 1400)
            self.seq = [("jump", 0.0, None)]
            self._enter(t, "crouch", 0.1)
            self.air_attack = t + 0.1 + r.uniform(0.22, 0.3)
            return
        if dist > reach and not tip_close:
            self.want_vx = self.facing * (330 + 150 * self.style) * (0.7 if careful else 1.0)
            self.state = "walk"
            if can_jump and (foe_high or (dist > reach + 250 and r.random() < 0.08)):
                # jump in with an attack in the air
                self.jump_dx, self.jump_dy = r.uniform(380, 560), r.uniform(1100, 1400)
                self.seq = [("jump", 0.0, None)]
                self._enter(t, "crouch", 0.12)
                self.air_attack = t + 0.12 + r.uniform(0.2, 0.32)
            return
        self.want_vx = self.facing * 60 if dist > reach * 0.7 else -self.facing * 120
        if careful and r.random() < 0.3:
            self.want_vx = -self.facing * 250
            return
        # attack: windup -> strike -> recover (combo for fast weapons)
        moves = ["A", "B"] + (["C"] if self.weapon == "gloves" else [])
        mv = r.choice(moves)
        self.seq = [("strike", strike, None), ("recover", rec, None)]
        if self.weapon in ("gloves", "sword") and r.random() < 0.5:      # 2-hit combo
            nxt = r.choice([m for m in moves if m != mv])
            self.seq = [("strike", strike, None), ("wind", wind * 0.6, nxt), ("strike", strike, None),
                        ("recover", rec, None)]
            if self.weapon == "gloves" and r.random() < 0.5:
                self.seq[-1:] = [("wind", wind * 0.6, "C"), ("strike", strike, None), ("recover", rec, None)]
        self._enter(t, "wind", wind * r.uniform(0.85, 1.25), mv)
        total = sum(d for _, d, _ in self.seq) + wind
        self.next_think = t + total + r.uniform(0.05, 0.35) * (1.3 - self.style)

    def shoot(self, t, foe):
        g = self.game
        tip = self.weapon_tip()
        base = self.weapon_base()
        u = (tip - base).normalized()
        b = pymunk.Body()
        b.position = tip + u * 10
        b.velocity = u * 1900
        b.velocity_func = _no_gravity
        s = pymunk.Circle(b, 7)
        s.mass, s.filter, s.collision_type = 0.05, self.filt, CT_BULLET
        s.owner, s.born = self, t
        g.space.add(b, s)
        g.bullets.append(s)
        self.wbody.apply_impulse_at_world_point(-u * 700, tip)
        self.last_shot = t
        g.sfx(t, "pew", 0.05)


# ===================================================================== game / match
class Game:
    def __init__(self, seed, record=False):
        self.seed, self.record = seed, record
        self.rng = random.Random(seed * 7919 + 17)
        self.theme = self.rng.choice(THEMES)
        self.map = self.rng.choice(MAPS)
        self.frames, self.effects, self.sounds = [], [], []
        self.vt = 0.0                         # video time
        self.t = 0.0                          # physics time
        self.score = [0, 0]
        self.round = 0
        self.rounds = []
        self.last_sound = {}
        self.names = ("RED", "BLUE")
        pool = list(WEAPONS)
        self.round_weapons = []
        for _ in range(2 * WIN_ROUNDS - 1):
            a, b = self.rng.sample(pool, 2) if self.rng.random() < 0.7 else [self.rng.choice(pool)] * 2
            self.round_weapons.append((a, b))
        self.platforms = []
        if "platforms" in self.map:
            y = self.rng.uniform(1120, 1220)
            self.platforms = [(140, 400, y), (680, 940, y)]
            if self.rng.random() < 0.5:
                self.platforms.append((400, 680, y - self.rng.uniform(300, 360)))
        self.spikes = []
        if "spikes" in self.map:
            w = self.rng.uniform(150, 190)
            self.spikes = [(X0, X0 + w), (X1 - w, X1)]

    # ---------------------------------------------------------------- helpers
    def fx(self, kind, *a):
        self.effects.append((self.vt, kind) + a)

    def sfx(self, t, kind, gap=0.06):
        vt = self.vt
        if vt - self.last_sound.get(kind, -9) >= gap:
            self.last_sound[kind] = vt
            self.sounds.append((vt, kind))

    def ground_below(self, p):
        y = FLOOR
        for x0, x1, py in self.platforms:
            if x0 - 10 <= p.x <= x1 + 10 and py >= p.y - 30:
                y = min(y, py)
        return y

    # ---------------------------------------------------------------- round setup
    def new_round(self):
        self.round += 1
        self.space = sp = pymunk.Space()
        sp.gravity = (0, G)
        sp.iterations = 25
        static = sp.static_body
        segs = [((X0, FLOOR), (X1, FLOOR)), ((X0, CEIL), (X0, FLOOR)), ((X1, CEIL), (X1, FLOOR)),
                ((X0, CEIL), (X1, CEIL))]
        for a, b in segs:
            s = pymunk.Segment(static, a, b, 12)
            s.friction, s.elasticity, s.collision_type = 0.9, 0.2, CT_GROUND
            sp.add(s)
        for x0, x1, y in self.platforms:
            s = pymunk.Segment(static, (x0, y), (x1, y), 10)
            s.friction, s.elasticity, s.collision_type = 0.9, 0.2, CT_GROUND
            sp.add(s)
        for x0, x1 in self.spikes:
            s = pymunk.Segment(static, (x0, FLOOR - 16), (x1, FLOOR - 16), 14)
            s.collision_type, s.elasticity = CT_HAZARD, 0.6
            sp.add(s)
        wa, wb = self.round_weapons[self.round - 1]
        sx = self.rng.uniform(270, 330)
        self.fighters = [Ragdoll(self, 0, sx, 1, RED, "RED", wa),
                         Ragdoll(self, 1, W - sx, -1, BLUE, "BLUE", wb)]
        for f in self.fighters:
            f.next_think += self.t
        self.bullets = []
        self.hit_cd = {}
        self.hitstop = 0
        sp.on_collision(CT_WEAPON, CT_BODY, post_solve=self._weapon_body)
        sp.on_collision(CT_WEAPON, CT_WEAPON, post_solve=self._clash)
        sp.on_collision(CT_BULLET, CT_BODY, begin=self._bullet_body)
        sp.on_collision(CT_BULLET, CT_WEAPON, begin=self._bullet_other)
        sp.on_collision(CT_BULLET, CT_GROUND, begin=self._bullet_other)
        sp.on_collision(CT_BULLET, CT_HAZARD, begin=self._bullet_other)
        sp.on_collision(CT_HAZARD, CT_BODY, begin=self._spike)
        self.phase, self.phase_t = "intro", self.vt
        self.round_t0 = self.t
        self.round_winner = None
        self.ko_t = -9.0
        final = self.score[0] == WIN_ROUNDS - 1 and self.score[1] == WIN_ROUNDS - 1
        mp = max(self.score) == WIN_ROUNDS - 1
        self.fx("round", self.round, "FINAL ROUND!" if final else ("MATCH POINT!" if mp else ""), wa, wb)
        self.sfx(self.t, "rise", 0)

    # ---------------------------------------------------------------- collisions
    def _hit(self, att, vic, part, v, p, rel, kind):
        if self.phase != "fight" or not vic.alive or not att.alive:
            return
        key = (att.idx, part)
        if self.t - self.hit_cd.get(key, -9) < 0.22:
            return
        mult = WEAPONS[kind]["mult"] if kind != "bullet" else 1.0
        if kind == "bullet":
            dmg = 7.0
        else:
            if v < 420:
                return
            dmg = min(32.0, (v - 330) / 52.0 * mult)
        crit = part == "head"
        if crit:
            dmg *= 1.8
        elif part == "limb":
            dmg *= 0.6
        el = self.t - self.round_t0
        if el > 25:
            dmg *= 1 + (el - 25) / 8
        if dmg < 2.5:
            return
        self.hit_cd[key] = self.t
        vic.hp -= dmg
        vic.flash = self.t
        # hit reaction: interrupt, stagger (muscles go weak), hitstop freeze
        vic.seq = []
        vic.state, vic.state_end = "guard", self.t
        vic.stun_amt = min(1.0, dmg / 22)
        vic.stun_until = self.t + 0.12 + dmg * (0.02 if dmg < 16 else 0.04)
        self.hitstop = max(self.hitstop, min(5, 1 + int(dmg / 7)))
        if rel.length > 1:
            kb = rel.normalized() * min(9000, dmg * 330)
            vic.torso.apply_impulse_at_world_point(kb, vic.torso.position)
            if crit:
                vic.head.apply_impulse_at_world_point(kb * 0.25, vic.head.position)
        self.fx("hit", p.x, p.y, dmg, crit, vic.idx)
        big = dmg > 14
        self.sfx(self.t, "heavy" if big or kind == "hammer" else ("slash" if kind in ("sword", "axe", "spear") else "punch"), 0.05)
        if big:
            self.fx("shake", min(26.0, dmg * 1.2))
        if crit and dmg > 10 and not any(e[1] in ("text", "round") and self.vt - e[0] < 1.0
                                         for e in self.effects[-12:]):
            self.fx("text", "CRITICAL!", GOLD)
        if vic.hp <= 0:
            self.ko(vic, att)

    def _weapon_body(self, arb, space, data):
        ws, bs = arb.shapes
        if ws.owner is bs.owner or not arb.contact_point_set.points:
            return
        p = arb.contact_point_set.points[0].point_a
        rel = ws.body.velocity_at_world_point(p) - bs.body.velocity_at_world_point(p)
        self._hit(ws.owner, bs.owner, bs.part, rel.length, p, rel, ws.kind)

    def _clash(self, arb, space, data):
        a, b = arb.shapes
        if a.owner is b.owner or not arb.is_first_contact or not arb.contact_point_set.points:
            return
        p = arb.contact_point_set.points[0].point_a
        rel = a.body.velocity_at_world_point(p) - b.body.velocity_at_world_point(p)
        if rel.length > 350 and self.phase == "fight":
            self.fx("clash", p.x, p.y)
            self.sfx(self.t, "block", 0.1)

    def _bullet_body(self, arb, space, data):
        bs, body = arb.shapes
        if bs.owner is body.owner:
            return False
        p = bs.body.position
        self._hit(bs.owner, body.owner, body.part, 0, p, bs.body.velocity * 0.6, "bullet")
        self._kill_bullet(bs)
        return False

    def _bullet_other(self, arb, space, data):
        bs, other = arb.shapes
        if getattr(other, "owner", None) is bs.owner:
            return False
        self.fx("spark", bs.body.position.x, bs.body.position.y)
        self._kill_bullet(bs)
        return False

    def _kill_bullet(self, s):
        if s in self.bullets:
            self.bullets.remove(s)
            self.space.add_post_step_callback(lambda sp, k: sp.remove(s.body, s) if s.body in sp.bodies else None, s)

    def _spike(self, arb, space, data):
        hz, bs = arb.shapes
        f = bs.owner
        if self.phase != "fight" or not f.alive:
            return True
        if self.t - self.hit_cd.get(("spike", f.idx), -9) > 0.5:
            self.hit_cd[("spike", f.idx)] = self.t
            f.hp -= 9
            f.flash = self.t
            f.torso.apply_impulse_at_world_point((0, -f.mass * 900), f.torso.position)
            p = bs.body.position
            self.fx("hit", p.x, FLOOR - 30, 9, False, f.idx)
            self.sfx(self.t, "crack", 0.1)
            if f.hp <= 0:
                self.ko(f, None)
        return True

    def ko(self, vic, att):
        if self.phase != "fight":
            return
        vic.alive = False
        vic.hp = 0.0
        vic.go_limp()
        win = self.fighters[1 - vic.idx]
        self.round_winner = win
        self.score[win.idx] += 1
        self.phase, self.ko_t = "ko", self.t
        self.ko_vt = self.vt
        self.rounds.append(dict(round=self.round, winner=win.idx, t=self.t - self.round_t0,
                                hp=win.hp))
        # K.O. replaces any "CRITICAL!" that would overlap it
        self.effects = [e for e in self.effects if not (e[1] == "text" and self.vt - e[0] < 0.9)]
        self.fx("ko", win.idx)
        self.fx("shake", 30.0)
        self.sfx(self.t, "ko", 0)
        self.sfx(self.t, "crack", 0)

    # ---------------------------------------------------------------- main loop
    def step_frame(self):
        if self.hitstop > 0 and self.phase == "fight":      # hitstop: freeze a few frames on impact
            self.hitstop -= 1
            self.vt += 1.0 / FPS
            if self.record:
                self.frames.append(self.snapshot())
            return None
        slow = 1.0
        if self.phase == "ko" and self.vt - self.ko_vt < 1.4:
            slow = 0.25
        h = DT * slow
        for _ in range(SUB):
            for f in self.fighters:
                f.control(self.t, h)
            self.space.step(h)
            self.t += h
        for b in list(self.bullets):
            p = b.body.position
            if not (X0 < p.x < X1 and CEIL < p.y < FLOOR) or self.t - b.born > 2:
                self._kill_bullet(b)
        self.vt += 1.0 / FPS
        # phases
        if self.phase == "intro" and self.vt - self.phase_t > 1.6:
            self.phase, self.phase_t = "fight", self.vt
            self.fx("text", "FIGHT!", GOLD)
            self.sfx(self.t, "go", 0)
        elif self.phase == "ko" and self.vt - self.ko_vt > 3.0:
            if max(self.score) >= WIN_ROUNDS:
                self.phase, self.phase_t = "end", self.vt
                self.fx("winner", self.round_winner.idx)
                self.sfx(self.t, "fanfare", 0)
            else:
                return "next"
        elif self.phase == "fight" and self.t - self.round_t0 > 60:
            return "stuck"
        elif self.phase == "end" and self.vt - self.phase_t > 4.0:
            return "done"
        if self.record:
            self.frames.append(self.snapshot())
        return None

    def run(self, max_vt=200.0):
        self.new_round()
        while self.vt < max_vt:
            r = self.step_frame()
            if r == "next":
                self.new_round()
            elif r in ("done", "stuck"):
                self.result = r
                break
        else:
            self.result = "timeout"
        return self

    def snapshot(self):
        fs = []
        for f in self.fighters:
            segs = [(f.neck(), f.hip())]
            for ua, fa, *_ in f.arms:
                for b in (ua, fa):
                    s = b.shapes and [x for x in b.shapes if isinstance(x, pymunk.Segment) and x.collision_type == CT_BODY][0]
                    segs.append((b.local_to_world(s.a), b.local_to_world(s.b)))
            for th, sn, *_ in f.legs:
                for b in (th, sn):
                    s = [x for x in b.shapes if isinstance(x, pymunk.Segment)][0]
                    segs.append((b.local_to_world(s.a), b.local_to_world(s.b)))
            if f.weapon == "gloves":
                wpts = [f.arms[k][1].local_to_world(f.wshapes[k].offset) for k in range(2)]
            else:
                wpts = [f.weapon_base(), f.weapon_tip()]
            f.trail = (f.trail + [tuple(wpts[-1])])[-5:]
            fs.append(dict(segs=[(tuple(a), tuple(b)) for a, b in segs], head=tuple(f.head.position),
                           hang=f.head.angle, hp=max(0.0, f.hp), alive=f.alive, weapon=f.weapon,
                           w=[tuple(p) for p in wpts], flash=self.t - f.flash < 0.12,
                           facing=f.facing, trail=list(f.trail), shot=self.t - f.last_shot < 0.06))
        return dict(vt=self.vt, fighters=fs, bullets=[tuple(b.body.position) + tuple(b.body.velocity)
                                                      for b in self.bullets],
                    score=list(self.score), round=self.round, phase=self.phase,
                    weapons=self.round_weapons[self.round - 1])


def simulate(seed, record=False):
    return Game(seed, record).run()


def is_good(g):
    if g.result != "done":
        return False
    n = len(g.rounds)
    if n < 4:                                   # 3-1 or 3-2: there is a comeback / drama
        return False
    if not 55 <= g.vt <= 150:
        return False
    if any(r["t"] < 3.0 or r["t"] > 40 for r in g.rounds):
        return False
    return True


# ===================================================================== drawing
def _text(ctx, s, x, y, size, rgb, a=1.0, outline=0, italic=True, max_w=None):
    ctx.select_font_face("Inter", cairo.FONT_SLANT_ITALIC if italic else cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(size)
    ext = ctx.text_extents(s)
    if max_w and ext.width > max_w:
        size *= max_w / ext.width
        ctx.set_font_size(size)
        ext = ctx.text_extents(s)
    ctx.move_to(x - ext.width / 2 - ext.x_bearing, y)
    ctx.text_path(s)
    if outline:
        ctx.set_source_rgba(0, 0, 0, a)
        ctx.set_line_width(outline)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.stroke_preserve()
    ctx.set_source_rgba(*rgb, a)
    ctx.fill()


_BG = {}


def _background(g):
    key = (g.seed, g.map)
    if key in _BG:
        return _BG[key]
    th = g.theme
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    c = cairo.Context(s)
    gr = cairo.LinearGradient(0, 0, 0, H)
    gr.add_color_stop_rgb(0, *th["sky"][0])
    gr.add_color_stop_rgb(0.75, *th["sky"][1])
    gr.add_color_stop_rgb(1, *th["sky"][0])
    c.set_source(gr); c.paint()
    rng = random.Random(g.seed)
    # far silhouettes
    c.set_source_rgba(0, 0, 0, 0.35)
    if th["name"] in ("neon", "storm"):
        x = -20
        while x < W:
            w = rng.uniform(60, 140); hh = rng.uniform(200, 620)
            c.rectangle(x, FLOOR - hh, w, hh); x += w + rng.uniform(4, 20)
        c.fill()
        c.set_source_rgba(*th["line"], 0.25)
        for _ in range(140):
            c.rectangle(rng.uniform(0, W), FLOOR - rng.uniform(30, 560), 6, 9)
        c.fill()
    else:
        c.move_to(0, FLOOR)
        x = 0
        while x <= W + 100:
            c.line_to(x, FLOOR - rng.uniform(150, 520)); x += rng.uniform(120, 240)
        c.line_to(W, FLOOR); c.close_path(); c.fill()
        if th["name"] == "dojo":
            c.set_source_rgba(1, 0.85, 0.6, 0.18)
            c.arc(780, 760, 150, 0, 6.29); c.fill()
    # floor
    c.set_source_rgb(*th["floor"])
    c.rectangle(0, FLOOR, W, H - FLOOR); c.fill()
    c.set_source_rgba(*th["line"], 0.9); c.set_line_width(6)
    c.move_to(0, FLOOR); c.line_to(W, FLOOR); c.stroke()
    # arena walls (subtle)
    c.set_source_rgba(*th["line"], 0.25); c.set_line_width(4)
    c.move_to(X0, CEIL + 40); c.line_to(X0, FLOOR); c.move_to(X1, CEIL + 40); c.line_to(X1, FLOOR); c.stroke()
    # platforms
    for x0, x1, y in g.platforms:
        c.set_source_rgba(0, 0, 0, 0.4)
        c.rectangle(x0, y + 6, x1 - x0, 26); c.fill()
        c.set_source_rgb(*[v * 0.6 + 0.15 for v in th["floor"]])
        c.rectangle(x0, y - 10, x1 - x0, 22); c.fill()
        c.set_source_rgba(*th["line"], 0.9); c.set_line_width(4)
        c.move_to(x0, y - 10); c.line_to(x1, y - 10); c.stroke()
    # spikes
    for x0, x1 in g.spikes:
        n = int((x1 - x0) / 34)
        w = (x1 - x0) / n
        for k in range(n):
            c.move_to(x0 + k * w, FLOOR); c.line_to(x0 + k * w + w / 2, FLOOR - 46); c.line_to(x0 + (k + 1) * w, FLOOR)
        c.close_path()
        sg = cairo.LinearGradient(0, FLOOR - 46, 0, FLOOR)
        sg.add_color_stop_rgb(0, 0.95, 0.95, 1.0); sg.add_color_stop_rgb(1, 0.35, 0.35, 0.45)
        c.set_source(sg); c.fill()
        c.set_source_rgba(1, 0.2, 0.2, 0.25)
        c.rectangle(x0, FLOOR - 4, x1 - x0, 8); c.fill()
    _BG[key] = s
    return s


def _limb(ctx, a, b, col, w):
    ctx.move_to(*a); ctx.line_to(*b)


def _draw_weapon(ctx, f, col):
    k = f["weapon"]
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    # motion trail
    tr = f["trail"]
    if k != "gloves" and len(tr) > 2:
        for j in range(1, len(tr)):
            ctx.set_source_rgba(1, 1, 1, 0.08 * j)
            ctx.set_line_width(6 + 3 * j)
            ctx.move_to(*tr[j - 1]); ctx.line_to(*tr[j]); ctx.stroke()
    if k == "gloves":
        for (x, y) in f["w"]:
            ctx.set_source_rgb(0, 0, 0); ctx.arc(x, y, 27, 0, 6.29); ctx.fill()
            ctx.set_source_rgb(0.9, 0.12, 0.12) if col == RED else ctx.set_source_rgb(0.12, 0.35, 0.95)
            ctx.arc(x, y, 22, 0, 6.29); ctx.fill()
            ctx.set_source_rgba(1, 1, 1, 0.5); ctx.arc(x - 7, y - 8, 7, 0, 6.29); ctx.fill()
        return
    (x0, y0), (x1, y1) = f["w"]
    a = math.atan2(y1 - y0, x1 - x0)
    L = math.hypot(x1 - x0, y1 - y0)
    ctx.save(); ctx.translate(x0, y0); ctx.rotate(a)
    if k == "sword":
        ctx.set_source_rgb(0.4, 0.25, 0.12); ctx.rectangle(-26, -5, 26, 10); ctx.fill()
        ctx.set_source_rgb(1, 0.8, 0.2); ctx.rectangle(-4, -18, 10, 36); ctx.fill()
        ctx.move_to(6, -9); ctx.line_to(L - 22, -9); ctx.line_to(L + 4, 0); ctx.line_to(L - 22, 9); ctx.line_to(6, 9)
        ctx.close_path()
        ctx.set_source_rgb(0, 0, 0); ctx.set_line_width(5); ctx.stroke_preserve()
        g = cairo.LinearGradient(0, -9, 0, 9)
        g.add_color_stop_rgb(0, 1, 1, 1); g.add_color_stop_rgb(1, 0.6, 0.65, 0.75)
        ctx.set_source(g); ctx.fill()
    elif k == "spear":
        ctx.set_source_rgb(0, 0, 0); ctx.set_line_width(13); ctx.move_to(-30, 0); ctx.line_to(L - 30, 0); ctx.stroke()
        ctx.set_source_rgb(0.62, 0.42, 0.2); ctx.set_line_width(8); ctx.move_to(-30, 0); ctx.line_to(L - 30, 0); ctx.stroke()
        ctx.move_to(L - 40, -14); ctx.line_to(L + 12, 0); ctx.line_to(L - 40, 14); ctx.close_path()
        ctx.set_source_rgb(0, 0, 0); ctx.set_line_width(5); ctx.stroke_preserve()
        ctx.set_source_rgb(0.85, 0.88, 0.95); ctx.fill()
    elif k in ("axe", "hammer"):
        ctx.set_source_rgb(0, 0, 0); ctx.set_line_width(15); ctx.move_to(-20, 0); ctx.line_to(L, 0); ctx.stroke()
        ctx.set_source_rgb(0.55, 0.35, 0.16); ctx.set_line_width(9); ctx.move_to(-20, 0); ctx.line_to(L, 0); ctx.stroke()
        if k == "hammer":
            ctx.rectangle(L - 34, -40, 52, 80)
            ctx.set_source_rgb(0, 0, 0); ctx.set_line_width(6); ctx.stroke_preserve()
            ctx.set_source_rgb(0.55, 0.58, 0.66); ctx.fill()
            ctx.set_source_rgb(*col); ctx.rectangle(L - 34, -40, 52, 12); ctx.fill(); ctx.rectangle(L - 34, 28, 52, 12); ctx.fill()
        else:
            ctx.move_to(L - 30, -6); ctx.curve_to(L - 40, -50, L + 30, -60, L + 34, -10)
            ctx.line_to(L + 34, 10); ctx.curve_to(L + 30, 60, L - 40, 50, L - 30, 6); ctx.close_path()
            ctx.set_source_rgb(0, 0, 0); ctx.set_line_width(6); ctx.stroke_preserve()
            ctx.set_source_rgb(0.75, 0.78, 0.86); ctx.fill()
    elif k == "blaster":
        ctx.rectangle(-8, -14, L + 14, 24)
        ctx.set_source_rgb(0, 0, 0); ctx.set_line_width(6); ctx.stroke_preserve()
        ctx.set_source_rgb(0.25, 0.28, 0.35); ctx.fill()
        ctx.set_source_rgb(*col); ctx.rectangle(4, -10, L - 10, 6); ctx.fill()
        ctx.set_source_rgb(0.25, 0.28, 0.35); ctx.rectangle(-4, 8, 14, 22); ctx.fill()
        if f["shot"]:
            ctx.set_source_rgba(1, 0.95, 0.5, 0.95)
            ctx.move_to(L + 6, 0)
            for j in range(10):
                rr = 34 if j % 2 == 0 else 12
                aa = j * math.pi / 5
                ctx.line_to(L + 6 + rr * math.cos(aa), rr * math.sin(aa))
            ctx.close_path(); ctx.fill()
    ctx.restore()


def _draw_fighter(ctx, f, col):
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    c = (1, 1, 1) if f["flash"] else (col if f["alive"] else tuple(v * 0.75 for v in col))
    for wdt, cc in ((30, (0, 0, 0)), (19, c)):
        ctx.set_source_rgb(*cc)
        ctx.set_line_width(wdt)
        for a, b in f["segs"]:
            ctx.move_to(*a); ctx.line_to(*b)
        ctx.stroke()
    _draw_weapon(ctx, f, col)
    hx, hy = f["head"]
    ctx.set_source_rgb(0, 0, 0); ctx.arc(hx, hy, HEAD_R + 6, 0, 6.29); ctx.fill()
    ctx.set_source_rgb(*c); ctx.arc(hx, hy, HEAD_R, 0, 6.29); ctx.fill()
    # face
    fd = f["facing"]
    ctx.save(); ctx.translate(hx, hy); ctx.rotate(f["hang"] * 0.5)
    if not f["alive"]:
        ctx.set_source_rgb(0, 0, 0); ctx.set_line_width(5)
        for ex in (fd * 6, fd * 22):
            ctx.move_to(ex - 7, -12); ctx.line_to(ex + 7, 2); ctx.move_to(ex + 7, -12); ctx.line_to(ex - 7, 2)
        ctx.stroke()
    else:
        for ex in (fd * 4, fd * 21):
            ctx.set_source_rgb(1, 1, 1); ctx.arc(ex, -5, 8, 0, 6.29); ctx.fill()
            ctx.set_source_rgb(0, 0, 0); ctx.arc(ex + fd * 3, -4, 4, 0, 6.29); ctx.fill()
        ctx.set_source_rgb(0, 0, 0); ctx.set_line_width(5)          # angry brows
        ctx.move_to(fd * -6, -20); ctx.line_to(fd * 12, -12)
        ctx.move_to(fd * 13, -12); ctx.line_to(fd * 30, -19); ctx.stroke()
        if f["flash"]:
            ctx.arc(fd * 14, 13, 7, 0, 6.29); ctx.fill()
    ctx.restore()


def _particles(ctx, t, t0, x, y, col, seed, n=12, spd=520, life=0.35, w=6):
    dt = t - t0
    if not 0 <= dt <= life:
        return
    k = dt / life
    rng = random.Random(seed)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    for _ in range(n):
        a = rng.uniform(0, 6.28); v = rng.uniform(0.4, 1) * spd
        px, py = x + math.cos(a) * v * dt, y + math.sin(a) * v * dt
        ctx.set_source_rgba(*col, 1 - k); ctx.set_line_width(w * (1 - k) + 1)
        ctx.move_to(px, py); ctx.line_to(px - math.cos(a) * 18 * (1 - k), py - math.sin(a) * 18 * (1 - k)); ctx.stroke()


def camera_track(frames):
    """Fight camera: zooms in on the two fighters, follows them, keeps the floor low on screen."""
    out, cur = [], None
    for fr in frames:
        fs = fr["fighters"]
        xs = [f["segs"][0][1][0] for f in fs]
        heads = [f["head"][1] for f in fs]
        dx = abs(xs[0] - xs[1])
        z = max(1.15, min(1.75, 1080 * 0.62 / (dx + 260)))
        cx = sum(xs) / 2
        if fr["phase"] == "ko":
            z = min(1.95, z * 1.12)
        if fr["phase"] == "end":                       # close-up on the winner
            w = [f for f in fs if f["alive"]]
            if w:
                cx, z = w[0]["segs"][0][1][0], 1.7
        cy = FLOOR - 400 / z
        top = min(heads) - 140
        if (top - cy) * z + 1100 < 420:
            cy = top + 680 / z
        cx = max(X0 - 20 + 540 / z, min(X1 + 20 - 540 / z, cx))
        tgt = (cx, cy, z)
        cur = tgt if cur is None else tuple(c + (t - c) * 0.12 for c, t in zip(cur, tgt))
        out.append(cur)
    return out


def draw(ctx, g, fr, effects, cam=(540.0, 1100.0, 1.0)):
    t = fr["vt"]
    shake = 0.0
    for e in effects:
        if e[1] == "shake" and 0 <= t - e[0] < 0.3:
            shake = max(shake, e[2] * (1 - (t - e[0]) / 0.3))
    ox = oy = 0.0
    if shake:
        r = random.Random(int(t * 1000)); ox, oy = r.uniform(-shake, shake), r.uniform(-shake, shake)
    cx, cy, z = cam
    ctx.set_source_rgb(*g.theme["sky"][0]); ctx.paint()
    ctx.save()
    ctx.translate(540 + ox, 1100 + oy)
    ctx.scale(z, z)
    ctx.translate(-cx, -cy)
    ctx.set_source_surface(_background(g), 0, 0)
    ctx.paint()
    cols = (RED, BLUE)
    for i, f in enumerate(fr["fighters"]):
        if not f["alive"]:
            _draw_fighter(ctx, f, cols[i])
    for i, f in enumerate(fr["fighters"]):
        if f["alive"]:
            _draw_fighter(ctx, f, cols[i])
    for x, y, vx, vy in fr["bullets"]:
        sp = math.hypot(vx, vy) or 1
        ux, uy = vx / sp, vy / sp
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        for wdt, al, c in ((18, 0.35, GOLD), (8, 1.0, WHITE)):
            ctx.set_source_rgba(*c, al); ctx.set_line_width(wdt)
            ctx.move_to(x, y); ctx.line_to(x - ux * 46, y - uy * 46); ctx.stroke()
    for e in effects:
        dt = t - e[0]
        k = e[1]
        if k == "hit" and dt < 0.8:
            x, y, dmg, crit, vic = e[2:7]
            _particles(ctx, t, e[0], x, y, (1, 0.95, 0.6), int(e[0] * 997), n=10 + int(dmg), spd=420 + 18 * dmg, life=0.35)
            if dt < 0.12:
                ctx.set_source_rgba(1, 1, 1, 0.8 * (1 - dt / 0.12))
                ctx.arc(x, y, 30 + 3 * dmg, 0, 6.29); ctx.fill()
            kk = dt / 0.8
            _text(ctx, f"-{round(dmg)}", x + 40, y - 40 - 80 * kk, (44 if crit else 36) + 14 * (1 - kk) ** 3,
                  GOLD if crit else (1, 0.35, 0.3), 1 - kk ** 2, outline=7)
        elif k == "clash" and dt < 0.35:
            _particles(ctx, t, e[0], e[2], e[3], (0.7, 0.9, 1.0), int(e[0] * 991), n=16, spd=650, life=0.35)
        elif k == "spark" and dt < 0.25:
            _particles(ctx, t, e[0], e[2], e[3], GOLD, int(e[0] * 977), n=7, spd=360, life=0.25, w=4)
    ctx.restore()
    _hud(ctx, g, fr, effects)


def _hud(ctx, g, fr, effects):
    t = fr["vt"]
    _text(ctx, "RAGDOLL DUEL", 540, 92, 60, WHITE, 1, outline=8)
    _text(ctx, f"FIRST TO {WIN_ROUNDS} WINS", 540, 132, 28, GOLD, 0.95, outline=5)
    cols = (RED, BLUE)
    for i, f in enumerate(fr["fighters"]):
        side = -1 if i == 0 else 1
        x0 = 50 if i == 0 else 580
        hp = f["hp"] / 100
        ctx.set_source_rgba(0, 0, 0, 0.6); ctx.rectangle(x0 - 4, 160, 458, 42); ctx.fill()
        wv = 450 * hp
        ctx.set_source_rgb(*cols[i])
        ctx.rectangle(x0 + (450 - wv if side < 0 else 0), 164, wv, 34); ctx.fill()
        ctx.set_source_rgba(1, 1, 1, 0.9); ctx.set_line_width(3); ctx.rectangle(x0 - 4, 160, 458, 42); ctx.stroke()
        nx = x0 + 90 if side < 0 else x0 + 360
        _text(ctx, g.names[i], nx, 244, 40, cols[i], 1, outline=6)
        _text(ctx, f["weapon"].upper(), nx, 280, 26, WHITE, 0.9, outline=5, italic=False)
        for k in range(WIN_ROUNDS):                     # round pips
            px = (x0 + 200 + k * 34) if side < 0 else (x0 + 250 - k * 34)
            ctx.set_source_rgb(0, 0, 0); ctx.arc(px, 236, 13, 0, 6.29); ctx.fill()
            if fr["score"][i] > k:
                ctx.set_source_rgb(*GOLD); ctx.arc(px, 236, 10, 0, 6.29); ctx.fill()
            else:
                ctx.set_source_rgba(1, 1, 1, 0.3); ctx.set_line_width(3); ctx.arc(px, 236, 9, 0, 6.29); ctx.stroke()
    _text(ctx, "VS", 540, 194, 40, WHITE, 1, outline=6)
    # center messages
    for e in effects:
        dt = t - e[0]
        k = e[1]
        if k == "round" and 0 <= dt < 1.6:
            a = min(1.0, (1.6 - dt) / 0.3)
            pop = 1 + 0.4 * max(0, 1 - dt / 0.12)
            _text(ctx, f"ROUND {e[2]}", 540, 470, 120 * pop, WHITE, a, outline=14)
            if e[3]:
                _text(ctx, e[3], 540, 560, 64, GOLD, a, outline=10)
            _text(ctx, f"{e[4].upper()}  vs  {e[5].upper()}", 540, 640 if e[3] else 570, 50, (0.85, 0.9, 1), a,
                  outline=8)
        elif k == "text" and 0 <= dt < 0.9:
            a = min(1.0, (0.9 - dt) / 0.25)
            pop = 1 + 0.5 * max(0, 1 - dt / 0.1)
            _text(ctx, e[2], 540, 480, 100 * pop, e[3], a, outline=12)
        elif k == "ko" and 0 <= dt < 2.6:
            a = min(1.0, (2.6 - dt) / 0.4)
            pop = 1 + 1.2 * max(0, 1 - dt / 0.1)
            _text(ctx, "K.O.!", 540, 530, 200 * pop, (1, 0.22, 0.22), a, outline=16)
            if dt > 0.6:
                _text(ctx, f"{g.names[e[2]]} WINS THE ROUND", 540, 620, 54, (RED, BLUE)[e[2]],
                      min(a, (dt - 0.6) / 0.3), outline=8)
        elif k == "winner" and dt >= 0:
            a = min(1.0, dt / 0.3)
            _text(ctx, f"{g.names[e[2]]} WINS!", 540, 480, 150, (RED, BLUE)[e[2]], a, outline=16)
            _text(ctx, f"{fr['score'][e[2]]} - {fr['score'][1 - e[2]]}", 540, 590, 90, WHITE, a, outline=12)
            _text(ctx, "Did you pick the winner?", 540, 670, 54, GOLD, a, outline=8)
    _text(ctx, "COMMENT: RED OR BLUE?", 540, 1660, 40, WHITE, 0.9, outline=6)


# ===================================================================== render
def render(seed, out_base):
    g = Game(seed, record=True).run()
    frames = g.frames
    total = len(frames) / FPS
    sections = [(0, 1.6, 0), (1.6, total, 3), (total - 4, total + 2, 1)]
    wav = out_base + ".wav"
    fightaudio.mix(total + 0.6, g.sounds, sections, wav, seed)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    tmp = out_base + ".v.mp4"
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                           "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    eff = sorted(g.effects, key=lambda e: e[0])
    cams = camera_track(frames)
    lo = 0
    for fi, fr in enumerate(frames):
        t = fr["vt"]
        while lo < len(eff) and t - eff[lo][0] > 3.0 and eff[lo][1] != "winner":
            lo += 1
        view = [e for e in eff[lo:] if e[0] <= t]
        draw(ctx, g, fr, view, cams[fi])
        surf.flush()
        ff.stdin.write(bytes(surf.get_data()))
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-i", wav, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "160k", "-shortest", "-movflags", "+faststart", out_base + ".mp4"], check=True)
    os.remove(tmp); os.remove(wav)
    # cover: a big hit in the middle of the match
    hits = [e for e in eff if e[1] == "hit" and e[4] > 12 and 0.3 * total < e[0] < 0.8 * total]
    ct = hits[0][0] + 0.05 if hits else total * 0.45
    fi = min(len(frames) - 1, int(ct * FPS))
    draw(ctx, g, frames[fi], [e for e in eff if e[0] <= frames[fi]["vt"] and frames[fi]["vt"] - e[0] < 3], cams[fi])
    surf.write_to_png(out_base + "_cover.png")
    return g, round(total, 2)


def find_seed(start, tries=400):
    for s in range(start, start + tries):
        if is_good(simulate(s)):
            return s
    return start


TITLES = [
    "Ragdoll stickman duel: RED vs BLUE — who wins? 🔴🔵",
    "Random weapon every round ⚔️ Who wins the ragdoll duel?",
    "This ragdoll fight went to the FINAL ROUND 😳",
    "{w} vs {v}… pick a side! 🔥 Ragdoll Duel",
    "First to 3 wins — RED or BLUE? ⚔️",
    "The comeback in round {n} 😱 Ragdoll stickman fight",
]


def make_meta(g, seed):
    rng = random.Random(seed * 31 + 3)
    wa, wb = g.round_weapons[0]
    title = rng.choice(TITLES).format(w=wa.title(), v=wb.title(), n=len(g.rounds))
    desc = "\n".join([
        "Two ragdoll stickmen, real physics, and a random weapon every round: swords, axes, hammers, "
        "spears, boxing gloves and blasters. First to 3 round wins takes the duel.",
        "Who did you pick? Comment RED or BLUE 👇",
        "",
        "New stickman fights every day — subscribe! 🔔",
        "Simulated and animated entirely with code. Music and sound effects are original and synthesized.",
        "",
        "#shorts #stickman #ragdoll #stickfight #physics #animation",
    ])
    tags = ["stickman", "ragdoll", "stickman fight", "ragdoll physics", "stick fight", "red vs blue",
            "physics simulation", "shorts", "stick figure", "duel", "sword fight", "animation"]
    return dict(title=f"{title} #shorts"[:100], description=desc, tags=tags, categoryId="1",
                containsSyntheticMedia=False)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    s = find_seed(a.seed)
    g, d = render(s, os.path.join(a.out, f"duel_{s}"))
    print("seed", s, "duration", d, "score", g.score, make_meta(g, s)["title"])
