# Jovian front: echoes of war
![deploy badge](https://github.com/francescorinaldi/jovian-front-web/actions/workflows/build-and-deploy.yml/badge.svg)

> A hard‑science, top‑down space‑combat prototype set in the turbulent Jovian system, built with **Pygame** for desktop and **pygbag** for instant WebAssembly deployments.

---

## overview

*In 2112 two rival blocs—the resource‑driven **Jovian Concord** and the militarised **Terran Mandate**—wage limited war for helium‑3 and moon‑born metals.*  
You pilot a nimble interceptor, balance power and heat, out‑maneuver AI raiders, and master true Newtonian flight.

### key features

- Newtonian movement with screen‑wrap for quick testing  
- Three player weapons (laser, railgun, missile) plus manual point defences  
- Component heat & damage management; systems lock when overheated  
- Basic enemy AI: pursuit, heat limits, range‑based firing  
- Minimal UI with dynamic hull & heat bars  
- One‑file codebase for clarity; WASM build served via GitHub Pages  

### gameplay loop

1. **engage** – Rotate (←/→) and thrust (↑) to close on the enemy  
2. **fire** – Select weapons (1–3) and shoot (Space) while watching heat  
3. **defend** – Burst point defence (P) to snipe incoming fire, reload (R)  
4. **adapt** – Cool down, manage inertia, finish the fight  
5. **victory / defeat** – Text splash, then restart for fast iteration  

### controls

| key | action |
|-----|--------|
| ← / → | rotate ship |
| ↑ | thrust |
| 1 / 2 / 3 | laser / railgun / missile |
| **space** | fire current weapon |
| **p** | point‑defence burst |
| **r** | reload PD |
| esc | quit (desktop) |

## hard‑science design pillars

- No reactionless drives: fusion engines impart realistic acceleration  
- Energy weapons create heat; radiators & cooldown in real seconds  
- Missiles carry finite Δv and course‑correct each frame  
- Sensors, EW, and resource limits will expand in later milestones  

## live demo

Play the latest build in your browser:  
<https://francescorinaldi.github.io/jovian-front-web/>

*(Desktop Chrome/Firefox auto‑starts; mobile Safari requires one tap to un‑mute audio.)*

## running locally (desktop)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                     # installs pygame only
python main.py
