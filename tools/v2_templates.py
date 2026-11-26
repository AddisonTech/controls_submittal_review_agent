"""System templates for test set v2 (spec compliance packages).

Each template returns the governing specification content (sequence sections and
points schedule) and the contractor submittal content (paraphrased sequence,
points list, drawing device list) for one HVAC system, plus the slots where an
error can be planted.

Sources (see validation/v2/SOURCES.md):
  - Sequence logic follows the ASHRAE Guideline 36 implementations documented in
    the Modelica Buildings Library (BSD 3-clause style license), package
    Buildings.Controls.OBC.ASHRAE.G36, commit 79f33d6. No Guideline 36 text is
    copied; the sentences here are written for this project.
  - Points schedule columns follow UFGS 23 09 00 paragraph 3.3.10 and alarm
    wording follows UFGS 23 09 00 paragraph 1.4.1 (US Government works).
Every value, tag and sentence is synthetic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

ERROR_TYPES = ("point_missing", "wrong_point_type", "sequence_contradiction", "setpoint_out_of_spec",
               "alarm_wrong_or_missing", "interlock_missing", "unit_scaling_mismatch", "device_tag_mismatch",
               "ddc_hardware_mismatch")
PROSE_KEYS = {"contra": "sequence_contradiction", "setpt": "setpoint_out_of_spec",
              "alarm": "alarm_wrong_or_missing", "interlock": "interlock_missing"}
ABSENT = None  # an error variant of None deletes the submittal paragraph


@dataclass
class Para:
    num: str
    spec: str
    sub: str
    errs: dict = field(default_factory=dict)  # contra / setpt / alarm / interlock -> erroneous submittal text or ABSENT


@dataclass
class Section:
    num: str
    title: str
    paras: list


@dataclass
class Alarm:
    level: int
    kind: str  # above, below, dev, trip, mismatch, belowpct
    value: Optional[float] = None
    delay: Optional[int] = None


@dataclass
class Point:
    name: str
    desc: str
    io: str  # AI, AO, BI, BO
    kind: str  # temp, dtemp, press, flow, pct, bin, wflow, wdp, ppm
    rng: tuple
    device: str
    ddc: str
    alarm: Optional[Alarm] = None
    bad_io: Optional[str] = None  # the wrong type a planted error uses
    settings: str = ""


@dataclass
class Device:
    tag: str
    desc: str
    ddc: str
    sheet: str
    points: list  # point names; an empty list renders as the note in `note`
    note: str = ""


@dataclass
class System:
    key: str
    eq: str
    title: str
    sections: list
    points: list
    devices: list
    extras: dict  # paragraph number after which a contractor paragraph is added -> (number, text)
    local_devices: list  # drawing list devices with no BAS point (look-alike)


def c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


# ---------------------------------------------------------------------------
# A: multizone VAV air handling unit (G36 5.16)
# ---------------------------------------------------------------------------
def ahu_multizone(n: int, v: int) -> tuple[System, dict]:
    eq = f"AHU-{n}"
    p = dict(eq=eq, sp_min=0.15, sp_max=(1.2, 1.5, 1.8)[v % 3], sp_ini=1.0, sp_trim=0.05, sp_res=0.06,
             sp_resmax=0.15, ign=2, fan_min=(20, 25, 30)[v % 3], sat_min=55, sat_max=(65, 60, 63)[v % 3],
             oat_max=70, oat_min=60, sat_warm=(95, 90, 92)[v % 3], econ_hl=(75, 65, 70)[v % 3], econ_db=1,
             min_oa=(3200, 4500, 2600, 5800)[v % 4], fz1=40, fz1_hold=42, fz1_end=45, fz2=38, fz3=34,
             hs=(3.0, 3.5, 2.5)[v % 3], flt=1.0)
    p.update(sp_max_bad=round(p["sp_max"] + 1.0, 2), fan_min_bad=p["fan_min"] - 15, sat_min_bad=50,
             sat_max_bad=p["sat_max"] + 7, sat_warm_bad=p["sat_warm"] + 20, econ_hl_bad=p["econ_hl"] + 12,
             min_oa_bad=int(round(p["min_oa"] * 0.6, -2)), hs_bad=round(p["hs"] + 2.0, 1), fz1_bad=35)
    S = [
        Section("3.1", "Supply Fan Control", [
            Para("3.1.1", "The supply fan shall run when the system is in the Cool-down, Setup or Occupied mode.",
                 "The supply fan runs in the Occupied, Cool-down and Setup modes.",
                 {"contra": "The supply fan runs in the Occupied, Cool-down, Setup and Setback modes."}),
            Para("3.1.2", "No zone served by {eq} has reheat, so the supply fan shall not run in the Setback or Warmup mode.",
                 "Since no zone on {eq} has reheat, the supply fan stays off in the Setback and Warmup modes."),
            Para("3.1.3", "The duct static pressure setpoint shall be reset by trim and respond logic between {P:sp_min} and {P:sp_max}, starting from {P:sp_ini}.",
                 "Trim and respond logic resets the duct static pressure setpoint between a minimum of {P:sp_min} and a maximum of {P:sp_max}, with an initial value of {P:sp_ini}.",
                 {"setpt": "Trim and respond logic resets the duct static pressure setpoint between a minimum of {P:sp_min} and a maximum of {P:sp_max_bad}, with an initial value of {P:sp_ini}."}),
            Para("3.1.4", "Every 2 minutes the setpoint shall be trimmed by {P:sp_trim} when fewer than {ign} zone pressure requests are present, and raised by {P:sp_res} for each request above that number, up to {P:sp_resmax} per interval.",
                 "At 2 minute intervals the logic lowers the setpoint by {P:sp_trim} if there are fewer than {ign} zone pressure requests, and otherwise raises it by {P:sp_res} per request beyond {ign}, limited to {P:sp_resmax} per interval.",
                 {"setpt": "At 10 minute intervals the logic lowers the setpoint by {P:sp_trim} if there are fewer than {ign} zone pressure requests, and otherwise raises it by {P:sp_res} per request beyond {ign}, limited to {P:sp_resmax} per interval."}),
            Para("3.1.5", "When the supply fan is proven on, supply fan speed shall be modulated by a PI loop to maintain duct static pressure at setpoint.",
                 "With the supply fan proven on, a PI loop modulates fan speed to hold duct static pressure at setpoint.",
                 {"contra": "With the supply fan proven on, a PI loop modulates fan speed to hold supply airflow at the scheduled design airflow."}),
            Para("3.1.6", "Supply fan speed shall not be reduced below {fan_min} percent.",
                 "The minimum supply fan speed is {fan_min} percent.",
                 {"setpt": "The minimum supply fan speed is {fan_min_bad} percent."}),
            Para("3.1.7", "The return fan shall start when the supply fan is proven on and shall stop when the supply fan stops.",
                 "The return fan is started after the supply fan proves on and is stopped whenever the supply fan stops.",
                 {"interlock": ABSENT}),
        ]),
        Section("3.2", "Supply Air Temperature Control", [
            Para("3.2.1", "The supply air temperature control loop shall be enabled when the supply fan is proven on; otherwise the loop shall be disabled with heating off and the economizer at minimum position.",
                 "The supply air temperature loop is enabled only while the supply fan is proven on. When it is disabled, heating is off and the economizer is at minimum position.",
                 {"contra": "The supply air temperature loop is enabled as soon as the supply fan is commanded on, without waiting for proof of flow. When it is disabled, heating is off and the economizer is at minimum position."}),
            Para("3.2.2", "During Occupied and Setup modes the supply air temperature setpoint shall be reset from {T:sat_min} when the outdoor air temperature is {T:oat_max} and above, proportionally up to the maximum supply air temperature setpoint when the outdoor air temperature is {T:oat_min} and below.",
                 "In the Occupied and Setup modes the supply air temperature setpoint is {T:sat_min} with outdoor air at {T:oat_max} or warmer and rises linearly to the maximum setpoint with outdoor air at {T:oat_min} or cooler.",
                 {"setpt": "In the Occupied and Setup modes the supply air temperature setpoint is {T:sat_min_bad} with outdoor air at {T:oat_max} or warmer and rises linearly to the maximum setpoint with outdoor air at {T:oat_min} or cooler.",
                  "contra": "In the Occupied and Setup modes the supply air temperature setpoint is the maximum setpoint with outdoor air at {T:oat_max} or warmer and falls linearly to {T:sat_min} with outdoor air at {T:oat_min} or cooler."}),
            Para("3.2.3", "The maximum supply air temperature setpoint shall be reset by trim and respond logic between {T:sat_min} and {T:sat_max}.",
                 "The maximum supply air temperature setpoint is reset by trim and respond logic within the range {T:sat_min} to {T:sat_max}.",
                 {"setpt": "The maximum supply air temperature setpoint is reset by trim and respond logic within the range {T:sat_min} to {T:sat_max_bad}."}),
            Para("3.2.4", "During Cool-down mode the supply air temperature setpoint shall be {T:sat_min}.",
                 "In Cool-down mode the supply air temperature setpoint is fixed at {T:sat_min}.",
                 {"contra": "In Cool-down mode the supply air temperature setpoint is fixed at {T:sat_max}."}),
            Para("3.2.5", "During Setback and Warmup modes the supply air temperature setpoint shall be {T:sat_warm}.",
                 "In Setback and Warmup modes the supply air temperature setpoint is {T:sat_warm}.",
                 {"setpt": "In Setback and Warmup modes the supply air temperature setpoint is {T:sat_warm_bad}."}),
            Para("3.2.6", "The loop output shall sequence the heating coil valve, then the outdoor and return air dampers, then the chilled water valve, to maintain the supply air temperature at setpoint.",
                 "As the loop output rises it strokes the heating coil valve closed first, then modulates the outdoor and return air dampers, and finally opens the chilled water valve.",
                 {"contra": "As the loop output rises it opens the chilled water valve first, then modulates the outdoor and return air dampers, and finally strokes the heating coil valve closed."}),
        ]),
        Section("3.3", "Economizer and Minimum Outdoor Air", [
            Para("3.3.1", "The economizer shall be disabled when the outdoor air temperature exceeds {T:econ_hl} and enabled again when it falls {dT:econ_db} below that limit.",
                 "Economizer operation is locked out above an outdoor air temperature of {T:econ_hl} and released once the outdoor air temperature drops {dT:econ_db} below the limit.",
                 {"setpt": "Economizer operation is locked out above an outdoor air temperature of {T:econ_hl_bad} and released once the outdoor air temperature drops {dT:econ_db} below the limit."}),
            Para("3.3.2", "The economizer shall be disabled whenever freeze protection stage 2 or higher is active.",
                 "Economizer operation is disabled during freeze protection stage 2 and stage 3.",
                 {"contra": "Economizer operation is disabled during freeze protection stage 3 only."}),
            Para("3.3.3", "The minimum outdoor airflow setpoint shall be {F:min_oa}, maintained by modulating the minimum outdoor air damper against the airflow measuring station.",
                 "The minimum outdoor air damper modulates to hold the measured outdoor airflow at the {F:min_oa} minimum setpoint.",
                 {"setpt": "The minimum outdoor air damper modulates to hold the measured outdoor airflow at the {F:min_oa_bad} minimum setpoint."}),
            Para("3.3.4", "When the supply fan is off, the outdoor air dampers shall be closed and the return air damper shall be open.",
                 "With the supply fan off, the outdoor air dampers are closed and the return air damper is open.",
                 {"contra": "With the supply fan off, the outdoor air dampers and the return air damper are all closed."}),
            Para("3.3.5", "When the economizer is enabled, the economizer outdoor air damper and the return air damper shall be modulated in sequence to maintain the supply air temperature setpoint.",
                 "When the economizer is enabled, the economizer outdoor air and return air dampers modulate in sequence to hold supply air temperature at setpoint."),
        ]),
        Section("3.4", "Freeze Protection", [
            Para("3.4.1", "If the supply air temperature drops below {T:fz1} for 5 minutes, the controller shall send two heating hot water plant requests, override the outdoor air damper to minimum position, and modulate the heating coil to keep the supply air temperature at or above {T:fz1_hold}; this stage shall end when the supply air temperature is above {T:fz1_end} for 5 minutes.",
                 "Stage 1: when supply air temperature stays below {T:fz1} for 5 minutes, the controller sends two heating hot water plant requests, holds the outdoor air damper at minimum position and modulates the heating coil to maintain at least {T:fz1_hold}; stage 1 ends after the supply air temperature is above {T:fz1_end} for 5 minutes.",
                 {"setpt": "Stage 1: when supply air temperature stays below {T:fz1_bad} for 5 minutes, the controller sends two heating hot water plant requests, holds the outdoor air damper at minimum position and modulates the heating coil to maintain at least {T:fz1_hold}; stage 1 ends after the supply air temperature is above {T:fz1_end} for 5 minutes.",
                  "contra": "Stage 1: when supply air temperature stays below {T:fz1} for 5 minutes, the controller sends two heating hot water plant requests, drives the outdoor air damper fully open and modulates the heating coil to maintain at least {T:fz1_hold}; stage 1 ends after the supply air temperature is above {T:fz1_end} for 5 minutes."}),
            Para("3.4.2", "If the supply air temperature drops below {T:fz2} for 5 minutes, the economizer and minimum outdoor air dampers shall close for 1 hour and a Level 3 alarm shall be set noting that minimum ventilation was interrupted.",
                 "Stage 2: when supply air temperature stays below {T:fz2} for 5 minutes, both outdoor air dampers close for 1 hour and the controller sets a Level 3 alarm stating that minimum ventilation was interrupted.",
                 {"alarm": "Stage 2: when supply air temperature stays below {T:fz2} for 5 minutes, both outdoor air dampers close for 1 hour."}),
            Para("3.4.3", "Upon a signal from the freeze-stat, or if the supply air temperature drops below {T:fz2} for 15 minutes or below {T:fz3} for 5 minutes, the supply and return fans shall shut down, the outdoor air dampers shall close, the cooling coil valve shall open to 100 percent, the chilled water pumps shall be energized, and a Level 2 alarm shall be set indicating the unit is shut down by freeze protection.",
                 "Stage 3: on a freeze-stat trip, or when supply air temperature is below {T:fz2} for 15 minutes or below {T:fz3} for 5 minutes, the supply and return fans stop, the outdoor air dampers close, the cooling coil valve opens fully, the chilled water pumps are energized and a Level 2 alarm reports a freeze protection shutdown.",
                 {"interlock": "Stage 3: when supply air temperature is below {T:fz2} for 15 minutes or below {T:fz3} for 5 minutes, the supply and return fans stop, the outdoor air dampers close, the cooling coil valve opens fully, the chilled water pumps are energized and a Level 2 alarm reports a freeze protection shutdown.",
                  "contra": "Stage 3: on a freeze-stat trip, or when supply air temperature is below {T:fz2} for 15 minutes or below {T:fz3} for 5 minutes, the supply and return fans stop, the outdoor air dampers close, the cooling coil valve closes, the chilled water pumps are energized and a Level 2 alarm reports a freeze protection shutdown.",
                  "alarm": "Stage 3: on a freeze-stat trip, or when supply air temperature is below {T:fz2} for 15 minutes or below {T:fz3} for 5 minutes, the supply and return fans stop, the outdoor air dampers close, the cooling coil valve opens fully, the chilled water pumps are energized and a Level 4 alarm reports a freeze protection shutdown."}),
            Para("3.4.4", "A freeze protection shutdown shall be cleared only by a manual reset at the operator workstation.",
                 "Restart after a freeze protection shutdown requires a manual reset at the operator workstation.",
                 {"interlock": "After a freeze protection shutdown the unit restarts automatically once supply air temperature recovers."}),
        ]),
        Section("3.5", "Safeties and Interlocks", [
            Para("3.5.1", "The freeze-stat shall be hardwired to stop the supply and return fans regardless of the BAS command, and its status shall be monitored by the BAS.",
                 "The freeze-stat is hardwired in the fan starter circuits and stops the supply and return fans independent of the BAS; the BAS monitors its status.",
                 {"interlock": "The BAS monitors the freeze-stat and stops the supply and return fans through their start/stop commands when it trips."}),
            Para("3.5.2", "Duct smoke detectors in the supply and return air ducts shall be hardwired to stop both fans and close the outdoor air dampers, and the BAS shall set a Level 1 alarm on detection.",
                 "The supply and return duct smoke detectors are hardwired to stop both fans and close the outdoor air dampers; the BAS sets a Level 1 alarm on detection.",
                 {"interlock": "The supply duct smoke detector is hardwired to stop both fans and close the outdoor air dampers; the BAS sets a Level 1 alarm on detection.",
                  "alarm": "The supply and return duct smoke detectors are hardwired to stop both fans and close the outdoor air dampers; the BAS sets a Level 3 alarm on detection."}),
            Para("3.5.3", "A high static pressure safety switch set at {P:hs} shall stop the supply fan, and the fan shall restart only after a manual reset.",
                 "The high static pressure safety switch, set at {P:hs}, stops the supply fan, which then needs a manual reset to restart.",
                 {"setpt": "The high static pressure safety switch, set at {P:hs_bad}, stops the supply fan, which then needs a manual reset to restart.",
                  "interlock": "The high static pressure safety switch, set at {P:hs}, stops the supply fan, which restarts automatically when the pressure falls."}),
            Para("3.5.4", "The supply fan shall not start until the minimum outdoor air damper end switch proves the damper open.",
                 "The supply fan start is held off until the minimum outdoor air damper end switch proves the damper open.",
                 {"interlock": ABSENT}),
        ]),
    ]
    d1, d2 = f"DDC-AHU{n}-1", f"DDC-AHU{n}-2"
    P = [
        Point(f"{eq}-SF-C", "Supply fan start/stop", "BO", "bin", ("Off", "On"), f"VFD-{n}-SF", d1),
        Point(f"{eq}-SF-S", "Supply fan status", "BI", "bin", ("Off", "On"), f"VFD-{n}-SF", d1, Alarm(2, "mismatch", delay=15), bad_io="AI"),
        Point(f"{eq}-SF-SPD", "Supply fan speed command", "AO", "pct", (0, 100), f"VFD-{n}-SF", d1, bad_io="BO"),
        Point(f"{eq}-RF-C", "Return fan start/stop", "BO", "bin", ("Off", "On"), f"VFD-{n}-RF", d1),
        Point(f"{eq}-RF-S", "Return fan status", "BI", "bin", ("Off", "On"), f"VFD-{n}-RF", d1, Alarm(2, "mismatch", delay=15), bad_io="AI"),
        Point(f"{eq}-RF-SPD", "Return fan speed command", "AO", "pct", (0, 100), f"VFD-{n}-RF", d1, bad_io="BO"),
        Point(f"{eq}-DSP", "Duct static pressure", "AI", "press", (0, 5), f"DPT-{n}-1", d1, Alarm(3, "above", 2.0, 10), bad_io="BI"),
        Point(f"{eq}-SAT", "Supply air temperature", "AI", "temp", (30, 130), f"TT-{n}-SA", d1, Alarm(3, "dev", 5, 10)),
        Point(f"{eq}-MAT", "Mixed air temperature", "AI", "temp", (0, 130), f"TT-{n}-MA", d1),
        Point(f"{eq}-RAT", "Return air temperature", "AI", "temp", (30, 130), f"TT-{n}-RA", d1),
        Point(f"{eq}-OAT", "Outdoor air temperature", "AI", "temp", (-40, 130), f"TT-{n}-OA", d1),
        Point(f"{eq}-OAF", "Minimum outdoor airflow", "AI", "flow", (0, 10000), f"AFMS-{n}-1", d1, Alarm(3, "belowpct", 90, 15)),
        Point(f"{eq}-MOAD", "Minimum outdoor air damper command", "AO", "pct", (0, 100), f"DMP-{n}-MOA", d2, bad_io="BO"),
        Point(f"{eq}-EOAD", "Economizer outdoor air damper command", "AO", "pct", (0, 100), f"DMP-{n}-EOA", d2, bad_io="BO"),
        Point(f"{eq}-RAD", "Return air damper command", "AO", "pct", (0, 100), f"DMP-{n}-RA", d2),
        Point(f"{eq}-CHWV", "Chilled water valve command", "AO", "pct", (0, 100), f"VLV-{n}-CHW", d1, bad_io="BO"),
        Point(f"{eq}-HWV", "Heating hot water valve command", "AO", "pct", (0, 100), f"VLV-{n}-HW", d1, bad_io="BO"),
        Point(f"{eq}-FZ", "Freeze-stat status", "BI", "bin", ("Normal", "Alarm"), f"TS-{n}-FZ", d2, Alarm(2, "trip"), bad_io="AI"),
        Point(f"{eq}-SD-SA", "Supply duct smoke detector", "BI", "bin", ("Normal", "Alarm"), f"SD-{n}-SA", d2, Alarm(1, "trip")),
        Point(f"{eq}-SD-RA", "Return duct smoke detector", "BI", "bin", ("Normal", "Alarm"), f"SD-{n}-RA", d2, Alarm(1, "trip")),
        Point(f"{eq}-HSS", "High static safety switch", "BI", "bin", ("Normal", "Trip"), f"PS-{n}-HS", d2, Alarm(2, "trip")),
        Point(f"{eq}-FLT", "Filter differential pressure", "AI", "press", (0, 2), f"DPT-{n}-FLT", d1, Alarm(4, "above", p["flt"], 30), bad_io="BI"),
        Point(f"{eq}-MOAD-ES", "Minimum outdoor air damper end switch", "BI", "bin", ("Closed", "Open"), f"DMP-{n}-MOA", d2),
    ]
    extras = {"3.1.3": ("3.1.3a", "The static pressure setpoint, its limits and the trim and respond parameters are adjustable at the operator workstation."),
              "3.2.5": ("3.2.5a", "Mode changes come from the zone group mode selector for the zone groups served by {eq}."),
              "3.4.4": ("3.4.4a", "Each freeze protection stage change is recorded in the controller trend log.")}
    local = [Device(f"GA-{n}-FLT", "Filter differential pressure gauge, local", "-", "M-501", [], "none (local gauge, no BAS connection)"),
             Device(f"TI-{n}-MA", "Mixed air dial thermometer, local", "-", "M-501", [], "none (local indicator, no BAS connection)")]
    return _system("ahu_mz", eq, f"Multizone VAV Air Handling Unit {eq}", S, P, extras, local), p


# ---------------------------------------------------------------------------
# B: single zone VAV air handling unit (G36 5.18)
# ---------------------------------------------------------------------------
def ahu_single_zone(n: int, v: int) -> tuple[System, dict]:
    eq = f"RTU-{n}"
    p = dict(eq=eq, occ_h=(70, 68, 69)[v % 3], occ_c=(75, 74, 76)[v % 3], unocc_h=60, unocc_c=85, adj=2,
             fan_min=(30, 35, 25)[v % 3], fan_max=100, fan_hmax=(50, 60, 55)[v % 3], sat_dead=(70, 72, 68)[v % 3],
             sat_min=(55, 54, 56)[v % 3], sat_hmax=90, clo=(55, 50, 58)[v % 3], econ_hl=(75, 70, 65)[v % 3],
             econ_db=1, minpos_min=(25, 30, 20)[v % 3], minpos_max=(15, 18, 12)[v % 3])
    p.update(unocc_h_bad=50, adj_bad=6, fan_min_bad=p["fan_min"] - 20, fan_hmax_bad=100, sat_min_bad=48,
             sat_hmax_bad=120, clo_bad=p["clo"] - 25, econ_hl_bad=p["econ_hl"] + 12, minpos_min_bad=p["minpos_min"] - 15)
    S = [
        Section("3.1", "Zone Setpoints and Modes", [
            Para("3.1.1", "Occupied zone setpoints shall be {T:occ_h} heating and {T:occ_c} cooling; unoccupied setpoints shall be {T:unocc_h} heating and {T:unocc_c} cooling.",
                 "The zone is held between {T:occ_h} heating and {T:occ_c} cooling when occupied, and between {T:unocc_h} heating and {T:unocc_c} cooling when unoccupied.",
                 {"setpt": "The zone is held between {T:occ_h} heating and {T:occ_c} cooling when occupied, and between {T:unocc_h_bad} heating and {T:unocc_c} cooling when unoccupied."}),
            Para("3.1.2", "Occupant adjustment of the zone setpoints shall be limited to plus or minus {dT:adj}.",
                 "The occupant can offset the zone setpoints by no more than {dT:adj} up or down.",
                 {"setpt": "The occupant can offset the zone setpoints by no more than {dT:adj_bad} up or down."}),
            Para("3.1.3", "During unoccupied hours the unit shall run only in the Setback or Setup mode, as needed to hold the unoccupied setpoints.",
                 "Outside scheduled hours the unit runs only in Setback or Setup mode when needed to hold the unoccupied setpoints.",
                 {"contra": "Outside scheduled hours the unit runs continuously at minimum speed to hold the unoccupied setpoints."}),
        ]),
        Section("3.2", "Supply Fan Control", [
            Para("3.2.1", "The supply fan shall run continuously in the Occupied mode.",
                 "In the Occupied mode the supply fan runs continuously.",
                 {"contra": "In the Occupied mode the supply fan cycles on and off with the heating and cooling loops."}),
            Para("3.2.2", "In the deadband the supply fan shall run at its minimum speed of {fan_min} percent.",
                 "With both loops in deadband the supply fan runs at the {fan_min} percent minimum speed.",
                 {"setpt": "With both loops in deadband the supply fan runs at the {fan_min_bad} percent minimum speed."}),
            Para("3.2.3", "In cooling, supply fan speed shall rise from minimum to {fan_max} percent as the cooling loop goes from 50 to 100 percent.",
                 "As the cooling loop goes from 50 to 100 percent, supply fan speed rises from minimum to {fan_max} percent."),
            Para("3.2.4", "In heating, supply fan speed shall rise from minimum to {fan_hmax} percent as the heating loop goes from 50 to 100 percent.",
                 "As the heating loop goes from 50 to 100 percent, supply fan speed rises from minimum to {fan_hmax} percent.",
                 {"setpt": "As the heating loop goes from 50 to 100 percent, supply fan speed rises from minimum to {fan_hmax_bad} percent."}),
        ]),
        Section("3.3", "Supply Air Temperature Control", [
            Para("3.3.1", "In cooling, the supply air temperature setpoint shall be reset from {T:sat_dead} at 0 percent cooling loop down to {T:sat_min} at 50 percent cooling loop.",
                 "The cooling supply air temperature setpoint moves from {T:sat_dead} at 0 percent cooling loop down to {T:sat_min} at 50 percent cooling loop.",
                 {"setpt": "The cooling supply air temperature setpoint moves from {T:sat_dead} at 0 percent cooling loop down to {T:sat_min_bad} at 50 percent cooling loop.",
                  "contra": "The cooling supply air temperature setpoint moves from {T:sat_min} at 0 percent cooling loop up to {T:sat_dead} at 50 percent cooling loop."}),
            Para("3.3.2", "In heating, the supply air temperature setpoint shall be reset from {T:sat_dead} at 0 percent heating loop up to {T:sat_hmax} at 50 percent heating loop.",
                 "The heating supply air temperature setpoint moves from {T:sat_dead} at 0 percent heating loop up to {T:sat_hmax} at 50 percent heating loop.",
                 {"setpt": "The heating supply air temperature setpoint moves from {T:sat_dead} at 0 percent heating loop up to {T:sat_hmax_bad} at 50 percent heating loop."}),
            Para("3.3.3", "Mechanical cooling shall be enabled only when the outdoor air temperature is above {T:clo}.",
                 "The chilled water valve is allowed to open only when outdoor air is warmer than {T:clo}.",
                 {"setpt": "The chilled water valve is allowed to open only when outdoor air is warmer than {T:clo_bad}."}),
        ]),
        Section("3.4", "Economizer", [
            Para("3.4.1", "The economizer shall be disabled when the outdoor air temperature exceeds {T:econ_hl} and enabled again when it falls {dT:econ_db} below that limit.",
                 "The economizer is locked out above {T:econ_hl} outdoor air temperature and released when outdoor air drops {dT:econ_db} below that limit.",
                 {"setpt": "The economizer is locked out above {T:econ_hl_bad} outdoor air temperature and released when outdoor air drops {dT:econ_db} below that limit."}),
            Para("3.4.2", "The outdoor air damper shall be held at its minimum position whenever the unit is in heating.",
                 "In heating the outdoor air damper stays at its minimum position.",
                 {"contra": "In heating the outdoor air damper modulates above minimum to hold mixed air temperature at {T:sat_min}."}),
            Para("3.4.3", "The minimum outdoor air damper position shall be {minpos_min} percent at minimum fan speed and {minpos_max} percent at maximum fan speed, interpolated linearly between.",
                 "Minimum outdoor air damper position is interpolated linearly from {minpos_min} percent at minimum fan speed to {minpos_max} percent at maximum fan speed.",
                 {"setpt": "Minimum outdoor air damper position is interpolated linearly from {minpos_min_bad} percent at minimum fan speed to {minpos_max} percent at maximum fan speed."}),
        ]),
        Section("3.5", "Safeties and Interlocks", [
            Para("3.5.1", "The duct smoke detector shall be hardwired to stop the supply fan and close the outdoor air damper, and the BAS shall set a Level 1 alarm on detection.",
                 "The duct smoke detector is hardwired to stop the supply fan and close the outdoor air damper, and the BAS raises a Level 1 alarm on detection.",
                 {"alarm": "The duct smoke detector is hardwired to stop the supply fan and close the outdoor air damper."}),
            Para("3.5.2", "The freeze-stat shall be hardwired to stop the supply fan and shall require a manual reset.",
                 "The freeze-stat is hardwired to stop the supply fan and must be reset by hand.",
                 {"interlock": "The freeze-stat is hardwired to stop the supply fan and resets automatically when the coil warms up."}),
            Para("3.5.3", "A condensate overflow switch shall close the chilled water valve and set a Level 3 alarm.",
                 "On a condensate overflow switch trip the chilled water valve closes and a Level 3 alarm is set.",
                 {"interlock": ABSENT, "alarm": "On a condensate overflow switch trip the chilled water valve closes and a Level 4 alarm is set."}),
            Para("3.5.4", "Heating and cooling shall be disabled until the supply fan is proven on.",
                 "The heating and chilled water valves stay closed until the supply fan is proven on.",
                 {"interlock": ABSENT}),
        ]),
    ]
    d1 = f"DDC-RTU{n}-1"
    P = [
        Point(f"{eq}-SF-C", "Supply fan start/stop", "BO", "bin", ("Off", "On"), f"VFD-{n}-SF", d1),
        Point(f"{eq}-SF-S", "Supply fan status", "BI", "bin", ("Off", "On"), f"VFD-{n}-SF", d1, Alarm(2, "mismatch", delay=15), bad_io="AI"),
        Point(f"{eq}-SF-SPD", "Supply fan speed command", "AO", "pct", (0, 100), f"VFD-{n}-SF", d1, bad_io="BO"),
        Point(f"{eq}-ZT", "Zone temperature", "AI", "temp", (40, 100), f"TS-{n}-Z", d1, Alarm(3, "dev", 4, 60)),
        Point(f"{eq}-SAT", "Supply air temperature", "AI", "temp", (30, 130), f"TT-{n}-SA", d1, Alarm(3, "dev", 5, 10)),
        Point(f"{eq}-MAT", "Mixed air temperature", "AI", "temp", (0, 130), f"TT-{n}-MA", d1),
        Point(f"{eq}-OAT", "Outdoor air temperature", "AI", "temp", (-40, 130), f"TT-{n}-OA", d1),
        Point(f"{eq}-OAD", "Outdoor air damper command", "AO", "pct", (0, 100), f"DMP-{n}-OA", d1, bad_io="BO"),
        Point(f"{eq}-CHWV", "Chilled water valve command", "AO", "pct", (0, 100), f"VLV-{n}-CHW", d1, bad_io="BO"),
        Point(f"{eq}-HWV", "Heating hot water valve command", "AO", "pct", (0, 100), f"VLV-{n}-HW", d1, bad_io="BO"),
        Point(f"{eq}-FZ", "Freeze-stat status", "BI", "bin", ("Normal", "Alarm"), f"TS-{n}-FZ", d1, Alarm(2, "trip"), bad_io="AI"),
        Point(f"{eq}-SD", "Duct smoke detector", "BI", "bin", ("Normal", "Alarm"), f"SD-{n}-SA", d1, Alarm(1, "trip")),
        Point(f"{eq}-COS", "Condensate overflow switch", "BI", "bin", ("Normal", "Alarm"), f"LS-{n}-CO", d1, Alarm(3, "trip")),
        Point(f"{eq}-FLT", "Filter differential pressure", "AI", "press", (0, 2), f"DPT-{n}-FLT", d1, Alarm(4, "above", 1.0, 30), bad_io="BI"),
    ]
    extras = {"3.2.4": ("3.2.4a", "Fan speed limits are adjustable at the operator workstation."),
              "3.3.2": ("3.3.2a", "The supply air temperature loops use the zone heating and cooling loop outputs calculated by the zone controller.")}
    local = [Device(f"TI-{n}-SA", "Supply air dial thermometer, local", "-", "M-502", [], "none (local indicator, no BAS connection)")]
    return _system("ahu_sz", eq, f"Single Zone VAV Air Handling Unit {eq}", S, P, extras, local), p


# ---------------------------------------------------------------------------
# C: VAV terminal units with hot water reheat (G36 5.6), many boxes
# ---------------------------------------------------------------------------
def vav_reheat(n: int, v: int, boxes: int) -> tuple[System, dict]:
    eq = f"VAV-{n}"
    p = dict(eq=eq, ahu=f"AHU-{n}", occ_h=(70, 69, 71)[v % 3], occ_c=(74, 75, 76)[v % 3], unocc_h=60, unocc_c=85,
             adj=2, dat_rise=20, dat_lo=15)
    p.update(adj_bad=5, dat_rise_bad=40, occ_c_bad=p["occ_c"] + 6)
    air = []
    for j in range(1, boxes + 1):
        cmax = 300 + ((j * 137 + v * 61) % 9) * 100
        mn = int(round(cmax * 0.3, -1))
        hmax = int(round(cmax * 0.5, -1))
        key = f"{n}{j:02d}"
        p[f"cmax_{key}"], p[f"min_{key}"], p[f"hmax_{key}"] = cmax, mn, hmax
        p[f"min_{key}_bad"] = int(round(mn * 0.4, -1))
        p[f"cmax_{key}_bad"] = cmax + 400
        air.append(Para(f"3.2.{j + 1}", f"Terminal VAV-{key} shall have a maximum cooling airflow of {{F:cmax_{key}}}, a minimum airflow of {{F:min_{key}}} and a maximum heating airflow of {{F:hmax_{key}}}.",
                        f"VAV-{key} is scheduled for {{F:cmax_{key}}} cooling maximum, {{F:min_{key}}} minimum and {{F:hmax_{key}}} heating maximum.",
                        {"setpt": f"VAV-{key} is scheduled for {{F:cmax_{key}}} cooling maximum, {{F:min_{key}_bad}} minimum and {{F:hmax_{key}}} heating maximum."}))
    S = [
        Section("3.1", "Zone Temperature Setpoints", [
            Para("3.1.1", "Occupied zone setpoints shall be {T:occ_h} heating and {T:occ_c} cooling; unoccupied setpoints shall be {T:unocc_h} heating and {T:unocc_c} cooling.",
                 "Each zone holds {T:occ_h} heating and {T:occ_c} cooling when occupied and {T:unocc_h} heating and {T:unocc_c} cooling when unoccupied.",
                 {"setpt": "Each zone holds {T:occ_h} heating and {T:occ_c_bad} cooling when occupied and {T:unocc_h} heating and {T:unocc_c} cooling when unoccupied."}),
            Para("3.1.2", "Occupant adjustment of the zone setpoints shall be limited to plus or minus {dT:adj}.",
                 "Occupants may adjust the zone setpoints by at most {dT:adj} in either direction.",
                 {"setpt": "Occupants may adjust the zone setpoints by at most {dT:adj_bad} in either direction."}),
        ]),
        Section("3.2", "Terminal Airflow Setpoints", [
            Para("3.2.1", "Each terminal shall control discharge airflow between its scheduled minimum airflow and the active maximum airflow listed below.",
                 "Each terminal controls its discharge airflow between the scheduled minimum and the active maximum listed below."),
        ] + air),
        Section("3.3", "Damper and Valve Control", [
            Para("3.3.1", "In cooling, the airflow setpoint shall be reset from the minimum airflow up to the maximum cooling airflow as the cooling loop rises from 0 to 100 percent.",
                 "As the cooling loop rises from 0 to 100 percent, the airflow setpoint rises from the minimum to the maximum cooling airflow.",
                 {"contra": "As the cooling loop rises from 0 to 100 percent, the airflow setpoint falls from the maximum cooling airflow to the minimum."}),
            Para("3.3.2", "In heating, the discharge air temperature setpoint shall be reset from the zone temperature up to {dT:dat_rise} above the zone temperature as the heating loop rises from 0 to 50 percent, and the airflow setpoint shall rise to the maximum heating airflow as the heating loop rises from 50 to 100 percent.",
                 "From 0 to 50 percent heating loop the discharge air temperature setpoint rises from zone temperature to {dT:dat_rise} above it, and from 50 to 100 percent heating loop the airflow setpoint rises to the maximum heating airflow.",
                 {"setpt": "From 0 to 50 percent heating loop the discharge air temperature setpoint rises from zone temperature to {dT:dat_rise_bad} above it, and from 50 to 100 percent heating loop the airflow setpoint rises to the maximum heating airflow."}),
            Para("3.3.3", "The hot water valve shall be closed whenever the zone is in cooling or in the deadband.",
                 "In cooling and in the deadband the hot water valve is closed.",
                 {"contra": "In the deadband the hot water valve modulates to keep the discharge air temperature at the zone temperature."}),
            Para("3.3.4", "On loss of communication with the AHU controller, each terminal shall control to its minimum airflow setpoint.",
                 "If communication with the AHU controller is lost, each terminal controls to its minimum airflow setpoint.",
                 {"contra": "If communication with the AHU controller is lost, each terminal closes its damper fully."}),
        ]),
        Section("3.4", "Terminal Alarms", [
            Para("3.4.1", "If the measured airflow is below 70 percent of setpoint for 5 minutes while the setpoint is above zero, a Level 3 low airflow alarm shall be set; if it is below 50 percent of setpoint for 5 minutes, a Level 2 alarm shall be set.",
                 "With a setpoint above zero, airflow under 70 percent of setpoint for 5 minutes sets a Level 3 low airflow alarm, and airflow under 50 percent of setpoint for 5 minutes sets a Level 2 alarm.",
                 {"alarm": "With a setpoint above zero, airflow under 70 percent of setpoint for 5 minutes sets a Level 3 low airflow alarm."}),
            Para("3.4.2", "If heating hot water is available and the discharge air temperature is {dT:dat_lo} below its setpoint for 10 minutes, a Level 3 low discharge temperature alarm shall be set.",
                 "When heating hot water is available, a discharge air temperature {dT:dat_lo} under its setpoint for 10 minutes sets a Level 3 low discharge temperature alarm.",
                 {"alarm": "When heating hot water is available, a discharge air temperature {dT:dat_lo} under its setpoint for 60 minutes sets a Level 3 low discharge temperature alarm."}),
            Para("3.4.3", "If the damper is commanded closed and the measured airflow stays above 10 percent of the maximum cooling airflow for 10 minutes, a Level 4 leaking damper alarm shall be set.",
                 "A damper commanded closed with measured airflow above 10 percent of the maximum cooling airflow for 10 minutes sets a Level 4 leaking damper alarm.",
                 {"alarm": ABSENT}),
        ]),
        Section("3.5", "Interlocks", [
            Para("3.5.1", "The hot water valve shall be closed and heating disabled whenever the {ahu} supply fan is not proven on.",
                 "Whenever the {ahu} supply fan is not proven on, heating is disabled and the hot water valve is closed.",
                 {"interlock": ABSENT}),
        ]),
    ]
    P, D = [], []
    for j in range(1, boxes + 1):
        key = f"{n}{j:02d}"
        b, ddc = f"VAV-{key}", f"DDC-VAV{key}"
        P += [Point(f"{b}-ZT", "Zone temperature", "AI", "temp", (40, 100), f"TS-{key}", ddc),
              Point(f"{b}-FLOW", "Discharge airflow", "AI", "flow", (0, p[f"cmax_{key}"] + 300), f"FS-{key}", ddc, Alarm(3, "belowpct", 70, 5)),
              Point(f"{b}-DMP", "Damper command", "AO", "pct", (0, 100), f"DA-{key}", ddc, bad_io="BO"),
              Point(f"{b}-HWV", "Hot water valve command", "AO", "pct", (0, 100), f"VLV-{key}", ddc, bad_io="BO"),
              Point(f"{b}-DAT", "Discharge air temperature", "AI", "temp", (40, 140), f"TT-{key}-DA", ddc, Alarm(3, "below", 55, 10), bad_io="BI")]
    extras = {"3.1.2": ("3.1.2a", "Zone setpoints and the adjustment limit are adjustable at the operator workstation."),
              "3.3.4": ("3.3.4a", "Each terminal controller reports its cooling and pressure reset requests to {ahu} over the BACnet MS/TP trunk.")}
    local = [Device(f"BD-{n}01", "Manual balancing damper, branch duct", "-", "M-601", [], "none (manual device, no BAS connection)")]
    return _system("vav_rh", eq, f"VAV Terminal Units with Hot Water Reheat on {p['ahu']}", S, P, extras, local), p


# ---------------------------------------------------------------------------
# D: fan coil unit (G36 5.22)
# ---------------------------------------------------------------------------
def fan_coil(n: int, v: int) -> tuple[System, dict]:
    eq = f"FCU-{n}"
    p = dict(eq=eq, occ_h=(70, 68, 71)[v % 3], occ_c=(75, 76, 74)[v % 3], unocc_h=60, unocc_c=85,
             fan_min=(20, 30, 25)[v % 3], sat_dead=(72, 70, 71)[v % 3], sat_min=(55, 56, 54)[v % 3],
             sat_hmax=(95, 100, 90)[v % 3])
    p.update(fan_min_bad=p["fan_min"] - 15, sat_min_bad=45, sat_hmax_bad=130, unocc_c_bad=95)
    S = [
        Section("3.1", "Fan Control", [
            Para("3.1.1", "The fan shall run continuously in the Occupied mode and shall cycle with demand in the Setback and Setup modes.",
                 "The fan runs all the time in the Occupied mode and cycles with heating or cooling demand in Setback and Setup.",
                 {"contra": "The fan cycles with heating or cooling demand in all modes, including Occupied."}),
            Para("3.1.2", "The fan shall run at its minimum speed of {fan_min} percent in the deadband and rise to 100 percent as either loop rises from 50 to 100 percent.",
                 "In deadband the fan runs at {fan_min} percent, ramping to 100 percent as the heating or cooling loop goes from 50 to 100 percent.",
                 {"setpt": "In deadband the fan runs at {fan_min_bad} percent, ramping to 100 percent as the heating or cooling loop goes from 50 to 100 percent."}),
        ]),
        Section("3.2", "Supply Air Temperature Control", [
            Para("3.2.1", "In cooling, the supply air temperature setpoint shall be reset from {T:sat_dead} at 0 percent cooling loop down to {T:sat_min} at 50 percent cooling loop.",
                 "Cooling resets the supply air temperature setpoint from {T:sat_dead} at 0 percent loop down to {T:sat_min} at 50 percent loop.",
                 {"setpt": "Cooling resets the supply air temperature setpoint from {T:sat_dead} at 0 percent loop down to {T:sat_min_bad} at 50 percent loop."}),
            Para("3.2.2", "In heating, the supply air temperature setpoint shall be reset from {T:sat_dead} at 0 percent heating loop up to {T:sat_hmax} at 50 percent heating loop.",
                 "Heating resets the supply air temperature setpoint from {T:sat_dead} at 0 percent loop up to {T:sat_hmax} at 50 percent loop.",
                 {"setpt": "Heating resets the supply air temperature setpoint from {T:sat_dead} at 0 percent loop up to {T:sat_hmax_bad} at 50 percent loop."}),
            Para("3.2.3", "The heating valve and the cooling valve shall never be open at the same time.",
                 "The controller never opens the heating and cooling valves at the same time.",
                 {"contra": "The heating valve may stay open at minimum position while the cooling valve modulates, to limit overcooling."}),
        ]),
        Section("3.3", "Zone Setpoints", [
            Para("3.3.1", "Occupied zone setpoints shall be {T:occ_h} heating and {T:occ_c} cooling; unoccupied setpoints shall be {T:unocc_h} heating and {T:unocc_c} cooling.",
                 "Occupied setpoints are {T:occ_h} heating and {T:occ_c} cooling, and unoccupied setpoints are {T:unocc_h} heating and {T:unocc_c} cooling.",
                 {"setpt": "Occupied setpoints are {T:occ_h} heating and {T:occ_c} cooling, and unoccupied setpoints are {T:unocc_h} heating and {T:unocc_c_bad} cooling."}),
        ]),
        Section("3.4", "Alarms and Interlocks", [
            Para("3.4.1", "A condensate overflow switch shall be hardwired to close the cooling valve, and the BAS shall set a Level 3 alarm when it trips.",
                 "The condensate overflow switch is hardwired to close the cooling valve and the BAS sets a Level 3 alarm on a trip.",
                 {"interlock": "The BAS closes the cooling valve through its command when the condensate overflow switch trips and sets a Level 3 alarm.",
                  "alarm": "The condensate overflow switch is hardwired to close the cooling valve."}),
            Para("3.4.2", "If the fan status does not match its command for 15 seconds, a Level 2 fan failure alarm shall be set and both valves shall close.",
                 "A fan status that disagrees with the command for 15 seconds sets a Level 2 fan failure alarm and closes both valves.",
                 {"alarm": "A fan status that disagrees with the command for 15 seconds closes both valves."}),
            Para("3.4.3", "The heating valve shall not open until the fan is proven on.",
                 "The heating valve stays closed until the fan is proven on.",
                 {"interlock": ABSENT}),
        ]),
    ]
    d1 = f"DDC-FCU{n}"
    P = [
        Point(f"{eq}-FAN-C", "Fan start/stop", "BO", "bin", ("Off", "On"), f"M-{n}-FAN", d1),
        Point(f"{eq}-FAN-S", "Fan status", "BI", "bin", ("Off", "On"), f"CS-{n}-FAN", d1, Alarm(2, "mismatch", delay=15), bad_io="AI"),
        Point(f"{eq}-FAN-SPD", "Fan speed command", "AO", "pct", (0, 100), f"M-{n}-FAN", d1, bad_io="BO"),
        Point(f"{eq}-ZT", "Zone temperature", "AI", "temp", (40, 100), f"TS-{n}-Z", d1),
        Point(f"{eq}-SAT", "Supply air temperature", "AI", "temp", (30, 130), f"TT-{n}-SA", d1, Alarm(3, "dev", 5, 15)),
        Point(f"{eq}-CHWV", "Cooling valve command", "AO", "pct", (0, 100), f"VLV-{n}-CHW", d1, bad_io="BO"),
        Point(f"{eq}-HWV", "Heating valve command", "AO", "pct", (0, 100), f"VLV-{n}-HW", d1, bad_io="BO"),
        Point(f"{eq}-COS", "Condensate overflow switch", "BI", "bin", ("Normal", "Alarm"), f"LS-{n}-CO", d1, Alarm(3, "trip"), bad_io="AI"),
    ]
    extras = {"3.2.3": ("3.2.3a", "The supply air temperature control loops are disabled while the fan is off.")}
    local = [Device(f"BV-{n}-CHW", "Chilled water balancing valve, manual", "-", "M-701", [], "none (manual valve, no BAS connection)")]
    return _system("fcu", eq, f"Fan Coil Unit {eq}", S, P, extras, local), p


# ---------------------------------------------------------------------------
# E: chilled water plant
# ---------------------------------------------------------------------------
def chilled_water_plant(n: int, v: int, chillers: int) -> tuple[System, dict]:
    eq = f"CHWP-{n}"
    p = dict(eq=eq, req=(2, 3, 2)[v % 3], lock=(55, 50, 60)[v % 3], lock_db=2, stg_up=2, stg_pct=(90, 85, 80)[v % 3],
             stg_dn=(40, 45, 35)[v % 3], dp_min=(5, 6, 4)[v % 3], dp_max=(15, 18, 20)[v % 3],
             minflow=(240, 300, 180)[v % 3], chw_min=(44, 42, 45)[v % 3], chw_max=(54, 56, 52)[v % 3],
             cws=(85, 80, 83)[v % 3], cw_min=(70, 65, 68)[v % 3], ppm=(25, 30, 20)[v % 3])
    p.update(lock_bad=p["lock"] - 25, stg_pct_bad=55, dp_max_bad=p["dp_max"] + 20, minflow_bad=int(p["minflow"] * 0.3),
             chw_max_bad=p["chw_max"] + 12, cws_bad=p["cws"] + 12, ppm_bad=p["ppm"] * 8, chw_min_bad=36)
    S = [
        Section("3.1", "Plant Enable", [
            Para("3.1.1", "The plant shall be enabled when there are {req} or more chiller plant requests for 5 minutes and the outdoor air temperature is above the {T:lock} lockout.",
                 "The plant enables after 5 minutes with at least {req} chiller plant requests, provided outdoor air is warmer than the {T:lock} lockout.",
                 {"setpt": "The plant enables after 5 minutes with at least {req} chiller plant requests, provided outdoor air is warmer than the {T:lock_bad} lockout."}),
            Para("3.1.2", "The plant shall be disabled when there are fewer than {req} requests for 3 minutes or when the outdoor air temperature falls {dT:lock_db} below the lockout.",
                 "The plant disables after 3 minutes with fewer than {req} requests, or once outdoor air is {dT:lock_db} below the lockout.",
                 {"contra": "The plant stays enabled until an operator disables it, regardless of requests or outdoor air temperature."}),
        ]),
        Section("3.2", "Chiller Staging", [
            Para("3.2.1", "Before a chiller is enabled, its chilled water and condenser water isolation valves shall be open and flow shall be proven through its evaporator and condenser.",
                 "A chiller is enabled only after its chilled water and condenser water isolation valves are open and evaporator and condenser flow are proven.",
                 {"interlock": "A chiller is enabled after its chilled water and condenser water isolation valves are commanded open."}),
            Para("3.2.2", "The next chiller shall be staged on when the chilled water supply temperature is {dT:stg_up} above setpoint for 10 minutes and the operating chillers are above {stg_pct} percent load.",
                 "A chiller stages on when chilled water supply temperature is {dT:stg_up} above setpoint for 10 minutes with the running chillers above {stg_pct} percent load.",
                 {"setpt": "A chiller stages on when chilled water supply temperature is {dT:stg_up} above setpoint for 10 minutes with the running chillers above {stg_pct_bad} percent load."}),
            Para("3.2.3", "A chiller shall be staged off when the operating chillers are below {stg_dn} percent load for 15 minutes.",
                 "A chiller stages off after the running chillers are under {stg_dn} percent load for 15 minutes.",
                 {"contra": "A chiller stages off as soon as chilled water supply temperature reaches setpoint."}),
        ]),
        Section("3.3", "Chilled Water Pumping", [
            Para("3.3.1", "The lead chilled water pump shall run whenever the plant is enabled.",
                 "The lead chilled water pump runs whenever the plant is enabled.",
                 {"contra": "The lead chilled water pump runs only while a chiller is running."}),
            Para("3.3.2", "Pump speed shall be modulated to maintain the remote differential pressure at setpoint, reset between {D:dp_min} and {D:dp_max} by trim and respond logic.",
                 "Pump speed modulates to hold remote differential pressure at a setpoint that trim and respond logic resets between {D:dp_min} and {D:dp_max}.",
                 {"setpt": "Pump speed modulates to hold remote differential pressure at a setpoint that trim and respond logic resets between {D:dp_min} and {D:dp_max_bad}.",
                  "contra": "Pump speed modulates to hold pump discharge pressure at a fixed {D:dp_max}."}),
            Para("3.3.3", "The minimum flow bypass valve shall modulate to keep chilled water flow through each operating chiller above {W:minflow}.",
                 "The minimum flow bypass valve modulates to keep chilled water flow through each running chiller above {W:minflow}.",
                 {"setpt": "The minimum flow bypass valve modulates to keep chilled water flow through each running chiller above {W:minflow_bad}."}),
        ]),
        Section("3.4", "Chilled Water Supply Temperature Reset", [
            Para("3.4.1", "The chilled water supply temperature setpoint shall be reset between {T:chw_min} and {T:chw_max} by trim and respond logic driven by cooling coil requests.",
                 "Trim and respond logic driven by cooling coil requests resets the chilled water supply temperature setpoint between {T:chw_min} and {T:chw_max}.",
                 {"setpt": "Trim and respond logic driven by cooling coil requests resets the chilled water supply temperature setpoint between {T:chw_min} and {T:chw_max_bad}."}),
            Para("3.4.2", "On plant enable the chilled water supply temperature setpoint shall start at {T:chw_min}.",
                 "When the plant enables, the chilled water supply temperature setpoint starts at {T:chw_min}.",
                 {"contra": "When the plant enables, the chilled water supply temperature setpoint starts at {T:chw_max}."}),
        ]),
        Section("3.5", "Condenser Water and Cooling Tower", [
            Para("3.5.1", "Cooling tower fan speed shall be modulated to maintain the condenser water supply temperature at {T:cws}.",
                 "Tower fan speed modulates to hold condenser water supply temperature at {T:cws}.",
                 {"setpt": "Tower fan speed modulates to hold condenser water supply temperature at {T:cws_bad}."}),
            Para("3.5.2", "The tower fans shall stop and the tower bypass valve shall modulate open when the condenser water supply temperature falls below {T:cw_min}.",
                 "Below {T:cw_min} condenser water supply temperature the tower fans stop and the tower bypass valve modulates open.",
                 {"contra": "Below {T:cw_min} condenser water supply temperature the tower fans run at minimum speed and the tower bypass valve stays closed."}),
        ]),
        Section("3.6", "Safeties and Interlocks", [
            Para("3.6.1", "Each chiller shall be hardwired to its chilled water and condenser water flow switches so that it cannot run without proven flow.",
                 "The chilled water and condenser water flow switches are hardwired into each chiller control circuit so the chiller cannot run without proven flow.",
                 {"interlock": "The BAS reads the chilled water and condenser water flow switches and disables a chiller in software when flow is lost."}),
            Para("3.6.2", "When the refrigerant monitor exceeds {ppm} ppm, the machine room exhaust fans shall start and a Level 1 alarm shall be set.",
                 "A refrigerant monitor reading above {ppm} ppm starts the machine room exhaust fans and sets a Level 1 alarm.",
                 {"setpt": "A refrigerant monitor reading above {ppm_bad} ppm starts the machine room exhaust fans and sets a Level 1 alarm.",
                  "alarm": "A refrigerant monitor reading above {ppm} ppm starts the machine room exhaust fans and sets a Level 3 alarm."}),
            Para("3.6.3", "The emergency stop switch at the machine room exit shall be hardwired to stop all chillers.",
                 "The emergency stop switch at the machine room exit is hardwired to stop every chiller.",
                 {"interlock": ABSENT}),
        ]),
    ]
    d1, d2 = f"DDC-CHWP{n}-1", f"DDC-CHWP{n}-2"
    P = [Point(f"{eq}-CHWST", "Chilled water supply temperature", "AI", "temp", (30, 80), f"TT-{n}-CHWS", d1, Alarm(3, "dev", 5, 15)),
         Point(f"{eq}-CHWRT", "Chilled water return temperature", "AI", "temp", (30, 80), f"TT-{n}-CHWR", d1),
         Point(f"{eq}-CHW-DP", "Remote chilled water differential pressure", "AI", "wdp", (0, 50), f"DPT-{n}-CHW", d1, Alarm(3, "below", p["dp_min"] - 2, 10), bad_io="BI"),
         Point(f"{eq}-CHW-FLOW", "Chilled water flow", "AI", "wflow", (0, 2000), f"FM-{n}-CHW", d1),
         Point(f"{eq}-BYPV", "Minimum flow bypass valve command", "AO", "pct", (0, 100), f"VLV-{n}-BYP", d1, bad_io="BO"),
         Point(f"{eq}-CWST", "Condenser water supply temperature", "AI", "temp", (40, 110), f"TT-{n}-CWS", d2),
         Point(f"{eq}-CWRT", "Condenser water return temperature", "AI", "temp", (40, 110), f"TT-{n}-CWR", d2),
         Point(f"{eq}-CT-SPD", "Cooling tower fan speed command", "AO", "pct", (0, 100), f"VFD-{n}-CT", d2, bad_io="BO"),
         Point(f"{eq}-CT-S", "Cooling tower fan status", "BI", "bin", ("Off", "On"), f"VFD-{n}-CT", d2, Alarm(2, "mismatch", delay=30), bad_io="AI"),
         Point(f"{eq}-RM", "Refrigerant monitor concentration", "AI", "ppm", (0, 1000), f"RM-{n}-1", d2, Alarm(1, "above", p["ppm"], 1), bad_io="BI"),
         Point(f"{eq}-ESTOP", "Machine room emergency stop status", "BI", "bin", ("Normal", "Stop"), f"ES-{n}-1", d2, Alarm(1, "trip"))]
    for k in range(1, chillers + 1):
        P += [Point(f"{eq}-CH{k}-EN", f"Chiller {k} enable", "BO", "bin", ("Off", "On"), f"CH-{n}{k}", d1),
              Point(f"{eq}-CH{k}-S", f"Chiller {k} status", "BI", "bin", ("Off", "On"), f"CH-{n}{k}", d1, Alarm(2, "mismatch", delay=300), bad_io="AI"),
              Point(f"{eq}-CH{k}-ALM", f"Chiller {k} common alarm", "BI", "bin", ("Normal", "Alarm"), f"CH-{n}{k}", d1, Alarm(2, "trip")),
              Point(f"{eq}-CHWP{k}-SPD", f"Chilled water pump {k} speed command", "AO", "pct", (0, 100), f"VFD-{n}-P{k}", d1, bad_io="BO"),
              Point(f"{eq}-CHWP{k}-S", f"Chilled water pump {k} status", "BI", "bin", ("Off", "On"), f"VFD-{n}-P{k}", d1, Alarm(2, "mismatch", delay=15)),
              Point(f"{eq}-CHW-FS{k}", f"Chiller {k} evaporator flow switch", "BI", "bin", ("No flow", "Flow"), f"FS-{n}-E{k}", d2, bad_io="AI")]
    extras = {"3.2.3": ("3.2.3a", "Chiller lead and lag order rotates weekly at the operator workstation, adjustable."),
              "3.4.2": ("3.4.2a", "Requests from each cooling coil are counted only while its air handling unit supply fan is proven on.")}
    local = [Device(f"PG-{n}-CHWS", "Chilled water supply pressure gauge, local", "-", "M-801", [], "none (local gauge, no BAS connection)"),
             Device(f"TI-{n}-CHWS", "Chilled water supply thermometer, local", "-", "M-801", [], "none (local indicator, no BAS connection)")]
    return _system("chw_plant", eq, f"Chilled Water Plant {eq}", S, P, extras, local), p


# ---------------------------------------------------------------------------
# F: hot water boiler plant
# ---------------------------------------------------------------------------
def boiler_plant(n: int, v: int, boilers: int) -> tuple[System, dict]:
    eq = f"HWP-{n}"
    p = dict(eq=eq, req=(2, 1, 2)[v % 3], hw_lock=(65, 60, 70)[v % 3], hw_max=(180, 160, 140)[v % 3],
             hw_min=(140, 120, 110)[v % 3], oa_lo=(20, 10, 15)[v % 3], oa_hi=(60, 65, 55)[v % 3], stg=10,
             fire_min=(20, 25, 30)[v % 3], dp_min=(4, 5, 3)[v % 3], dp_max=(12, 15, 10)[v % 3], hlim=(200, 190, 180)[v % 3])
    p.update(hw_lock_bad=p["hw_lock"] + 20, hw_max_bad=p["hw_max"] + 30, dp_max_bad=p["dp_max"] + 20, hlim_bad=p["hlim"] + 40,
             hw_min_bad=p["hw_min"] - 30)
    S = [
        Section("3.1", "Plant Enable", [
            Para("3.1.1", "The plant shall be enabled when there are {req} or more heating hot water plant requests for 5 minutes and the outdoor air temperature is below the {T:hw_lock} lockout.",
                 "The plant enables after 5 minutes with {req} or more heating hot water plant requests while outdoor air is colder than the {T:hw_lock} lockout.",
                 {"setpt": "The plant enables after 5 minutes with {req} or more heating hot water plant requests while outdoor air is colder than the {T:hw_lock_bad} lockout."}),
        ]),
        Section("3.2", "Hot Water Supply Temperature Reset", [
            Para("3.2.1", "The hot water supply temperature setpoint shall be reset from {T:hw_max} at an outdoor air temperature of {T:oa_lo} and below to {T:hw_min} at {T:oa_hi} and above.",
                 "The hot water supply temperature setpoint is {T:hw_max} with outdoor air at {T:oa_lo} or colder and resets linearly to {T:hw_min} with outdoor air at {T:oa_hi} or warmer.",
                 {"setpt": "The hot water supply temperature setpoint is {T:hw_max_bad} with outdoor air at {T:oa_lo} or colder and resets linearly to {T:hw_min} with outdoor air at {T:oa_hi} or warmer.",
                  "contra": "The hot water supply temperature setpoint is {T:hw_min} with outdoor air at {T:oa_lo} or colder and resets linearly to {T:hw_max} with outdoor air at {T:oa_hi} or warmer."}),
            Para("3.2.2", "The setpoint shall never be lower than {T:hw_min}.",
                 "The setpoint is limited to no lower than {T:hw_min}.",
                 {"setpt": "The setpoint is limited to no lower than {T:hw_min_bad}."}),
        ]),
        Section("3.3", "Boiler Staging", [
            Para("3.3.1", "The lead boiler shall be enabled only after the lead hot water pump is proven on and boiler flow is proven.",
                 "The lead boiler is enabled once the lead hot water pump is proven on and boiler flow is proven.",
                 {"interlock": "The lead boiler is enabled at the same time as the lead hot water pump is commanded on."}),
            Para("3.3.2", "The next boiler shall be staged on when the hot water supply temperature is {dT:stg} below setpoint for 10 minutes with the operating boilers at full fire.",
                 "Another boiler stages on when the hot water supply temperature is {dT:stg} under setpoint for 10 minutes and the running boilers are at full fire.",
                 {"contra": "Another boiler stages on when the hot water supply temperature is {dT:stg} under setpoint for 10 minutes, whatever the firing rate of the running boilers."}),
            Para("3.3.3", "Each boiler shall operate no lower than {fire_min} percent firing rate.",
                 "Each boiler holds a minimum firing rate of {fire_min} percent."),
        ]),
        Section("3.4", "Hot Water Pumping", [
            Para("3.4.1", "Pump speed shall be modulated to maintain the remote differential pressure at setpoint, reset between {D:dp_min} and {D:dp_max} by trim and respond logic.",
                 "Pump speed modulates to hold remote differential pressure at a setpoint reset by trim and respond logic between {D:dp_min} and {D:dp_max}.",
                 {"setpt": "Pump speed modulates to hold remote differential pressure at a setpoint reset by trim and respond logic between {D:dp_min} and {D:dp_max_bad}."}),
            Para("3.4.2", "On failure of the lead pump, the lag pump shall start and a Level 2 alarm shall be set.",
                 "If the lead pump fails, the lag pump starts and a Level 2 alarm is set.",
                 {"alarm": "If the lead pump fails, the lag pump starts."}),
        ]),
        Section("3.5", "Safeties and Interlocks", [
            Para("3.5.1", "Each boiler shall be hardwired to its flow switch and low water cutoff so that it cannot fire without proven flow and water level.",
                 "The flow switch and low water cutoff are hardwired in each boiler firing circuit so the boiler cannot fire without proven flow and water level.",
                 {"interlock": "Each boiler firing circuit includes the flow switch so the boiler cannot fire without proven flow."}),
            Para("3.5.2", "Each boiler high limit control shall be set at {T:hlim} and shall require a manual reset.",
                 "Each boiler high limit is set at {T:hlim} with manual reset.",
                 {"setpt": "Each boiler high limit is set at {T:hlim_bad} with manual reset.",
                  "interlock": "Each boiler high limit is set at {T:hlim} with automatic reset."}),
            Para("3.5.3", "The emergency shutoff switch at the boiler room exit shall be hardwired to stop all boilers, and the BAS shall set a Level 1 alarm.",
                 "The boiler room exit emergency shutoff switch is hardwired to stop every boiler, and the BAS sets a Level 1 alarm.",
                 {"interlock": ABSENT, "alarm": "The boiler room exit emergency shutoff switch is hardwired to stop every boiler, and the BAS sets a Level 3 alarm."}),
        ]),
    ]
    d1 = f"DDC-HWP{n}-1"
    P = [Point(f"{eq}-HWST", "Hot water supply temperature", "AI", "temp", (40, 240), f"TT-{n}-HWS", d1, Alarm(3, "dev", 10, 15)),
         Point(f"{eq}-HWRT", "Hot water return temperature", "AI", "temp", (40, 240), f"TT-{n}-HWR", d1),
         Point(f"{eq}-HW-DP", "Remote hot water differential pressure", "AI", "wdp", (0, 50), f"DPT-{n}-HW", d1, Alarm(3, "below", p["dp_min"] - 1, 10), bad_io="BI"),
         Point(f"{eq}-OAT", "Outdoor air temperature", "AI", "temp", (-40, 130), f"TT-{n}-OA", d1),
         Point(f"{eq}-HW-FS", "Hot water flow switch", "BI", "bin", ("No flow", "Flow"), f"FS-{n}-HW", d1, bad_io="AI"),
         Point(f"{eq}-ESS", "Boiler room emergency shutoff status", "BI", "bin", ("Normal", "Stop"), f"ES-{n}-1", d1, Alarm(1, "trip"))]
    for k in range(1, boilers + 1):
        P += [Point(f"{eq}-B{k}-EN", f"Boiler {k} enable", "BO", "bin", ("Off", "On"), f"B-{n}{k}", d1),
              Point(f"{eq}-B{k}-S", f"Boiler {k} status", "BI", "bin", ("Off", "On"), f"B-{n}{k}", d1, Alarm(2, "mismatch", delay=120), bad_io="AI"),
              Point(f"{eq}-B{k}-ALM", f"Boiler {k} common alarm", "BI", "bin", ("Normal", "Alarm"), f"B-{n}{k}", d1, Alarm(2, "trip")),
              Point(f"{eq}-HWP{k}-SPD", f"Hot water pump {k} speed command", "AO", "pct", (0, 100), f"VFD-{n}-P{k}", d1, bad_io="BO"),
              Point(f"{eq}-HWP{k}-S", f"Hot water pump {k} status", "BI", "bin", ("Off", "On"), f"VFD-{n}-P{k}", d1, Alarm(2, "mismatch", delay=15), bad_io="AI")]
    extras = {"3.3.3": ("3.3.3a", "Boiler lead and lag order rotates weekly, adjustable at the operator workstation.")}
    local = [Device(f"PG-{n}-HWS", "Hot water supply pressure gauge, local", "-", "M-901", [], "none (local gauge, no BAS connection)")]
    return _system("hw_plant", eq, f"Hot Water Boiler Plant {eq}", S, P, extras, local), p


def _system(key, eq, title, sections, points, extras, local) -> System:
    by_dev: dict[str, Device] = {}
    for pt in points:
        d = by_dev.get(pt.device)
        if d is None:
            sheet = {"ahu_mz": "M-501", "ahu_sz": "M-502", "vav_rh": "M-601", "fcu": "M-701", "chw_plant": "M-801",
                     "hw_plant": "M-901"}[key]
            d = by_dev[pt.device] = Device(pt.device, _device_desc(pt), pt.ddc, sheet, [])
        d.points.append(pt.name)
    return System(key, eq, title, sections, points, list(by_dev.values()), extras, local)


def _device_desc(pt: Point) -> str:
    prefix = pt.device.split("-")[0]
    names = {"VFD": "Variable frequency drive", "DPT": "Differential pressure transmitter", "TT": "Temperature sensor",
             "AFMS": "Airflow measuring station", "DMP": "Damper actuator", "VLV": "Control valve actuator",
             "TS": "Temperature switch or sensor", "SD": "Duct smoke detector", "PS": "Pressure switch",
             "FS": "Flow switch or sensor", "DA": "Damper actuator", "M": "Fan motor and speed controller",
             "CS": "Current switch", "LS": "Level switch", "FM": "Flow meter", "CH": "Chiller", "RM": "Refrigerant monitor",
             "ES": "Emergency stop switch", "B": "Boiler"}
    return f"{names.get(prefix, 'Device')}, {pt.desc.lower()}"


TEMPLATES = {"ahu_mz": ahu_multizone, "ahu_sz": ahu_single_zone, "vav_rh": vav_reheat, "fcu": fan_coil,
             "chw_plant": chilled_water_plant, "hw_plant": boiler_plant}
