# Engineering Specification: Constant-Velocity Tracker State Estimator

**Document:** CVT-EST-001  ·  **Revision:** C  ·  **Date:** 2026-03-02  ·  **Status:** Released
**Owner:** Priya Raman (estimator lead)

| Rev | Date       | Change |
|-----|------------|--------|
| B   | 2025-11-03 | §3 interface, §4 recursion, §5 R1–R5, §6 acceptance. |
| C   | 2026-03-02 | Adds R6 (non-finite or malformed measurements), raised by the 2026-02-18 validation incident (batch `val-2026-02-18`, test 1847). |

## 1. Purpose

This specification defines the state-estimation algorithm for the Constant-Velocity
Tracker (CVT), the subsystem that estimates the two-dimensional position and velocity
of a tracked object from a stream of noisy measurements. It is implemented in
MATLAB/Octave as the reference algorithm `kalman_update`.

## 2. Model

The tracker models the object with a four-element state vector

```
x = [ px ; py ; vx ; vy ]
```

where `px, py` are position and `vx, vy` are velocity. The estimator is a linear
Kalman filter with a constant-velocity process model.

### 2.1 Process model

```
x_k = F x_{k-1} + w,     w ~ N(0, Q)
```

### 2.2 Measurement model

```
z_k = H x_k + v,         v ~ N(0, R)
```

`H` is `m x 4` and `R` is `m x m`, where `m` is the measurement dimension. The
position-only sensor has `H = [I2 0]`, so `z_k = [px ; py]` plus noise and `m = 2`.

### 2.3 Constants

`F` (4x4), `Q` (4x4), `H` (m x 4), `R` (m x m), the initial state `x0` (4x1) and the
initial covariance `P0` (4x4) are **provided in `model.json`** and must be read from
there, not hard-coded. The caller supplies them in a `model` struct (§3). A unit time
step is assumed (it is already in `F`).

## 3. Required interface

```matlab
X = kalman_update(Z, model)
```

- **`Z`**: `N x m` matrix of measurements; row `k` is `z_k`.
- **`model`**: struct with fields `F, Q, H, R, x0, P0` (§2.3).
- **`X`**: `N x 4` matrix; row `k` is the **posterior** state estimate after step `k`.

The function must not read files, print, or depend on globals. It is a pure function
of `(Z, model)`.

## 4. Algorithm

Initialise `x = x0`, `P = P0`. For each measurement `z_k` (k = 1..N), perform a
**predict** step followed by a **measurement-update** step, then record the posterior
state as row `k` of `X`.

### 4.1 Predict

```
x = F x
P = F P F' + Q
```

### 4.2 Update

```
y = z_k - H x              % innovation
S = H P H' + R             % innovation covariance
K = P H' / S               % Kalman gain (solve K S = P H'; do not form inv(S) separately)
x = x + K y
P = (I - K H) P            % I is the 4x4 identity
```

The posterior `x` after the update is written to `X(k, :)`.

## 5. Requirements

- **R1** The function shall expose the signature in §3 exactly.
- **R2** The function shall return an `N x 4` matrix of posterior estimates, one row
  per input measurement, in input order.
- **R3** The function shall implement the predict/update recursion of §4 using the
  constants from `model`, initializing state and covariance from `model.x0` and
  `model.P0`.
- **R4** The function shall be deterministic: identical `(Z, model)` yields identical
  `X`.
- **R5** The implementation shall be accompanied by a runnable test that exercises
  R1–R4.
- **R6** Non-finite or malformed measurements shall be rejected and reported, never
  propagated into the state. (Raised by the 2026-02-18 incident: a truncated export
  file put a non-finite measurement into test 1847.)

## 6. Acceptance

The implementation is accepted when its output over a recorded measurement stream,
using the model in `model.json`, reproduces the specified recursion to tight
numerical agreement (maximum absolute state error below 1e-6 against the reference
computation) and its accompanying test runs clean.
