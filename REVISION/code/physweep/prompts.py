"""
physweep/prompts.py
===================
Text-channel prompts, copied verbatim from the v1 experiment scripts
(experiments/e0_pilot.py: gravity_prompt; experiments/e4_generality.py: the
other five builders and NEGATIVE_PROMPT; experiments/e3e5_extended.py: the
terse/verbose variants) so the v2 harness does not import those scripts, which
load torch and diffusers at import time. The wording is unchanged on purpose,
with ONE exception: the g > 16 gravity prompt says "very rapid" instead of
"violent rapid" (2026-10-17), because the Cosmos guardrail blocked "violent".
"""

NEGATIVE_PROMPT = "blurry, distorted, artifacts, morphing, multiple objects, text, watermark"


def gravity_prompt(g: float) -> str:
    if g <= 2.0:
        qual = "extremely weak gravity, like the Moon, very gentle slow-motion drifting fall"
    elif g <= 6.0:
        qual = "weak gravity, slow floaty fall"
    elif g <= 11.0:
        qual = "normal Earth-like gravity, natural falling speed"
    elif g <= 16.0:
        qual = "strong gravity, fast falling speed"
    else:
        # v1 said "violent rapid acceleration downward"; reworded for ALL models on 2026-10-17 because
        # the Cosmos guardrail's fuzzy blocklist matched "violent" to "violet" and blocked the prompt
        qual = "extremely strong gravity, like Jupiter, very rapid acceleration downward"
    return (f"a dark ball falling on a plain background with acceleration {g:.1f} meters "
            f"per second squared, {qual}, simple physics simulation")


def pendulum_omega_prompt(omega: float) -> str:
    if omega <= 3: qual = "swinging slowly, low frequency oscillation"
    elif omega <= 6: qual = "swinging at a natural, moderate speed"
    else: qual = "swinging extremely fast, rapid high-frequency oscillation"
    return (f"a dark ball on a pendulum swinging with angular frequency {omega:.1f} radians per "
            f"second, {qual}, simple physics simulation, plain background")


def pendulum_zeta_prompt(zeta: float) -> str:
    if zeta <= 0.1: qual = "swinging with almost no damping, oscillating steadily for a long time"
    elif zeta <= 0.3: qual = "swinging with noticeable damping, the swings shrinking over time"
    else: qual = "heavily damped, quickly settling to a stop, barely swinging at all"
    return (f"a dark ball on a pendulum with damping ratio {zeta:.2f}, {qual}, "
            f"simple physics simulation, plain background")


def bouncing_ball_prompt(e: float) -> str:
    if e <= 0.4: qual = "a dead, unbouncy ball that barely bounces at all and quickly stops"
    elif e <= 0.9: qual = "a normal bouncy ball bouncing with decreasing height each time"
    else: qual = "an extremely bouncy, superball-like ball that keeps bouncing almost as high each time"
    return (f"a dark ball bouncing on the ground with coefficient of restitution {e:.2f}, "
            f"{qual}, simple physics simulation, plain background")


def spring_mass_prompt(k: float) -> str:
    if k <= 15: qual = "a very soft, loose spring oscillating slowly"
    elif k <= 100: qual = "a normal spring oscillating at a moderate rate"
    else: qual = "an extremely stiff, rigid spring oscillating very rapidly"
    return (f"a dark ball attached to a spring with stiffness {k:.1f} newtons per meter, "
            f"{qual}, simple physics simulation, plain background")


def inclined_slide_prompt(mu: float) -> str:
    if mu <= 0.05: qual = "an almost frictionless surface, the ball sliding very fast with little resistance"
    elif mu <= 0.4: qual = "a normal surface with moderate friction, sliding steadily"
    else: qual = "an extremely high-friction, sticky surface, the ball barely sliding at all"
    return (f"a dark ball sliding down an incline with friction coefficient {mu:.2f}, "
            f"{qual}, simple physics simulation, plain background")


PROMPT_BUILDERS = {
    "projectile": gravity_prompt,
    "pendulum_omega": pendulum_omega_prompt,
    "pendulum_zeta": pendulum_zeta_prompt,
    "bouncing_ball": bouncing_ball_prompt,
    "spring_mass": spring_mass_prompt,
    "inclined_slide": inclined_slide_prompt,
}


def terse_prompt(system: str, theta: float) -> str:
    unit = {"projectile": "meters per second squared", "pendulum_omega": "radians per second",
            "pendulum_zeta": "", "bouncing_ball": "", "spring_mass": "newtons per meter",
            "inclined_slide": ""}[system]
    name = {"projectile": "acceleration", "pendulum_omega": "angular frequency",
            "pendulum_zeta": "damping ratio", "bouncing_ball": "coefficient of restitution",
            "spring_mass": "spring stiffness", "inclined_slide": "friction coefficient"}[system]
    return f"a dark ball, {name} {theta:.2f} {unit}".strip()


def verbose_prompt(system: str, theta: float) -> str:
    return (f"{PROMPT_BUILDERS[system](theta)}, precise physically accurate simulation, exact numerical value, "
            f"photorealistic rendering, laboratory measurement setup")


def build_prompt(system: str, theta: float, variant: str = "default") -> str:
    if variant == "default":
        return PROMPT_BUILDERS[system](theta)
    return {"terse": terse_prompt, "verbose": verbose_prompt}[variant](system, theta)
