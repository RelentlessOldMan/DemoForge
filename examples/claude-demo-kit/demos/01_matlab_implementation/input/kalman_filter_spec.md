# Engineering Specification - Constant-Velocity Tracker State Estimator

**Document:** CVT-EST-001 | **Revision:** B | **Date:** 2025-11-03 | **Status:** Released

**Owner:** Priya Raman (estimator lead)

## 1. Purpose

This specification defines the state-estimation algorithm for the Constant-Velocity
Tracker (CVT), the subsystem that estimates the two-dimensional position and velocity
of a tracked object from a stream of noisy position measurements. It is to be
implemented in MATLAB/Octave as the reference algorithm `kalman_update`.

## 2. Model

The tracker models the object with a four-element state vector

```
x = [ px ; py ; vx ; vy ]
```

where `px, py` are position and `vx, vy` are velocity. The estimator is a linear
Kalman filter with a constant-velocity process model and a position-only measurement
model.

### 2.1 Process model

Between steps the state evolves by the linear model

```
x_k = F x_{k-1} + w,     w ~ N(0, Q)
```

### 2.2 Measurement model

Each step observes position only, corrupted by noise:

```
z_k = H x_k + v,         v ~ N(0, R)
```

so `z_k = [px ; py]` plus noise. Measurements arrive as the rows of an `N x 2` matrix.

### 2.3 Constants

The matrices `F` (4x4), `Q` (4x4), `H` (2x4), `R` (2x2) and the initial state `x0`
(4x1) and initial covariance `P0` (4x4) are **provided in `model.json`** and must be
read from there - do not hard-code them. The caller supplies them in a `model` struct
(see Section 3). A unit time step is assumed (it is already baked into `F`).

## 3. Required interface

Implement exactly this function:

```matlab
X = kalman_update(Z, model)
```

- **`Z`** - `N x 2` matrix of measurements; row `k` is `z_k`.
- **`model`** - struct with fields `F, Q, H, R, x0, P0` (the Section 2.3 matrices).
- **`X`** - `N x 4` matrix; row `k` is the **posterior** state estimate after step `k`.

The function must not read files, print, or depend on globals - it is a pure function
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

- **R1** The function shall expose the signature in Section 3 exactly.
- **R2** The function shall return an `N x 4` matrix of posterior estimates, one row
  per input measurement, in input order.
- **R3** The function shall implement the predict/update recursion of Section 4 using the
  constants from `model` (sourced from `model.json`).
- **R4** The function shall be deterministic: identical `(Z, model)` yields identical
  `X`.
- **R5** The implementation shall be accompanied by a runnable test that exercises it
  on `test_vectors.csv` (a recorded measurement stream) and checks R1 to R4.

## 6. Acceptance

The implementation is accepted when its output over `test_vectors.csv`, using the
model in `model.json`, reproduces the specified recursion to tight numerical agreement
(maximum absolute state error below 1e-6 against the reference computation) and its
accompanying test runs clean.

## Revision history

| Rev | Date | Author | Change |
|---|---|---|---|
| A | 2025-09-15 | P. Raman | Initial draft for review |
| B | 2025-11-03 | P. Raman | Released for implementation |
