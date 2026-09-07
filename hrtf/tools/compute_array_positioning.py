#!/usr/bin/env python3
"""Recover the receiver positions of an array from the measured IR onset delays"""

from __future__ import division

import os
import sys
import glob
import yaml
import logging
import argparse

import numpy as np
from scipy.optimize import least_squares
from multiprocessing import Pool

logger = logging.getLogger(__name__)

# libyaml if it is installed. a measure set holds one 676 line config.yaml per source
# position and the pure python parser needs 26 s for 792 of them against 2.8 s here.
try:
    from yaml import CSafeLoader as YamlLoader
except ImportError:
    from yaml import SafeLoader as YamlLoader

#
# DEFINES / CONSTANT / GLOBALS
#
# which receivers to solve for.
#
# the listener comes from ess_params.yaml and every rig has a different one, so
# nothing here is hardcoded to a particular array: -l picks receivers by the
# short_name they carry in config.yaml, with the same "short_name[,description]"
# syntax that compute_3dti_sofa.py -s already uses.
#
# with no selection at all we take every receiver EXCEPT the groups whose nominal
# coordinates are all identical. that is not a special case for the ambisonic
# capsules, it is a statement about what is solvable: receivers that config.yaml
# places on the very same point are a placeholder, they cannot be told apart from
# one another, and on this rig their onsets scatter by 100..200 us, ten times the
# spread of every other channel. ask for them explicitly if you want them anyway.
_DEGENERATE_GROUP_MIN = 2

# HEAD / NO-HEAD MODEL SELECTION
#
# a receiver only sees a straight line to the source while the source is on its own
# side. _LIT_ANGLE_deg is the half angle of that cone, measured from the receiver's
# own direction: inside it the arrival time is pure geometry with or without a head
# in the middle, outside it a head (if there is one) forces the wave to creep around
# the surface and the arrival is late by a hundred microseconds or more.
_LIT_ANGLE_deg = 75.0

# how we decide whether something is blocking the direct path.
#
# NOT by comparing residuals: a model fitted on the cone is always better on the cone,
# so that ratio is above one even in free air and the two cases overlap.
#
# an obstacle can only ever make the sound arrive LATE. so we look at the SIGN of the
# miss in the deep shadow: with a head in the middle every shadowed arrival is late by
# a hundred microseconds or more and the mean is strongly positive, with nothing in the
# middle the model is simply right there and the misses average out around zero.
# the antipodal cap is where the creeping wave is at its longest and the two cases are
# furthest apart. measured: -3 us with the mics on stands in free air, +80 us with a
# dummy head in the middle. _DEEP_SHADOW_deg is the fallback when a partial grid leaves
# the cap too thin to average.
_ANTIPODE_deg = 150.0
_DEEP_SHADOW_deg = 120.0
_ANTIPODE_MIN_POINTS = 50
_HEAD_DETECT_EXCESS_s = 30e-6

# reading the measure folders is the whole cost of this tool, the solve itself takes
# a fraction of a second. 0 means "ask the machine", within reason.
_JOBS_DEFAULT = 0
# below this many folders the pool costs more to start than it saves
_JOBS_MIN_FOLDERS = 64
# past this the work is waiting on the disk, not on a core. measured on a 792 position
# set: 4.1 s on one process, 1.1 s on 8, 0.9 s on 16, and 0.9 s again on 64 while
# burning 3 s more CPU to get there. a bigger default would only be a worse neighbour.
_JOBS_CAP = 16

# outlier rejection: a residual this many sigma away from the fit is dropped and the
# fit is repeated once. a handful of IRs in a full set have an onset that lands on a
# reflection instead of the direct sound.
_SIGMA_CLIP = 5.0

# solver bounds, they only exist to stop the fit running away. the receiver offset,
# the source distance and the constant per-channel latency are all degenerate with
# each other at first order, so an unbounded solve can trade a 3 m latency against a
# 700 m source radius and still land on a low residual.
_POSITION_BOUND_m = 0.30
_LATENCY_BOUND_s = 0.002
_RADIUS_BOUND_m = 0.25

# the elevation arm is positioned by hand (see the ToDo in record_ess_map.py) and does
# not come back to the same distance twice, so each elevation ring gets its own source
# radius. left completely free that is a trap: on the shadowed model only the
# line-of-sight cone is usable, and inside a narrow cone a receiver can slide along the
# cone axis while the radius follows it, with no penalty. so the radius is given a
# prior instead of pure freedom: the tape says the source is at the distance written in
# config.yaml, to within _DISTANCE_TOLERANCE_m. with a full sphere of data the prior is
# negligible and the rings still come out wherever the data puts them.
_DISTANCE_TOLERANCE_m = 0.05
# expected onset noise of a single IR, used to weigh that prior against the data
_ONSET_NOISE_s = 20e-6

# WRITING BACK INTO THE MEASURE FOLDERS (--fix)
#
# a measure config.yaml is machine written by record_ess_map, so loading it and dumping
# it back with these settings reproduces the file byte for byte. that is what makes a
# safe surgical edit possible: we check that property on every single file before
# touching it, and only then dump the same tree with the coordinates replaced. the
# output can then differ from the original in the coordinate lines and nowhere else.
# a file that fails the check is left alone and reported.
_YAML_DUMP = {"default_flow_style": False, "sort_keys": True, "width": 4096}
# top level key of the --force file
_FORCE_ROOT = "listeners"

# speed of sound, computed from the room temperature written in config.yaml
_SOUND_SPEED_0C_ms = 331.3
_KELVIN_0C = 273.15

# Woodworth: on the shadowed side of a sphere of radius a the wave leaves the straight
# path at the tangent point and creeps along the surface, arriving late by
#
#     excess(psi) = (a/c) * (psi - pi/2 + cos psi)     for psi > 90 deg
#
# regressing the measured excess on that shape gives a/c, and with it the size of
# whatever the sound had to travel around. it is a sanity check, not a calibrated
# measurement: a real head is not a sphere and the mics stand off its surface, so
# expect it a couple of centimetres on the generous side. nothing in the position
# solve depends on it. the cut at 120 deg keeps out the shadow boundary, where real
# diffraction is smooth and Woodworth's kink is not.
_WOODWORTH_MIN_deg = 120.0


#
# TOOLS
#
def sound_speed(kelvin):
    """Speed of sound in dry air at the given absolute temperature, in m/s."""
    return _SOUND_SPEED_0C_ms * np.sqrt(kelvin / _KELVIN_0C)


def source_unit_vectors(azimuth_deg, elevation_deg):
    """Unit vectors pointing at the source, same convention as record_ess_map.py."""
    az = np.deg2rad(azimuth_deg)
    el = np.deg2rad(elevation_deg)
    return np.c_[np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)]


def receiver_name(receiver_config):
    """Human readable receiver name, "<short_name> <description>"."""
    short_name = receiver_config.get("short_name", "")
    description = receiver_config.get("description", "")
    return "{} {}".format(short_name, description).strip()


#
# RECEIVER SELECTION
#
def first_config(root):
    """The config.yaml of the first measure position under root, and the folder list."""
    folders = sorted(glob.glob(os.path.join(root, "*_xAngle")))
    if len(folders) == 0:
        # tolerate being pointed straight at a single measure position
        if os.path.isfile(os.path.join(root, "config.yaml")):
            folders = [root]

    if len(folders) == 0:
        sys.exit("\n[ERROR] no measure positions (*_xAngle folders) found under {}".format(root))

    for folder in folders:
        try:
            with open(os.path.join(folder, "config.yaml"), "r") as file:
                config = yaml.load(file, Loader=YamlLoader)
            if config["setup"]["listeners"][0]["receivers"] != None:
                return config, folders
        except Exception:
            continue

    sys.exit("\n[ERROR] no readable config.yaml with a receivers block under {}".format(root))


def match_selector(receiver, selector):
    """Does one receiver match one "short_name[,description]" selector?

    Same rule as compute_3dti_sofa.py --select_rx: the short name has to be exact,
    the optional second field only has to appear somewhere in the description.
    """
    key = selector.split(",")
    if len(key) == 1:
        key.append(None)

    if receiver.get("short_name") != key[0]:
        return False

    if key[1] == None:
        return True

    return key[1] in str(receiver.get("description", ""))


def degenerate_receivers(receivers):
    """Receivers that config.yaml puts on the exact same point as one another."""
    seen = {}
    for rx in receivers:
        try:
            spot = tuple(float(v) for v in receivers[rx]["position"]["coord"]["value"])
        except Exception:
            continue
        seen.setdefault(spot, []).append(rx)

    degenerate = []
    for spot in seen:
        if len(seen[spot]) >= _DEGENERATE_GROUP_MIN:
            degenerate += seen[spot]

    return sorted(degenerate)


def resolve_receivers(config, selectors, ids):
    """Turn the command line selection into an ordered list of receiver ids."""
    receivers = config["setup"]["listeners"][0]["receivers"]
    available = sorted(receivers)

    if selectors != None:
        chosen = []
        for selector in selectors:
            matched = [rx for rx in available if match_selector(receivers[rx], selector)]
            if len(matched) == 0:
                names = sorted(set(str(receivers[rx].get("short_name")) for rx in available))
                sys.exit(
                    "\n[ERROR] no receiver matches '{}'. short names in this config: {}".format(
                        selector, ", ".join(names)
                    )
                )
            logger.info(
                "compute array positioning: '{}' matches rx {}".format(
                    selector, ", ".join(str(rx) for rx in matched)
                )
            )
            chosen += [rx for rx in matched if rx not in chosen]
    else:
        # no selection: everything the rig can actually resolve
        chosen = list(available)
        dropped = degenerate_receivers(receivers)
        if len(dropped) > 0:
            chosen = [rx for rx in chosen if rx not in dropped]
            logger.warning(
                "compute array positioning: dropping rx {} , config.yaml puts them on the "
                "same point so they cannot be told apart. select them by name to override.".format(
                    ", ".join(str(rx) for rx in dropped)
                )
            )

    if ids != None:
        chosen = [rx for rx in chosen if rx in ids]

    if len(chosen) < 2:
        sys.exit("\n[ERROR] at least two receivers are needed, the selection resolves to {}".format(chosen))

    logger.info(
        "compute array positioning: solving for rx {}".format(", ".join(str(rx) for rx in chosen))
    )

    return chosen


#
# FORCED POSITIONS  (--force)
#
def read_forced_positions(path, rx_list, receivers):
    """Read receiver coordinates from a hand written yaml file.

    Expected shape, the same one this tool prints:

        listeners:
          4:
            position:
              coord:
                value: [-0.024, +0.075, +0.006]

    Returns a dict rx -> [x, y, z] holding only the receivers we are solving for.
    """
    try:
        with open(path, "r") as file:
            forced = yaml.load(file, Loader=YamlLoader)
    except Exception as exc:
        sys.exit("\n[ERROR] cannot read the forced position file {}: {}".format(path, exc))

    if not isinstance(forced, dict) or _FORCE_ROOT not in forced:
        sys.exit("\n[ERROR] {} has no '{}:' block at the top level".format(path, _FORCE_ROOT))

    entries = forced[_FORCE_ROOT]
    if not isinstance(entries, dict):
        sys.exit("\n[ERROR] '{}:' in {} is not a mapping of receiver id -> position".format(_FORCE_ROOT, path))

    positions = {}
    for rx in entries:
        try:
            value = entries[rx]["position"]["coord"]["value"]
            coordinate = [float(v) for v in value]
        except Exception:
            sys.exit(
                "\n[ERROR] receiver {} in {} has no readable position.coord.value".format(rx, path)
            )

        if len(coordinate) != 3:
            sys.exit("\n[ERROR] receiver {} in {} needs 3 coordinates, got {}".format(rx, path, len(coordinate)))

        if rx not in receivers:
            logger.warning(
                "compute array positioning: {} holds rx {} which this listener does not declare, ignored".format(
                    path, rx
                )
            )
            continue

        positions[rx] = coordinate

    # "is the array in this file?" - the whole point of the check the file has to pass
    present = [rx for rx in rx_list if rx in positions]
    missing = [rx for rx in rx_list if rx not in positions]

    if len(present) == 0:
        sys.exit(
            "\n[ERROR] {} holds no position for any receiver being solved ({}).".format(
                path, ", ".join(str(rx) for rx in rx_list)
            )
            + "\n        this file is for a different array."
        )

    logger.info(
        "compute array positioning: {} takes precedence for rx {}".format(
            path, ", ".join(str(rx) for rx in present)
        )
    )
    if len(missing) > 0:
        logger.warning(
            "compute array positioning: {} says nothing about rx {}, the measured position is used there".format(
                path, ", ".join(str(rx) for rx in missing)
            )
        )

    return {rx: positions[rx] for rx in present}


#
# MEASURE FOLDER SCAN
#
def read_ir_delay(path):
    """The onset delay out of one IR sidecar, in seconds, or None.

    The sidecar is a dozen lines written by compute_hrir and we want exactly one
    scalar out of it, so this walks the lines instead of building a parse tree:
    0.1 s for a whole measure set against 4.1 s through yaml.
    """
    try:
        with open(path, "r") as file:
            for line in file:
                if line.startswith("ir_delay:"):
                    return float(line.split(":", 1)[1].strip().strip("'\""))
    except Exception:
        return None

    return None


def read_measure_position(folder, rx_list):
    """Read one measure position. Returns (source value, delays, complaints).

    source value : [azimuth deg, elevation deg, distance m] as written by the positioner
    delays       : dict rx -> IR onset delay in seconds
    complaints   : anything worth logging, collected rather than logged because this
                   runs in a worker process where the logger goes nowhere
    """
    complaints = []
    config_file = os.path.join(folder, "config.yaml")

    try:
        with open(config_file, "r") as file:
            config = yaml.load(file, Loader=YamlLoader)
        source = config["setup"]["sources"][0]["position"]["coord"]
    except Exception as exc:
        return None, {}, ["cannot read the source position from {}: {}".format(config_file, exc)]

    if source.get("type") != "spherical":
        return None, {}, ["{} source is not spherical, skipped".format(config_file)]

    delays = {}
    for rx in rx_list:
        # "<name>_IR_rx_<n>_trid_<t>.yaml", the trailing "_trid_" keeps rx 1 and rx 11 apart
        matches = glob.glob(os.path.join(folder, "ir", "*_IR_rx_{}_trid_*.yaml".format(rx)))
        if len(matches) != 1:
            complaints.append("{} has {} sidecars for rx {}".format(folder, len(matches), rx))
            continue

        delay = read_ir_delay(matches[0])
        if delay == None:
            complaints.append("no ir_delay in {}".format(matches[0]))
            continue

        delays[rx] = delay

    return list(source["value"]), delays, complaints


def scan_worker(job):
    """Pool entry point. One measure folder in, its onset delays out."""
    folder, rx_list = job
    return read_measure_position(folder, rx_list)


def scan_measures(folders, rx_list, config, jobs):
    """Walk every measure position and collect the onset delays.

    Every folder is independent, so this is handed to a process Pool the same way
    compute_hrir does it. Processes rather than threads on purpose: the work is a
    yaml parse, which is CPU held under the GIL, and threads would serialise on it.

    Returns a dict with the flattened observations, one entry per (position, rx).
    """
    if jobs <= 0:
        jobs = min(os.cpu_count() or 1, _JOBS_CAP)
    jobs = max(1, min(jobs, len(folders)))
    if len(folders) < _JOBS_MIN_FOLDERS:
        jobs = 1

    logger.info(
        "compute array positioning: scanning {} measure positions on {} process(es)".format(len(folders), jobs)
    )

    work = [(folder, rx_list) for folder in folders]
    if jobs > 1:
        with Pool(jobs) as pool:
            results = pool.map(scan_worker, work, chunksize=16)
    else:
        results = [scan_worker(job) for job in work]

    azimuth = []
    elevation = []
    distance = []
    delay = []
    index = []

    for source, delays, complaints in results:
        for complaint in complaints:
            logger.warning("compute array positioning: {}".format(complaint))

        if source == None:
            continue

        for rx in delays:
            azimuth.append(source[0])
            elevation.append(source[1])
            distance.append(source[2])
            delay.append(delays[rx])
            index.append(rx_list.index(rx))

    if len(delay) == 0:
        sys.exit("\n[ERROR] no IR onset delays found, is compute_hrir done for this set?")

    data = {
        "azimuth": np.array(azimuth, dtype=float),
        "elevation": np.array(elevation, dtype=float),
        "distance": np.array(distance, dtype=float),
        "delay": np.array(delay, dtype=float),
        "index": np.array(index, dtype=int),
        "receivers": config["setup"]["listeners"][0]["receivers"],
        "config": config,
        "positions": len(folders),
    }

    logger.info(
        "compute array positioning: collected {} onset delays over {} receivers".format(len(delay), len(rx_list))
    )

    return data


#
# GEOMETRY SOLVER
#
# every receiver contributes its own position p and its own constant channel latency
# t0, every elevation ring contributes its own source radius R because the elevation
# arm is positioned by hand and does not come back to the same distance twice:
#
#     t(rx, az, el) = t0(rx) + | R(el) * u(az, el) - p(rx) | / c
#
# one radius has to be pinned or the whole thing slides: R, t0 and |p| all move the
# mean arrival time together. we pin the ring closest to the horizon to the distance
# the positioner wrote into config.yaml, which is the one you actually measured with
# a tape.
#
def unpack_parameters(q, receiver_count, ring_count, ring_pinned, radius_pinned):
    """Split the solver vector into positions, latencies and per-ring source radii."""
    positions = q[: receiver_count * 3].reshape(receiver_count, 3)
    latency = q[receiver_count * 3 : receiver_count * 4]
    free = q[receiver_count * 4 :]

    radius = np.empty(ring_count)
    radius[:ring_pinned] = free[:ring_pinned]
    radius[ring_pinned] = radius_pinned
    radius[ring_pinned + 1 :] = free[ring_pinned:]

    return positions, latency, radius


def model_and_jacobian(q, data, mask, c_air, shape, want_jacobian):
    """Predicted arrival times, and the analytic jacobian if asked for."""
    receiver_count, ring_count, ring_pinned, radius_pinned = shape
    positions, latency, radius = unpack_parameters(q, receiver_count, ring_count, ring_pinned, radius_pinned)

    rx = data["index"][mask]
    ring = data["ring"][mask]
    u = data["unit"][mask]

    # vector from the receiver to the source, and its length
    reach = radius[ring][:, None] * u - positions[rx]
    norm = np.linalg.norm(reach, axis=1)
    predicted = latency[rx] + norm / c_air

    if not want_jacobian:
        return predicted, None

    rows = np.arange(len(rx))
    jac = np.zeros((len(rx), len(q)))

    # d/dp = -(R*u - p) / (|R*u - p| * c)
    for axis in range(3):
        jac[rows, rx * 3 + axis] = -reach[:, axis] / (norm * c_air)

    # d/dt0 = 1
    jac[rows, receiver_count * 3 + rx] = 1.0

    # d/dR = (R - u.p) / (|R*u - p| * c) , only for the rings we did not pin
    d_radius = (radius[ring] - np.einsum("ij,ij->i", u, positions[rx])) / (norm * c_air)
    free_column = np.where(ring < ring_pinned, ring, ring - 1)
    keep = ring != ring_pinned
    jac[rows[keep], receiver_count * 4 + free_column[keep]] = d_radius[keep]

    return predicted, jac


def solve(data, mask, c_air, shape, start, radius_tolerance, z_reference):
    """Least squares solve of the whole geometry. Returns the parameter vector.

    radius_tolerance is how far each elevation ring is allowed to wander from the
    distance the positioner wrote into config.yaml. Pass 0 to nail every ring to it,
    which turns the fit into a rigid, always well-posed problem.

    z_reference fixes a gauge. Lifting every receiver by the same amount and lowering
    the whole source arc by the same amount produce identical arrival times, so the
    common part of z is not observable at all and the solver, left alone, will happily
    run it into the bounds. We hold the MEAN of z at z_reference and let the data
    place the receivers relative to each other, which is the part it can actually see.
    """
    receiver_count, ring_count, ring_pinned, radius_pinned = shape
    free_rings = ring_count - 1
    # stiff on purpose: this is a gauge, not a measurement
    gauge_weight = _ONSET_NOISE_s / 0.001

    # a prior row per free ring: the tape measure says this radius, to within
    # radius_tolerance. weighted against the expected onset noise of one IR.
    prior_weight = 0.0
    if radius_tolerance > 0:
        prior_weight = _ONSET_NOISE_s / radius_tolerance

    span = max(radius_tolerance * 5, 1e-6) if radius_tolerance > 0 else 1e-6
    span = min(span, _RADIUS_BOUND_m)

    lower = np.r_[
        np.full(receiver_count * 3, -_POSITION_BOUND_m),
        np.full(receiver_count, -_LATENCY_BOUND_s),
        np.full(free_rings, radius_pinned - span),
    ]
    upper = np.r_[
        np.full(receiver_count * 3, _POSITION_BOUND_m),
        np.full(receiver_count, _LATENCY_BOUND_s),
        np.full(free_rings, radius_pinned + span),
    ]

    z_columns = np.arange(receiver_count) * 3 + 2

    def residual(q):
        predicted, _ = model_and_jacobian(q, data, mask, c_air, shape, False)
        rows = predicted - data["delay"][mask]
        if prior_weight > 0:
            rows = np.r_[rows, (q[receiver_count * 4 :] - radius_pinned) * prior_weight]
        return np.r_[rows, (np.mean(q[z_columns]) - z_reference) * gauge_weight]

    def jacobian(q):
        _, jac = model_and_jacobian(q, data, mask, c_air, shape, True)
        if prior_weight > 0:
            prior = np.zeros((free_rings, len(q)))
            prior[np.arange(free_rings), receiver_count * 4 + np.arange(free_rings)] = prior_weight
            jac = np.vstack([jac, prior])
        gauge = np.zeros((1, len(q)))
        gauge[0, z_columns] = gauge_weight / receiver_count
        return np.vstack([jac, gauge])

    start = np.clip(start, lower, upper)
    result = least_squares(residual, start, jac=jacobian, bounds=(lower, upper), xtol=1e-14, ftol=1e-14)

    return result.x


def initial_estimate(data, c_air, receiver_count):
    """Closed-form starting point for the solver, one linear solve per receiver.

    Far from the array the arrival time flattens to a plane wave,

        t = t0 + R/c - (p . u)/c

    which is linear in the receiver position, so a plain least squares on [1, ux, uy,
    uz] lands within a centimetre or so with no local minima to fall into. The
    nonlinear solve needs this: started from a constant guess every receiver has the
    same direction, the line-of-sight cone is meaningless and the fit walks off into
    a 30 cm / 2 m corner of the parameter space and stays there.
    """
    positions = np.zeros((receiver_count, 3))
    latency = np.zeros(receiver_count)

    for i in range(receiver_count):
        rows = data["index"] == i
        design = np.c_[np.ones(int(rows.sum())), data["unit"][rows]]
        coefficients, *_ = np.linalg.lstsq(design, data["delay"][rows], rcond=None)
        positions[i] = -c_air * coefficients[1:]
        latency[i] = coefficients[0]

    # the constant term still holds R/c, only the differences between channels are
    # latency. leave the common part to the solver, it has the radius to trade with.
    latency = latency - np.mean(latency)

    return positions, latency


def source_angle(q, data, shape):
    """Angle between each source direction and the receiver's own direction, degrees."""
    receiver_count, ring_count, ring_pinned, radius_pinned = shape
    positions, _, _ = unpack_parameters(q, receiver_count, ring_count, ring_pinned, radius_pinned)

    # a receiver sitting exactly on the origin has no direction of its own
    length = np.linalg.norm(positions, axis=1)
    length[length <= 0] = 1.0
    facing = positions / length[:, None]

    cosine = np.einsum("ij,ij->i", data["unit"], facing[data["index"]])
    return np.rad2deg(np.arccos(np.clip(cosine, -1.0, 1.0)))


def lit_mask(q, data, shape, lit_angle_deg):
    """True where the source is inside the receiver's own line-of-sight cone."""
    return source_angle(q, data, shape) < lit_angle_deg


def far_side_excess(residual, angle):
    """Mean SIGNED miss on the far side of the array. Returns (excess, cut, points).

    Signed on purpose: an obstacle can only ever make the sound arrive late, so a
    positive mean means something is in the way while noise averages out around zero.
    Measured on real sets: -3 us with the mics on stands in free air, +80 us with a
    dummy head in the middle.
    """
    cut = _ANTIPODE_deg
    cap = (angle > cut) & np.isfinite(residual)
    if cap.sum() < _ANTIPODE_MIN_POINTS:
        cut = _DEEP_SHADOW_deg
        cap = (angle > cut) & np.isfinite(residual)

    if cap.sum() == 0:
        return 0.0, cut, 0

    return float(np.mean(residual[cap])), cut, int(cap.sum())


def rms_of(values):
    """RMS of the finite entries, 0 when there are none. numpy warns on empty slices."""
    finite = np.isfinite(values)
    if finite.sum() == 0:
        return 0.0
    return float(np.sqrt(np.mean(values[finite] ** 2)))


def residual_of(q, data, mask, c_air, shape):
    """Signed residual (measured - model) over the whole dataset, NaN outside mask."""
    predicted, _ = model_and_jacobian(q, data, mask, c_air, shape, False)
    residual = np.full(len(data["delay"]), np.nan)
    residual[mask] = data["delay"][mask] - predicted
    return residual


def fit_geometry(data, c_air, rx_list, lit_angle_deg, model, clip, distance_tolerance):
    """Fit the array geometry, choosing the free-field or the shadowed model.

    Returns the parameter vector, the mask of the points that were used, the signed
    residual over every point, and the name of the model that was applied.
    """
    rings = np.unique(data["elevation"])
    data["ring"] = np.searchsorted(rings, data["elevation"])
    data["unit"] = source_unit_vectors(data["azimuth"], data["elevation"])

    # pin the ring closest to the horizon, that is the one measured with a tape
    ring_pinned = int(np.argmin(np.abs(rings)))
    radius_pinned = float(np.median(data["distance"][data["ring"] == ring_pinned]))
    shape = (len(rx_list), len(rings), ring_pinned, radius_pinned)

    # gauge for the unobservable common z, anchored on the nominal geometry so that the
    # numbers we print stay in the coordinate convention of ess_params.yaml
    nominal = np.array(
        [data["receivers"][rx]["position"]["coord"]["value"] for rx in rx_list],
        dtype=float,
    )
    z_reference = float(np.mean(nominal[:, 2]))

    logger.info(
        "compute array positioning: {} elevation rings, pinning ring {:+.0f} deg at {:.3f} m".format(
            len(rings), rings[ring_pinned], radius_pinned
        )
    )

    guess_positions, guess_latency = initial_estimate(data, c_air, len(rx_list))
    start = np.r_[
        guess_positions.ravel(),
        guess_latency,
        np.full(len(rings) - 1, radius_pinned),
    ]
    for i, rx in enumerate(rx_list):
        logger.info(
            "compute array positioning: rx {} starting from [{:+.3f} {:+.3f} {:+.3f}] m".format(rx, *guess_positions[i])
        )

    everything = np.ones(len(data["delay"]), dtype=bool)

    #
    # STEP-01: detection pass. solve on the line-of-sight cone only, which is the one
    #          subset that is valid whether or not there is a head in the middle. the
    #          radius prior is what holds this together: inside a narrow cone the
    #          receiver would otherwise slide along the cone axis with the radius
    #          following it, and the fit walks off to a 30 cm offset at a 2 m radius.
    #
    mask = everything
    q = start
    for _ in range(4):
        q = solve(data, mask, c_air, shape, q, distance_tolerance, z_reference)
        mask = lit_mask(q, data, shape, lit_angle_deg)

    #
    # STEP-02: is anything blocking the direct path? ask the data. the model just
    #          fitted is only claimed to hold inside the cone, so look at how badly
    #          it misses outside it.
    #
    residual = residual_of(q, data, everything, c_air, shape)
    angle = source_angle(q, data, shape)

    if mask.sum() == 0:
        sys.exit(
            "\n[ERROR] no source position falls inside the {:.0f} deg line-of-sight cone of any "
            "receiver.\n        this set cannot constrain the geometry, widen it with -la or "
            "measure more directions.".format(lit_angle_deg)
        )

    lit_rms = rms_of(residual[mask])
    shadow_rms = rms_of(residual[~mask])

    excess, cut, points = far_side_excess(residual, angle)

    logger.info(
        "compute array positioning: residual {:.1f} us inside the line-of-sight cone, "
        "{:.1f} us outside it".format(lit_rms * 1e6, shadow_rms * 1e6)
    )
    logger.info(
        "compute array positioning: mean signed miss beyond {:.0f} deg is {:+.1f} us over {} points "
        "(a blocked path can only ever be LATE, threshold {:+.0f} us)".format(
            cut, excess * 1e6, points, _HEAD_DETECT_EXCESS_s * 1e6
        )
    )

    detected = "head" if excess > _HEAD_DETECT_EXCESS_s else "freefield"
    if model == "auto":
        chosen = detected
        logger.info(
            "compute array positioning: model selected automatically -> {}".format(chosen)
        )
    else:
        chosen = model
        if chosen != detected:
            logger.warning(
                "compute array positioning: model forced to '{}' but the data looks like '{}'".format(chosen, detected)
            )

    #
    # STEP-03: final solve with the chosen model, now letting each elevation ring find
    #          its own source radius around the taped one.
    #
    #          free field: nothing blocks anything, use the whole sphere. the data
    #          swamps the prior and the rings land wherever they really are.
    #          head: only the cone is usable, and there the prior is what keeps the
    #          receiver from sliding along the cone axis.
    #
    if chosen == "freefield":
        mask = everything
        q = solve(data, mask, c_air, shape, q, distance_tolerance, z_reference)
    else:
        for _ in range(3):
            q = solve(data, mask, c_air, shape, q, distance_tolerance, z_reference)
            mask = lit_mask(q, data, shape, lit_angle_deg)

    #
    # STEP-04: drop the few IRs whose onset landed on a reflection, then refit once
    #
    if clip > 0:
        residual = residual_of(q, data, mask, c_air, shape)
        limit = clip * rms_of(residual[mask])
        rejected = mask & (np.abs(np.nan_to_num(residual)) > limit)
        if rejected.sum() > 0:
            logger.info(
                "compute array positioning: rejecting {} of {} points beyond {:.0f} sigma ({:.1f} us)".format(
                    rejected.sum(), mask.sum(), clip, limit * 1e6
                )
            )
            mask = mask & ~rejected
            q = solve(data, mask, c_air, shape, q, distance_tolerance, z_reference)

    residual = residual_of(q, data, everything, c_air, shape)

    return q, mask, residual, chosen, shape, rings, excess, angle, z_reference


def woodworth_radius(residual, angle, c_air):
    """Radius of the obstacle, regressed from how late the shadowed arrivals are.

    Every shadowed point contributes, not just the antipodal ones: the excess has a
    known shape in psi, so a single slope through all of it is both more accurate and
    far less noisy than averaging one cap.
    """
    shadow = (angle > _WOODWORTH_MIN_deg) & np.isfinite(residual)
    if shadow.sum() < _ANTIPODE_MIN_POINTS:
        return None, 0

    psi = np.deg2rad(angle[shadow])
    shape = psi - np.pi / 2.0 + np.cos(psi)
    slope = np.sum(shape * residual[shadow]) / np.sum(shape**2)

    return slope * c_air, int(shadow.sum())


#
# WRITE BACK  (--fix)
#
def fix_worker(job):
    """Rewrite position.coord.value for one measure folder. Returns (state, detail).

    Nothing else in the file may change, so the edit is guarded: a config.yaml that
    does not survive a load/dump round trip untouched is left exactly as it is and
    reported, because for such a file we could not promise that.
    """
    folder, positions = job
    config_file = os.path.join(folder, "config.yaml")

    try:
        with open(config_file, "r") as file:
            original = file.read()
    except Exception as exc:
        return "error", "cannot read {}: {}".format(config_file, exc)

    try:
        config = yaml.load(original, Loader=YamlLoader)
    except Exception as exc:
        return "error", "cannot parse {}: {}".format(config_file, exc)

    # the guarantee: this exact tree dumps back to the exact bytes we just read
    try:
        if yaml.dump(config, **_YAML_DUMP) != original:
            return "skipped", "{} is not byte identical through a yaml round trip, left untouched".format(config_file)
    except Exception as exc:
        return "error", "cannot re-serialise {}: {}".format(config_file, exc)

    try:
        receivers = config["setup"]["listeners"][0]["receivers"]
    except Exception:
        return "error", "{} has no receivers block".format(config_file)

    changed = 0
    for rx in positions:
        if rx not in receivers:
            return "error", "{} does not declare rx {}".format(config_file, rx)

        coordinate = receivers[rx]["position"]["coord"]["value"]
        replacement = [round(float(v), 6) for v in positions[rx]]
        if list(coordinate) != replacement:
            receivers[rx]["position"]["coord"]["value"] = replacement
            changed += 1

    if changed == 0:
        return "unchanged", config_file

    updated = yaml.dump(config, **_YAML_DUMP)

    # write beside the target and rename, so an interrupted run cannot leave a
    # half written config.yaml behind
    temporary = config_file + ".tmp"
    try:
        with open(temporary, "w") as file:
            file.write(updated)
        os.replace(temporary, config_file)
    except Exception as exc:
        try:
            os.remove(temporary)
        except OSError:
            pass
        return "error", "cannot write {}: {}".format(config_file, exc)

    return "fixed", config_file


def apply_fix(folders, positions, jobs):
    """Write the receiver coordinates into every measure folder. Returns an error count."""
    if jobs <= 0:
        jobs = min(os.cpu_count() or 1, _JOBS_CAP)
    jobs = max(1, min(jobs, len(folders)))
    if len(folders) < _JOBS_MIN_FOLDERS:
        jobs = 1

    logger.info(
        "compute array positioning: writing rx {} into {} config.yaml on {} process(es)".format(
            ", ".join(str(rx) for rx in sorted(positions)), len(folders), jobs
        )
    )

    work = [(folder, positions) for folder in folders]
    if jobs > 1:
        with Pool(jobs) as pool:
            results = pool.map(fix_worker, work, chunksize=16)
    else:
        results = [fix_worker(job) for job in work]

    tally = {}
    errors = 0
    for state, detail in results:
        tally[state] = tally.get(state, 0) + 1
        if state == "error":
            errors += 1
            logger.error("compute array positioning: {}".format(detail))
        elif state == "skipped":
            logger.warning("compute array positioning: {}".format(detail))

    logger.info(
        "compute array positioning: {}".format(
            ", ".join("{} {}".format(tally[state], state) for state in sorted(tally))
        )
    )

    return errors, tally


#
# REPORT
#
def print_report(data, q, positions, mask, residual, chosen, shape, rings, excess, angle, c_air, rx_list, forced):
    """Print the fitted geometry, the per-receiver quality and the source arc."""
    receiver_count, ring_count, ring_pinned, radius_pinned = shape
    _, latency, radius = unpack_parameters(q, receiver_count, ring_count, ring_pinned, radius_pinned)
    receivers = data["receivers"]

    model_text = {
        "freefield": "FREE FIELD, nothing blocking the receivers, every direction used",
        "head": "HEAD IN THE MIDDLE, only the line-of-sight cone used",
    }[chosen]

    print("")
    print("array positioning from measured IR onset delays")
    print("===============================================")
    print("  measure positions   : {}".format(data["positions"]))
    print("  observations used   : {} of {}".format(int(mask.sum()), len(mask)))
    print("  speed of sound      : {:.1f} m/s".format(c_air))
    print("  source distance     : {:.3f} m pinned at elevation {:+.0f}".format(radius_pinned, rings[ring_pinned]))
    print("  model               : {}".format(model_text))
    far_excess, far_cut, far_points = far_side_excess(residual, angle)
    print("  far side excess     : {:+.0f} us beyond {:.0f} deg, over {} arrivals".format(
        far_excess * 1e6, far_cut, far_points
    ))
    print("  overall residual    : {:.1f} us".format(rms_of(residual[mask]) * 1e6))
    print("")

    print("  {:>3} {:>24} {:>8} {:>8} {:>8} | {:>8} {:>8} {:>8} | {:>7} {:>8} {:>7}".format(
        "rx", "name", "x cm", "y cm", "z cm", "cfg x", "cfg y", "cfg z", "move cm", "t0 us", "rms us"
    ))
    for i, rx in enumerate(rx_list):
        name = receiver_name(receivers[rx]) if receivers != None and rx in receivers else ""
        if forced != None and rx in forced:
            name = (name + " (forced)").strip()
        nominal = np.array(receivers[rx]["position"]["coord"]["value"], dtype=float)
        moved = np.linalg.norm(np.array(positions[rx]) - nominal) * 100
        own = residual[mask & (data["index"] == i)]
        print("  {:>3} {:>24} {:8.2f} {:8.2f} {:8.2f} | {:8.1f} {:8.1f} {:8.1f} | {:7.2f} {:8.1f} {:7.1f}".format(
            rx,
            name,
            positions[rx][0] * 100,
            positions[rx][1] * 100,
            positions[rx][2] * 100,
            nominal[0] * 100,
            nominal[1] * 100,
            nominal[2] * 100,
            moved,
            latency[i] * 1e6,
            rms_of(own) * 1e6,
        ))

    print("")
    print("  source arc radius per elevation ring [m], the pinned one is marked *")
    print("   " + "  ".join(
        "{:+.0f}:{:.3f}{}".format(e, r, "*" if j == ring_pinned else " ") for j, (e, r) in enumerate(zip(rings, radius))
    ))

    if chosen == "head":
        radius, points = woodworth_radius(residual, angle, c_air)
        if radius != None:
            print("")
            print("  obstacle radius     : {:.1f} cm (rough, from {} shadowed arrivals)".format(radius * 100, points))

    print("")


def resolve_positions(q, shape, rx_list, forced, z_reference):
    """Final coordinate per receiver: the forced file where it speaks, the fit elsewhere.

    The common part of z is snapped onto the gauge here rather than left wherever the
    solver's soft prior stopped. It costs nothing, because that common part is not
    observable in the first place, and it buys exact repeatability: without it a run of
    --fix moves the nominal z, the next run re-anchors on the value it just wrote, and
    the whole array creeps upward a millimetre at a time.
    """
    receiver_count, ring_count, ring_pinned, radius_pinned = shape
    fitted, _, _ = unpack_parameters(q, receiver_count, ring_count, ring_pinned, radius_pinned)

    fitted = np.array(fitted, dtype=float)
    fitted[:, 2] += z_reference - float(np.mean(fitted[:, 2]))

    positions = {}
    for i, rx in enumerate(rx_list):
        if forced != None and rx in forced:
            positions[rx] = [float(v) for v in forced[rx]]
        else:
            positions[rx] = [float(v) for v in fitted[i]]

    return positions


def print_yaml_block(data, positions, rx_list, forced):
    """Print the receiver coordinates ready to paste into ess_params.yaml."""
    receivers = data["receivers"]

    print("")
    print("  ess_params.yaml, setup.listeners.0.receivers, replace position.coord.value")
    print("  ------------------------------------------------------------------------")
    for rx in rx_list:
        name = receiver_name(receivers[rx]) if receivers != None and rx in receivers else ""
        if forced != None and rx in forced:
            name = (name + " (forced)").strip()
        print("        {}:{}# {}".format(rx, " " * max(1, 5 - len(str(rx))), name))
        print("          position:")
        print("            coord:")
        print("              value: [{:+.3f}, {:+.3f}, {:+.3f}]".format(*positions[rx]))
    print("")


#
# MAIN
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Recover the receiver positions of an array from the measured IR onset delays."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        required=True,
        help="folder holding the measure positions (the *_xAngle subfolders)",
    )
    parser.add_argument(
        "-l",
        "--list_rx",
        type=str,
        nargs="+",
        default=None,
        help="receivers to solve for, by the short_name they carry in config.yaml. "
        "space separated, and each entry may narrow the group with a description "
        "filter, same syntax as compute_3dti_sofa.py --select_rx. "
        "example: -l binaural array_six,rear . "
        "default: every receiver except groups sharing one nominal coordinate",
    )
    parser.add_argument(
        "-rx",
        "--receivers",
        type=str,
        default=None,
        help="further restrict to these receiver ids, comma separated (default: %(default)s)",
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        choices=["auto", "freefield", "head"],
        default="auto",
        help="geometry model, 'auto' picks it from the data (default: %(default)s)",
    )
    parser.add_argument(
        "-la",
        "--lit_angle",
        type=float,
        default=_LIT_ANGLE_deg,
        help="half angle of the line-of-sight cone, degrees (default: %(default)s)",
    )
    parser.add_argument(
        "-c",
        "--sound_speed",
        type=float,
        default=None,
        help="speed of sound in m/s, default is computed from the room temperature in config.yaml",
    )
    parser.add_argument(
        "-dt",
        "--distance_tolerance",
        type=float,
        default=_DISTANCE_TOLERANCE_m,
        help="how far one elevation ring may sit from the taped source distance, metres (default: %(default)s)",
    )
    parser.add_argument(
        "-sc",
        "--sigma_clip",
        type=float,
        default=_SIGMA_CLIP,
        help="reject onsets this many sigma off the fit, 0 disables (default: %(default)s)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        default=False,
        help="write the resulting coordinates into the config.yaml of every measure "
        "folder under -i. only position.coord.value of the selected receivers is "
        "touched, the rest of each file is left byte for byte as it is",
    )
    parser.add_argument(
        "--force",
        type=str,
        default=None,
        help="yaml file holding receiver positions under a 'listeners:' key. where it "
        "carries a receiver being solved, its value wins over the measured one. "
        "only meaningful together with --fix",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=_JOBS_DEFAULT,
        help="processes used to read the measure folders, 0 is one per core (default: %(default)s)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="verbose (default: %(default)s)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=False,
        help="print only the ess_params.yaml block, no report (default: %(default)s)",
    )
    parser.add_argument(
        "-s",
        "--silent",
        action="store_true",
        default=False,
        help="print nothing, warnings and errors still go to the log (default: %(default)s)",
    )
    parser.add_argument(
        "-log",
        "--logfile",
        type=str,
        default=None,
        help="log verbose output to file (default: %(default)s)",
    )

    args = parser.parse_args()

    #
    # set debug verbosity. -s and -q are about what lands on stdout, -v is about the
    # log: --silent still lets a warning or an error through, that is the point of it.
    #
    if args.verbose and not args.silent:
        if args.logfile != None:
            logging.basicConfig(filename=args.logfile, encoding="utf-8", level=logging.INFO)
        else:
            logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    if args.silent and args.verbose:
        logger.warning("compute array positioning: --silent overrides --verbose")

    if not os.path.isdir(args.input):
        sys.exit("\n[ERROR] not a folder: {}".format(args.input))

    if (args.force != None) and not args.fix:
        sys.exit("\n[ERROR] --force only means something together with --fix")

    if (args.force != None) and not os.path.isfile(args.force):
        sys.exit("\n[ERROR] not a file: {}".format(args.force))

    ids = None
    if args.receivers != None:
        try:
            ids = [int(x) for x in args.receivers.split(",") if len(x.strip()) > 0]
        except ValueError:
            sys.exit("\n[ERROR] cannot parse the receiver id list: {}".format(args.receivers))

    #
    # STEP-01: work out which receivers of this particular listener we are solving for
    #
    config, folders = first_config(args.input)
    logger.info(
        "compute array positioning: listener '{}', {} receivers declared".format(
            config["setup"]["listeners"][0].get("short_name", "?"),
            config["setup"]["listeners"][0].get("receivers_count", "?"),
        )
    )
    rx_list = resolve_receivers(config, args.list_rx, ids)

    #
    # STEP-02: collect every onset delay written next to the impulse responses
    #
    data = scan_measures(folders, rx_list, config, args.jobs)

    #
    # STEP-03: speed of sound, from the room temperature unless overridden
    #
    if args.sound_speed != None:
        c_air = args.sound_speed
    else:
        try:
            kelvin = float(data["config"]["room"]["temperature"]["value"])
            if data["config"]["room"]["temperature"]["units"] != "kelvin":
                raise ValueError
        except Exception:
            sys.exit("\n[ERROR] no room temperature in kelvin in config.yaml, pass -c instead")
        c_air = sound_speed(kelvin)
        logger.info("compute array positioning: room at {:.2f} K, speed of sound {:.1f} m/s".format(kelvin, c_air))

    #
    # STEP-04: solve, choosing the free-field or the shadowed model
    #
    q, mask, residual, chosen, shape, rings, excess, angle, z_reference = fit_geometry(
        data, c_air, rx_list, args.lit_angle, args.model, args.sigma_clip, args.distance_tolerance
    )

    #
    # STEP-05: a forced file, where given, has the last word over the measurement
    #
    forced = None
    if args.force != None:
        forced = read_forced_positions(args.force, rx_list, data["receivers"])

    positions = resolve_positions(q, shape, rx_list, forced, z_reference)

    #
    # STEP-06: report
    #
    if not args.silent:
        if not args.quiet:
            print_report(
                data, q, positions, mask, residual, chosen, shape, rings, excess, angle, c_air, rx_list, forced
            )
        print_yaml_block(data, positions, rx_list, forced)

    #
    # STEP-07: write the coordinates back into every measure folder
    #
    if args.fix:
        errors, tally = apply_fix(folders, positions, args.jobs)

        if not args.silent:
            print("  --fix: {}".format(", ".join("{} {}".format(tally[k], k) for k in sorted(tally))))
            print("")

        if errors > 0:
            sys.exit("\n[ERROR] --fix failed on {} of {} measure folders".format(errors, len(folders)))
