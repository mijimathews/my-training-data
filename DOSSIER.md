# Athlete Training Dossier & Performance Roadmap

**Dossier Version:** v1.1.1
**Protocol Compatibility:** Section 11 v11.6+
**Date:** 2026-03-04
**Primary Source Systems:** Intervals.icu

---

## 1. Athlete Overview

### Athlete Profile

| Field | Value |
|-------|-------|
| Name | Miji Mathews |
| Weight | 88 kg |
| Location | Highlands, Australia |

### Sport Focus

| Type | Description |
|------|-------------|
| Primary | Cycling performance (Endurance) |

### Goals

| Goal | Target Date |
|------|-------------|
| Highlands Gran Fondo | June 7, 2026 |
| Build CTL to 70 | June 2026 |
| Improve W/kg to 3.0 | 2026 |

**Current Phase:** Aerobic base building
**Training Style:** Polarized (~10h/week, progressing to 12h/week)

---

## 2. Equipment & Environment

### Indoor Training Setup

| Component | Details |
|-----------|---------|
| Platform | Zwift / Indoor trainer |

### Outdoor Setup

| Component | Details |
|-----------|---------|
| Bike | Road bike |
| Power Meter | Yes |

---

## 3. Training Schedule & Framework

### Weekly Volume Target

**Baseline:** 10 hours/week (± 1 hour)
**Volume progression target:** 12 hours/week by race week (increase max 10% per week)
**Peak phases:** Up to 12 hours (requires RI >= 0.8, HRV within 10%)

### Normal Weekly Schedule

| Day | Primary Session | Duration | Notes |
|-----|-----------------|----------|-------|
| Monday | REST | -- | Rest day |
| Tuesday | Z2 Endurance | 2h | Steady-state |
| Wednesday | Z2 Endurance | 1.5h | Easy spin |
| Thursday | Z2 Endurance | 2h | Steady-state |
| Friday | REST / Active Recovery | 45min | Rest or AE-4 |
| Saturday | Long Z2 Durability | 3h | Long ride |
| Sunday | Z2 Endurance | 2h | Steady-state |

### Recovery Protocol

**Recovery Triggers (Auto-Deload):**
- HRV down > 20% → Reduce to Z1/Z2 only
- RHR up >= 5 bpm → Skip hard session
- Feel >= 4 → Complete rest
- Two+ triggers → Full rest day

**Feel Scale:**
| Score | Meaning |
|-------|---------|
| 1 | Excellent (fully recovered) |
| 2 | Good (normal fatigue) |
| 3 | Moderate (manageable tiredness) |
| 4 | Fatigued (reduced readiness, deload trigger) |
| 5 | Exhausted (complete rest required) |

---

## 4. Performance Metrics

### Current Power Zones

| Zone | % of FTP | Power (W) | Notes |
|------|----------|-----------|-------|
| Z1 | 0-55% | 0-127 | Active Recovery |
| Z2 | 56-75% | 128-173 | Endurance (Base) |
| Z3 | 76-90% | 174-207 | Tempo |
| Z4 | 91-105% | 208-242 | Threshold |
| Z5 | 106-120% | 243-276 | VO2max |
| Z6 | 121-150% | 277-345 | Anaerobic |
| Z7 | 151%+ | 346+ | Neuromuscular |
| SS | 84-97% | 193-223 | Sweetspot |

**Current FTP:** 230W (Indoor: 235W)
**Max HR:** 190 bpm
**Threshold HR (LTHR):** 172 bpm

### Current Fitness Markers

| Metric | Value | Notes |
|--------|-------|-------|
| FTP (Outdoor) | 230W | |
| FTP (Indoor) | 235W | Adjusted for indoor conditions |
| eFTP | 230W | |
| W' | 19.4 kJ | |
| P-max | 851W | |
| CTL | 41 | |
| ATL | 38 | |
| TSB | +3.3 | |
| Resting HR | 54 bpm | |
| Weight | 88 kg | |
| W/kg | 2.61 | Target: 3.0 |

---

## 5. Nutrition / Fueling

### Fueling by Workout Type

| Workout Type | Duration | CHO Target | Setup |
|--------------|----------|------------|-------|
| Recovery / Z1-Z2 | < 1.5 h | Water only | -- |
| Endurance | 1.5-3 h | 60 g/h | Bottle mix |
| Long Endurance | 3-6 h | 80 g/h | Bottle mix + bars |
| Threshold / SS | 1-2 h | 60 g/h | Bottle mix |
| Race / Event | 4-6 h | 90 g/h | Bottle mix + gels |

---

## 6. Adaptation & Current Focus

### Current Adaptation Focus

- [ ] Build aerobic base (CTL 41 -> 70 by June)
- [ ] Improve durability for 4+ hour efforts
- [ ] Maintain polarized training distribution
- [ ] Increase outdoor ride frequency as weather permits

---

## 8. Long-Term Performance Roadmap

### Primary Objective

Complete Highlands Gran Fondo (June 7, 2026) with strong performance

### Event-Specific Targets

| Event/Segment | Year | Priority | Target |
|---------------|------|----------|--------|
| Highlands Gran Fondo | 2026 | RACE_B | Complete with CTL >= 65 |

> **Race tagging for automated protocol activation:** Tag races in Intervals.icu as `RACE_A`, `RACE_B`, or `RACE_C` using the event category selector. The race-week protocol (Section 11A) activates automatically for A and B races within 7 days.

---

## Data Mirror Configuration

### JSON Endpoint (for AI coaches)

**URL:** `https://raw.githubusercontent.com/mijimathews/my-training-data/main/latest.json`

**History:** `https://raw.githubusercontent.com/mijimathews/my-training-data/main/history.json`

**Archive:** `https://github.com/mijimathews/my-training-data/tree/main/archive`

This endpoint provides synchronized Intervals.icu metrics for deterministic AI parsing. See **Section 11** for the full AI Coach Guidance Protocol.

---

## Protocol Reference

This dossier follows the **Section 11 A/B AI Coach Guidance Protocol** for AI integration.

**Protocol Location:** https://github.com/CrankAddict/section-11

---

## Changelog

### v1.0 (2026-03-04)
- Initial dossier creation from CrankAddict template
- Populated with athlete data from Intervals.icu
